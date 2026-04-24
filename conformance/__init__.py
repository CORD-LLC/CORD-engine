"""
CORD Engine — Conformance Validator
Implements the three-category conformance validation framework
and four-tier classification system.

Validation Categories:
  Category 1 — Envelope Structure: required fields, types, constraints
  Category 2 — EFS Reporting: loss_report present, EFS computed, field_mappings complete
  Category 3 — Mapping Completeness: every source field has a mapping entry

Conformance Tiers:
  CORD-Compliant:  passes all three categories
  CORD-Partial:    passes Category 2 + 3, but omits event logs, per-field notes, or version chaining
  CORD-Compatible: produces/consumes core envelope fields without full EFS reporting
  Non-Compliant:   does not produce CORD-structured envelopes
"""

from __future__ import annotations
from typing import Any, Dict, List, Tuple
from enum import Enum


class ConformanceTier(str, Enum):
    COMPLIANT = "CORD-Compliant"
    PARTIAL = "CORD-Partial"
    COMPATIBLE = "CORD-Compatible"
    NON_COMPLIANT = "Non-Compliant"


class CategoryResult:
    """Result of a single validation category."""

    def __init__(self, category: int, name: str, passed: bool, details: List[str]):
        self.category = category
        self.name = name
        self.passed = passed
        self.details = details

    def dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
        }


class ConformanceReport:
    """Full conformance assessment result."""

    def __init__(
        self,
        tier: ConformanceTier,
        categories: List[CategoryResult],
        summary: str,
    ):
        self.tier = tier
        self.categories = categories
        self.summary = summary

    def dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier.value,
            "categories": [c.dict() for c in self.categories],
            "summary": self.summary,
        }


