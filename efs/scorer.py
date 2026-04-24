"""
CORD Engine — EFS Scorer
Envelope Fidelity Score computation engine.

EFS = Σ(weight_i × fidelity_coefficient_i) / Σ(weight_i)

Fidelity coefficients:
  FULL    → 1.0
  PARTIAL → configurable (default 0.5, per CORD v1.0 RFC baseline range 0.5–0.9)
  NONE    → 0.0

PARTIAL coefficient selection:
  When confidence scores are available, the PARTIAL coefficient is derived
  from the AI confidence on the source field:
    - confidence < low_threshold  → coefficient = 0.5 (floor)
    - confidence >= high_threshold → coefficient = 0.9 (ceiling)
    - otherwise → linear interpolation in [0.5, 0.9]
  When confidence is not provided, the baseline (0.5) is used.

Implementations MUST NOT use a PARTIAL coefficient below 0.5.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from api.models import CORDField, FieldMapping, MappingStatus


# CORD v1.0 RFC — PARTIAL coefficient bounds
PARTIAL_FLOOR = 0.5
PARTIAL_CEILING = 0.9
PARTIAL_BASELINE = 0.5

# Default fidelity coefficients per mapping status
DEFAULT_COEFFICIENTS = {
    MappingStatus.FULL: 1.0,
    MappingStatus.PARTIAL: PARTIAL_BASELINE,
    MappingStatus.NONE: 0.0,
}

# Default field weight — all fields equal unless overridden
DEFAULT_FIELD_WEIGHT = 1.0


class EFSScorer:
    """
    Computes the Envelope Fidelity Score (EFS) for a CORD translation.

    Field weighting is configurable per-request via field_weights dict.
    Partial coefficient defaults to 0.5 (per CORD v1.0 RFC baseline).
    Range is [0.5, 0.9] — implementations MUST NOT go below 0.5.

    When confidence propagation is enabled, the PARTIAL coefficient for
    each field is derived from the AI's confidence score on that field.
    """

    def __init__(
        self,
        partial_coefficient: float = PARTIAL_BASELINE,
        default_weight: float = 1.0,
        confidence_low_threshold: float = 0.5,
        confidence_high_threshold: float = 0.95,
    ):
        # Enforce floor
        if partial_coefficient < PARTIAL_FLOOR:
            raise ValueError(
                f"PARTIAL coefficient {partial_coefficient} is below the "
                f"CORD v1.0 floor of {PARTIAL_FLOOR}. "
                f"Implementations MUST NOT use a value below {PARTIAL_FLOOR}."
            )
        if partial_coefficient > PARTIAL_CEILING:
            raise ValueError(
                f"PARTIAL coefficient {partial_coefficient} exceeds the "
                f"CORD v1.0 ceiling of {PARTIAL_CEILING}."
            )

        self.partial_coefficient = partial_coefficient
        self.default_weight = default_weight
        self.confidence_low_threshold = confidence_low_threshold
        self.confidence_high_threshold = confidence_high_threshold
        self.coefficients = {
            MappingStatus.FULL: 1.0,
            MappingStatus.PARTIAL: partial_coefficient,
            MappingStatus.NONE: 0.0,
        }

    def _resolve_partial_coefficient(
        self,
        field_name: str,
        confidence_map: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Resolve the PARTIAL coefficient for a specific field.

        If a confidence score is available for this field, the coefficient
        is derived via linear interpolation in [0.5, 0.9] based on the
        confidence value relative to the low/high thresholds.

        If no confidence is available, returns the instance baseline.
        """
        if not confidence_map or field_name not in confidence_map:
            return self.partial_coefficient

        confidence = confidence_map[field_name]

        if confidence < self.confidence_low_threshold:
            return PARTIAL_FLOOR
        elif confidence >= self.confidence_high_threshold:
            return PARTIAL_CEILING
        else:
            # Linear interpolation between floor and ceiling
            range_conf = self.confidence_high_threshold - self.confidence_low_threshold
            if range_conf <= 0:
                return self.partial_coefficient
            t = (confidence - self.confidence_low_threshold) / range_conf
            return round(PARTIAL_FLOOR + t * (PARTIAL_CEILING - PARTIAL_FLOOR), 4)

    def compute(
        self,
        field_mappings: List[FieldMapping],
        field_weights: Optional[Dict[str, float]] = None,
        confidence_map: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Compute the EFS from a list of field mappings.

        Args:
            field_mappings: List of FieldMapping with status per field
            field_weights: Optional dict of field_name -> weight override
            confidence_map: Optional dict of field_name -> AI confidence [0.0-1.0]
                           Used for PARTIAL coefficient propagation

        Returns:
            EFS float rounded to 2 decimal places in [0.0, 1.0]
        """
        if not field_mappings:
            return 1.0  # no fields = nothing to lose

        weights = field_weights or {}
        total_weight = 0.0
        fidelity_sum = 0.0

        for mapping in field_mappings:
            weight = weights.get(mapping.field, self.default_weight)
            status = MappingStatus(mapping.status) if isinstance(mapping.status, str) else mapping.status

            if status == MappingStatus.PARTIAL:
                coefficient = self._resolve_partial_coefficient(
                    mapping.field, confidence_map
                )
                # Store the resolved coefficient on the mapping for auditability
                mapping.partial_coefficient = coefficient
            else:
                coefficient = self.coefficients.get(status, 0.0)

            fidelity_sum += weight * coefficient
            total_weight += weight

        if total_weight == 0:
            return 1.0

        efs = fidelity_sum / total_weight
        return round(min(max(efs, 0.0), 1.0), 2)

    def build_loss_report(
        self,
        field_mappings: List[FieldMapping],
        field_weights: Optional[Dict[str, float]] = None,
        confidence_map: Optional[Dict[str, float]] = None,
    ) -> "LossReport":
        """
        Compute EFS and return a complete LossReport object.
        """
        from api.models import LossReport
        efs = self.compute(field_mappings, field_weights, confidence_map)
        return LossReport(efs=efs, field_mappings=field_mappings)

    def interpret(self, efs: float) -> Tuple[str, str]:
        """
        Return (tier, description) for a given EFS value.
        Useful for logging and API responses.
        """
        if efs >= 0.90:
            return ("high", "High fidelity — legacy record is a reliable representation of source data")
        elif efs >= 0.50:
            return ("moderate", "Moderate fidelity — meaningful content preserved but significant information lost")
        else:
            return ("low", "Low fidelity — most structured content lost; target system schema has significant gaps")
