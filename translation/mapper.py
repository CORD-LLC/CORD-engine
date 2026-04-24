"""
CORD Engine — Field Mapper
Determines mapping status (FULL / PARTIAL / NONE) for each source field
by comparing it against the target system's schema.

This is the core translation intelligence. It does not implement
business logic — it implements structural analysis:

  FULL    = value fully representable in target schema
  PARTIAL = value partially representable (truncation, type coercion, array flattening)
  NONE    = no field in target schema can receive this value
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from api.models import CORDField, FieldMapping, MappingStatus


class FieldMapper:
    """
    Maps source CORD fields to legacy schema fields.
    Returns a FieldMapping with status and note for each source field.

    target_schema format:
    {
        "field_name": {
            "type": "string" | "integer" | "float" | "boolean" | "text",
            "max_length": int,        # optional — triggers truncation check
            "array": false,           # optional — if false, arrays will be flattened
            "required": bool          # optional
        },
        ...
    }

    Fields not present in target_schema receive status NONE.
    """

    def map_fields(
        self,
        source_fields: List[CORDField],
        target_schema: Dict[str, Any],
    ) -> List[FieldMapping]:
        """
        Produce a FieldMapping for every source field.
        """
        mappings = []
        for field in source_fields:
            status, note = self._assess_field(field, target_schema)
            mappings.append(FieldMapping(field=field.name, status=status, note=note))
        return mappings

    def _assess_field(
        self,
        field: CORDField,
        target_schema: Dict[str, Any],
    ) -> Tuple[MappingStatus, str]:
        """
        Assess a single field against the target schema.
        Returns (MappingStatus, note).
        """
        # Not in target schema at all → NONE
        if field.name not in target_schema:
            return (
                MappingStatus.NONE,
                f"No field '{field.name}' exists in target schema."
            )

        target_field = target_schema[field.name]
        target_type = target_field.get("type", "string")
        max_length = target_field.get("max_length")
        target_accepts_array = target_field.get("array", False)

        value = field.value
        partial_reasons = []

        # ── Array handling ───────────────────────────────────────────────────
        if isinstance(value, list):
            if not target_accepts_array:
                if len(value) == 0:
                    return (MappingStatus.FULL, "Empty array mapped to empty target field.")
                elif len(value) == 1:
                    # Single-element array → scalar, no real loss
                    pass
                else:
                    partial_reasons.append(
                        f"Source value is an array ({len(value)} items); "
                        f"target field does not accept arrays — will be flattened or truncated."
                    )

        # ── Structured object handling ────────────────────────────────────────
        if isinstance(value, dict):
            target_type_str = str(target_type).lower()
            if target_type_str in ("string", "text"):
                partial_reasons.append(
                    "Source value is a structured object; "
                    "target field accepts string only — structure will be lost."
                )

        # ── Type coercion ─────────────────────────────────────────────────────
        if not isinstance(value, (list, dict)):
            coercion_note = self._check_type_coercion(value, field.type, target_type)
            if coercion_note:
                partial_reasons.append(coercion_note)

        # ── Length truncation ─────────────────────────────────────────────────
        if max_length and isinstance(value, str) and len(value) > max_length:
            partial_reasons.append(
                f"Source value length ({len(value)} chars) exceeds "
                f"target max_length ({max_length}) — will be truncated."
            )

        # ── Determine final status ────────────────────────────────────────────
        if partial_reasons:
            return (MappingStatus.PARTIAL, " ".join(partial_reasons))
        else:
            return (MappingStatus.FULL, "Value fully representable in target schema.")

    def _check_type_coercion(
        self,
        value: Any,
        source_type: str,
        target_type: str,
    ) -> Optional[str]:
        """
        Check if the value requires type coercion and whether data is lost.
        Returns a note string if coercion occurs, None if types are compatible.
        """
        source_type = str(source_type).lower()
        target_type = str(target_type).lower()

        # Identical types — no coercion
        if source_type == target_type:
            return None

        # Numeric → string (no semantic loss, just type coercion)
        if source_type in ("integer", "float", "int") and target_type in ("string", "text"):
            return f"Numeric value will be coerced to string per target schema type."

        # Boolean → string (no semantic loss)
        if source_type == "boolean" and target_type in ("string", "text"):
            return f"Boolean value will be coerced to string (e.g. 'Y'/'N' or 'true'/'false')."

        # Float → integer (precision loss)
        if source_type == "float" and target_type in ("integer", "int"):
            return f"Float value will be truncated to integer — decimal precision lost."

        return None


class LegacyTranslator:
    """
    Translates source CORD fields into a legacy_output dict
    using the target schema as a guide.

    This produces the actual legacy_output object that gets
    written into the target system.
    """

    def translate(
        self,
        source_fields: List[CORDField],
        target_schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Produce a legacy_output dict from source fields + target schema.
        """
        output = {}

        for field in source_fields:
            if field.name not in target_schema:
                continue  # NONE — not writable

            target_field = target_schema[field.name]
            target_type = target_field.get("type", "string")
            max_length = target_field.get("max_length")
            target_accepts_array = target_field.get("array", False)
            target_key = target_field.get("key", field.name)  # allow field rename

            value = self._coerce_value(
                field.value,
                field.type,
                target_type,
                max_length,
                target_accepts_array,
            )

            output[target_key] = value

        return output

    def _coerce_value(
        self,
        value: Any,
        source_type: str,
        target_type: str,
        max_length: Optional[int],
        target_accepts_array: bool,
    ) -> Any:
        """Coerce a source value to the target type."""
        source_type = str(source_type).lower()
        target_type = str(target_type).lower()

        # Array handling
        if isinstance(value, list):
            if target_accepts_array:
                return value
            else:
                # Flatten: take first element or join as string
                if len(value) == 0:
                    return None
                elif len(value) == 1:
                    return self._coerce_scalar(value[0], target_type, max_length)
                else:
                    # Join to comma-separated string for PARTIAL mapping
                    flat = ", ".join(
                        str(v.get("name", v) if isinstance(v, dict) else v)
                        for v in value
                    )
                    return self._apply_max_length(flat, max_length)

        # Structured object → string
        if isinstance(value, dict):
            if target_type in ("string", "text"):
                parts = [f"{k}: {v}" for k, v in value.items()]
                flat = ", ".join(parts)
                return self._apply_max_length(flat, max_length)
            return value

        return self._coerce_scalar(value, target_type, max_length)

    def _coerce_scalar(self, value: Any, target_type: str, max_length: Optional[int]) -> Any:
        """Coerce a scalar value to the target type."""
        if target_type in ("string", "text"):
            result = str(value)
            return self._apply_max_length(result, max_length)
        elif target_type in ("integer", "int"):
            try:
                return int(value)
            except (ValueError, TypeError):
                return value
        elif target_type == "float":
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
        elif target_type == "boolean":
            if isinstance(value, bool):
                return value
            if str(value).lower() in ("true", "yes", "1", "y"):
                return True
            return False
        return value

    def _apply_max_length(self, value: str, max_length: Optional[int]) -> str:
        if max_length and len(value) > max_length:
            return value[:max_length]
        return value
