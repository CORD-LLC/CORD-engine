"""
CORD Engine — Envelope Builder
Constructs, validates, and integrity-protects CORD Interaction Envelopes.

SHA-256 envelope integrity via x_cord_digest
Replay protection via envelope_id uniqueness + staleness threshold
Delta envelopes with empty fields array for event-log-only updates
"""

from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from api.models import (
    CORDEnvelope, CORDField, EnvelopeType,
    LossReport, FieldMapping, EventLogEntry
)


def compute_digest(envelope_dict: Dict[str, Any]) -> str:
    """
    Compute SHA-256 digest of the canonical JSON serialization of a
    CORD envelope, excluding the x_cord_digest field itself.

    Returns: 'sha256:<hex_digest>'

    Per The digest enables tamper detection at the data layer
    without external signing infrastructure.
    """
    # Remove digest field if present before hashing
    to_hash = {k: v for k, v in envelope_dict.items() if k != "x_cord_digest"}
    # Canonical JSON: sorted keys, no whitespace, ensure_ascii for determinism
    canonical = json.dumps(to_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class ReplayProtector:
    """
    Validates envelope_id uniqueness and created_at staleness.

    Per Rejects envelopes with duplicate envelope_id values
    and envelopes with created_at timestamps older than a configurable
    staleness threshold.
    """

    def __init__(self, staleness_seconds: int = 3600):
        self._seen_ids: Set[str] = set()
        self.staleness_seconds = staleness_seconds

    def check(self, envelope_id: str, created_at: str) -> List[str]:
        """
        Returns list of rejection reasons. Empty = accepted.
        """
        errors = []

        # Uniqueness check
        if envelope_id in self._seen_ids:
            errors.append(
                f"Replay rejected: envelope_id '{envelope_id}' has already been ingested."
            )

        # Staleness check
        try:
            ts = created_at.rstrip("Z")
            envelope_time = datetime.fromisoformat(ts)
            # Make naive datetime UTC-aware if needed
            if envelope_time.tzinfo is None:
                envelope_time = envelope_time.replace(tzinfo=timezone.utc)
            threshold = datetime.now(timezone.utc) - timedelta(seconds=self.staleness_seconds)
            if envelope_time < threshold:
                errors.append(
                    f"Replay rejected: created_at '{created_at}' is older than "
                    f"staleness threshold ({self.staleness_seconds}s)."
                )
        except (ValueError, TypeError):
            # Can't parse timestamp — don't reject on staleness but note it
            pass

        if not errors:
            self._seen_ids.add(envelope_id)

        return errors

    def reset(self):
        """Clear all seen IDs. Useful for testing."""
        self._seen_ids.clear()


class EnvelopeBuilder:
    """
    Builds CORD Interaction Envelopes.
    Use build_snapshot() for new chains.
    Use build_delta() for incremental updates.

    All envelopes include x_cord_digest (SHA-256) for integrity verification.
    """

    @staticmethod
    def _attach_digest(envelope: CORDEnvelope) -> CORDEnvelope:
        """Compute and attach SHA-256 digest to the envelope."""
        envelope_dict = envelope.dict()
        envelope.x_cord_digest = compute_digest(envelope_dict)
        return envelope

    @staticmethod
    def build_snapshot(
        domain: str,
        source_system: str,
        target_system: str,
        fields: List[CORDField],
        legacy_output: Dict[str, Any],
        loss_report: LossReport,
        event_log: Optional[List[EventLogEntry]] = None,
    ) -> CORDEnvelope:
        """
        Build a snapshot envelope — the root of a new version chain.
        parent_envelope_id is always null for snapshots.
        Automatically computes and attaches x_cord_digest.
        """
        envelope = CORDEnvelope(
            cord_version="1.0",
            envelope_id=str(uuid.uuid4()),
            envelope_type=EnvelopeType.SNAPSHOT,
            version=1,
            parent_envelope_id=None,
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            domain=domain,
            source_system=source_system,
            target_system=target_system,
            fields=fields,
            legacy_output=legacy_output,
            loss_report=loss_report,
            event_log=event_log or [],
        )
        return EnvelopeBuilder._attach_digest(envelope)

    @staticmethod
    def build_delta(
        parent_envelope_id: str,
        parent_version: int,
        domain: str,
        source_system: str,
        target_system: str,
        changed_fields: List[CORDField],
        legacy_output: Dict[str, Any],
        loss_report: LossReport,
        event_log: Optional[List[EventLogEntry]] = None,
    ) -> CORDEnvelope:
        """
        Build a delta envelope — an incremental update to a version chain.
        Only include fields that changed from the parent.
        Each changed field will have changed=True.
        Automatically computes and attaches x_cord_digest.

        Per A delta with empty fields array is valid when the
        purpose is to record event log entries without modifying field state.
        """
        # Mark all fields as changed
        for field in changed_fields:
            field.changed = True

        envelope = CORDEnvelope(
            cord_version="1.0",
            envelope_id=str(uuid.uuid4()),
            envelope_type=EnvelopeType.DELTA,
            version=parent_version + 1,
            parent_envelope_id=parent_envelope_id,
            created_at=datetime.now(timezone.utc).isoformat() + "Z",
            domain=domain,
            source_system=source_system,
            target_system=target_system,
            fields=changed_fields,
            legacy_output=legacy_output,
            loss_report=loss_report,
            event_log=event_log or [],
        )
        return EnvelopeBuilder._attach_digest(envelope)


def verify_digest(envelope_dict: Dict[str, Any]) -> bool:
    """
    Verify the x_cord_digest of an envelope.
    Returns True if the digest matches, False if tampered or missing.
    """
    stored_digest = envelope_dict.get("x_cord_digest")
    if not stored_digest:
        return False

    expected = compute_digest(envelope_dict)
    return stored_digest == expected


class EnvelopeValidator:
    """
    Validates CORD envelopes against the v1.0 specification.
    Returns a list of validation errors (empty = valid).
    """

    def validate(self, envelope_dict: Dict[str, Any]) -> List[str]:
        errors = []

        # Required top-level fields
        required = [
            "cord_version", "envelope_id", "envelope_type", "version",
            "parent_envelope_id", "created_at", "domain",
            "source_system", "target_system", "fields",
            "legacy_output", "loss_report"
        ]
        for field in required:
            if field not in envelope_dict:
                errors.append(f"Missing required field: '{field}'")

        if errors:
            return errors  # stop early if missing basics

        # cord_version
        if envelope_dict.get("cord_version") != "1.0":
            errors.append(f"Unsupported cord_version: '{envelope_dict.get('cord_version')}'. Expected '1.0'")

        # envelope_type
        et = envelope_dict.get("envelope_type")
        if et not in ("snapshot", "delta"):
            errors.append(f"envelope_type must be 'snapshot' or 'delta', got '{et}'")

        # version
        version = envelope_dict.get("version")
        if not isinstance(version, int) or version < 1:
            errors.append("version must be an integer >= 1")

        # parent_envelope_id logic
        parent_id = envelope_dict.get("parent_envelope_id")
        if et == "delta" and not parent_id:
            errors.append("Delta envelopes must have a parent_envelope_id")
        if et == "snapshot" and parent_id is not None:
            errors.append("Snapshot chain roots must have parent_envelope_id = null")

        # fields array
        fields = envelope_dict.get("fields", [])
        if not isinstance(fields, list):
            errors.append("'fields' must be an array")
        else:
            field_names = []
            for i, f in enumerate(fields):
                if not isinstance(f, dict):
                    errors.append(f"fields[{i}] must be an object")
                    continue
                for req in ["name", "value", "type", "confidence", "source"]:
                    if req not in f:
                        errors.append(f"fields[{i}] missing required property '{req}'")
                if "name" in f:
                    if f["name"] in field_names:
                        errors.append(f"Duplicate field name '{f['name']}' in fields array")
                    field_names.append(f["name"])
                if "confidence" in f:
                    c = f["confidence"]
                    if not isinstance(c, (int, float)) or not (0.0 <= c <= 1.0):
                        errors.append(f"fields[{i}].confidence must be float in [0.0, 1.0]")

        # loss_report
        lr = envelope_dict.get("loss_report", {})
        if not isinstance(lr, dict):
            errors.append("'loss_report' must be an object")
        else:
            if "efs" not in lr:
                errors.append("loss_report missing required field 'efs'")
            else:
                efs = lr["efs"]
                if not isinstance(efs, (int, float)) or not (0.0 <= efs <= 1.0):
                    errors.append("loss_report.efs must be float in [0.0, 1.0]")
            if "field_mappings" not in lr:
                errors.append("loss_report missing required field 'field_mappings'")
            else:
                for i, fm in enumerate(lr.get("field_mappings", [])):
                    if not isinstance(fm, dict):
                        errors.append(f"loss_report.field_mappings[{i}] must be an object")
                        continue
                    if "field" not in fm:
                        errors.append(f"loss_report.field_mappings[{i}] missing 'field'")
                    if "status" not in fm:
                        errors.append(f"loss_report.field_mappings[{i}] missing 'status'")
                    elif fm["status"] not in ("FULL", "PARTIAL", "NONE"):
                        errors.append(
                            f"loss_report.field_mappings[{i}].status must be FULL, PARTIAL, or NONE"
                        )

        # legacy_output
        if not isinstance(envelope_dict.get("legacy_output"), dict):
            errors.append("'legacy_output' must be an object")

        # x_cord_digest integrity check (if present)
        if "x_cord_digest" in envelope_dict and envelope_dict["x_cord_digest"]:
            if not verify_digest(envelope_dict):
                errors.append("x_cord_digest integrity check failed — envelope may have been tampered with")

        return errors