class ConformanceValidator:
    """
    Runs the three-category conformance validation framework
    and classifies the implementation into one of four tiers.
    """

    def assess(self, envelope_dict: Dict[str, Any]) -> ConformanceReport:
        """
        Run all three validation categories against an envelope
        and return a ConformanceReport with tier classification.
        """
        cat1 = self._validate_category_1(envelope_dict)
        cat2 = self._validate_category_2(envelope_dict)
        cat3 = self._validate_category_3(envelope_dict)

        categories = [cat1, cat2, cat3]
        tier = self._classify_tier(envelope_dict, cat1, cat2, cat3)

        summary = self._build_summary(tier, categories)
        return ConformanceReport(tier=tier, categories=categories, summary=summary)

    def _validate_category_1(self, envelope_dict: Dict[str, Any]) -> CategoryResult:
        """
        Category 1 — Envelope Structure
        Validates required fields, types, and structural constraints.
        """
        details = []
        passed = True

        # Required top-level fields
        required = [
            "cord_version", "envelope_id", "envelope_type", "version",
            "parent_envelope_id", "created_at", "domain",
            "source_system", "target_system", "fields",
            "legacy_output", "loss_report"
        ]
        for field in required:
            if field not in envelope_dict:
                details.append(f"Missing required field: '{field}'")
                passed = False

        if not passed:
            return CategoryResult(1, "Envelope Structure", False, details)

        # cord_version
        if envelope_dict.get("cord_version") != "1.0":
            details.append(f"Unsupported cord_version: '{envelope_dict.get('cord_version')}'")
            passed = False

        # envelope_type
        et = envelope_dict.get("envelope_type")
        if et not in ("snapshot", "delta"):
            details.append(f"Invalid envelope_type: '{et}'")
            passed = False

        # version
        version = envelope_dict.get("version")
        if not isinstance(version, int) or version < 1:
            details.append("version must be integer >= 1")
            passed = False

        # parent_envelope_id consistency
        parent_id = envelope_dict.get("parent_envelope_id")
        if et == "delta" and not parent_id:
            details.append("Delta envelope missing parent_envelope_id")
            passed = False
        if et == "snapshot" and parent_id is not None:
            details.append("Snapshot has non-null parent_envelope_id")
            passed = False

        # fields array structure
        fields = envelope_dict.get("fields", [])
        if not isinstance(fields, list):
            details.append("'fields' must be an array")
            passed = False
        else:
            for i, f in enumerate(fields):
                if not isinstance(f, dict):
                    details.append(f"fields[{i}] is not an object")
                    passed = False
                    continue
                for req in ["name", "value", "type", "confidence", "source"]:
                    if req not in f:
                        details.append(f"fields[{i}] missing '{req}'")
                        passed = False

        # legacy_output type
        if not isinstance(envelope_dict.get("legacy_output"), dict):
            details.append("'legacy_output' must be an object")
            passed = False

        if passed:
            details.append("All structural requirements satisfied")

        return CategoryResult(1, "Envelope Structure", passed, details)

    def _validate_category_2(self, envelope_dict: Dict[str, Any]) -> CategoryResult:
        """
        Category 2 — EFS Reporting
        Validates loss_report presence, EFS computation, and field_mappings.
        """
        details = []
        passed = True

        lr = envelope_dict.get("loss_report")
        if not isinstance(lr, dict):
            details.append("loss_report missing or not an object")
            return CategoryResult(2, "EFS Reporting", False, details)

        # EFS present and valid
        efs = lr.get("efs")
        if efs is None:
            details.append("loss_report.efs is missing")
            passed = False
        elif not isinstance(efs, (int, float)):
            details.append(f"loss_report.efs is not numeric: {type(efs)}")
            passed = False
        elif not (0.0 <= efs <= 1.0):
            details.append(f"loss_report.efs out of range [0.0, 1.0]: {efs}")
            passed = False

        # field_mappings present and valid
        fm = lr.get("field_mappings")
        if fm is None:
            details.append("loss_report.field_mappings is missing")
            passed = False
        elif not isinstance(fm, list):
            details.append("loss_report.field_mappings is not an array")
            passed = False
        else:
            valid_statuses = {"FULL", "PARTIAL", "NONE"}
            for i, m in enumerate(fm):
                if not isinstance(m, dict):
                    details.append(f"field_mappings[{i}] is not an object")
                    passed = False
                    continue
                if "field" not in m:
                    details.append(f"field_mappings[{i}] missing 'field'")
                    passed = False
                if "status" not in m:
                    details.append(f"field_mappings[{i}] missing 'status'")
                    passed = False
                elif m["status"] not in valid_statuses:
                    details.append(f"field_mappings[{i}].status invalid: '{m['status']}'")
                    passed = False

        if passed:
            details.append("EFS reporting requirements satisfied")

        return CategoryResult(2, "EFS Reporting", passed, details)

    def _validate_category_3(self, envelope_dict: Dict[str, Any]) -> CategoryResult:
        """
        Category 3 — Mapping Completeness
        Every source field must have a corresponding entry in field_mappings.
        """
        details = []
        passed = True

        fields = envelope_dict.get("fields", [])
        lr = envelope_dict.get("loss_report", {})
        fm = lr.get("field_mappings", [])

        if not isinstance(fields, list) or not isinstance(fm, list):
            details.append("Cannot assess — fields or field_mappings not valid arrays")
            return CategoryResult(3, "Mapping Completeness", False, details)

        # Build set of field names from source fields
        source_names = set()
        for f in fields:
            if isinstance(f, dict) and "name" in f:
                source_names.add(f["name"])

        # Build set of mapped field names
        mapped_names = set()
        for m in fm:
            if isinstance(m, dict) and "field" in m:
                mapped_names.add(m["field"])

        # Check coverage
        unmapped = source_names - mapped_names
        if unmapped:
            details.append(
                f"Source fields without mapping entries: {sorted(unmapped)}"
            )
            passed = False

        # Empty fields array is valid for event-log-only deltas
        if len(fields) == 0:
            et = envelope_dict.get("envelope_type")
            if et == "delta":
                details.append("Empty fields array — valid event-log-only delta")
                passed = True
            else:
                details.append("Empty fields array on snapshot — no fields to map")

        if passed and not unmapped:
            details.append(
                f"All {len(source_names)} source fields have mapping entries"
            )

        return CategoryResult(3, "Mapping Completeness", passed, details)

    def _classify_tier(
        self,
        envelope_dict: Dict[str, Any],
        cat1: CategoryResult,
        cat2: CategoryResult,
        cat3: CategoryResult,
    ) -> ConformanceTier:
        """
        Classify into one of four conformance tiers per 
        """
        all_pass = cat1.passed and cat2.passed and cat3.passed

        if all_pass:
            # Check for optional elements that distinguish Compliant from Partial
            has_event_log = bool(envelope_dict.get("event_log"))
            has_notes = any(
                isinstance(m, dict) and m.get("note")
                for m in envelope_dict.get("loss_report", {}).get("field_mappings", [])
            )
            has_version_chain = (
                envelope_dict.get("envelope_type") == "delta"
                and envelope_dict.get("parent_envelope_id")
            ) or envelope_dict.get("version", 0) >= 1

            # CORD-Compliant requires event log, notes, and version support
            if has_event_log and has_notes:
                return ConformanceTier.COMPLIANT
            else:
                return ConformanceTier.PARTIAL

        if cat2.passed and cat3.passed:
            # Structure failed but EFS + mappings present
            return ConformanceTier.PARTIAL

        if cat1.passed:
            # Structure OK but EFS reporting incomplete
            return ConformanceTier.COMPATIBLE

        return ConformanceTier.NON_COMPLIANT

    def _build_summary(
        self, tier: ConformanceTier, categories: List[CategoryResult]
    ) -> str:
        passed = sum(1 for c in categories if c.passed)
        total = len(categories)
        return (
            f"{tier.value}: {passed}/{total} validation categories passed. "
            f"Cat 1 (Structure): {'PASS' if categories[0].passed else 'FAIL'} | "
            f"Cat 2 (EFS): {'PASS' if categories[1].passed else 'FAIL'} | "
            f"Cat 3 (Mapping): {'PASS' if categories[2].passed else 'FAIL'}"
        )
