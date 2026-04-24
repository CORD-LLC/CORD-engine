"""
CORD Engine — Versioning
Snapshot/delta chain management and state materialization.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from api.models import CORDEnvelope, CORDField


class VersionChain:
    """
    Manages a CORD version chain.
    Materializes full interaction state by replaying snapshot + deltas.
    """

    def __init__(self):
        self._envelopes: List[CORDEnvelope] = []

    def add(self, envelope: CORDEnvelope) -> None:
        """Add an envelope to the chain in version order."""
        self._envelopes.append(envelope)
        self._envelopes.sort(key=lambda e: e.version)

    def root(self) -> Optional[CORDEnvelope]:
        """Return the chain root snapshot."""
        if not self._envelopes:
            return None
        root = self._envelopes[0]
        if root.envelope_type != "snapshot":
            raise ValueError("Version chain root must be a snapshot envelope")
        return root

    def materialize(self, at_version: Optional[int] = None) -> Dict[str, Any]:
        """
        Reconstruct full interaction state at a given version.
        If at_version is None, materializes the latest state.

        Returns a dict of field_name -> CORDField representing
        the full merged field state.
        """
        if not self._envelopes:
            return {}

        target_version = at_version or self._envelopes[-1].version

        # Start from snapshot
        root = self.root()
        state: Dict[str, CORDField] = {
            f.name: f for f in root.fields
        }

        if root.version == target_version:
            return state

        # Apply deltas in order up to target_version
        for envelope in self._envelopes[1:]:
            if envelope.version > target_version:
                break
            if envelope.envelope_type == "delta":
                for field in envelope.fields:
                    if field.changed:
                        state[field.name] = field

        return state

    def latest_fields(self) -> Dict[str, CORDField]:
        """Return the materialized field state at the latest version."""
        return self.materialize()

    def validate_chain(self) -> List[str]:
        """
        Validate the integrity of the version chain.
        Returns a list of errors (empty = valid chain).
        """
        errors = []
        if not self._envelopes:
            return errors

        # First must be snapshot
        if self._envelopes[0].envelope_type != "snapshot":
            errors.append("Chain must start with a snapshot envelope")

        # Version numbers must be monotonically increasing
        versions = [e.version for e in self._envelopes]
        for i in range(1, len(versions)):
            if versions[i] <= versions[i - 1]:
                errors.append(
                    f"Version {versions[i]} is not greater than {versions[i-1]}"
                )

        # Each delta must reference the preceding envelope
        for i in range(1, len(self._envelopes)):
            current = self._envelopes[i]
            previous = self._envelopes[i - 1]
            if current.envelope_type == "delta":
                if current.parent_envelope_id != previous.envelope_id:
                    errors.append(
                        f"Envelope v{current.version} parent_envelope_id "
                        f"'{current.parent_envelope_id}' does not match "
                        f"preceding envelope id '{previous.envelope_id}'"
                    )

        return errors
