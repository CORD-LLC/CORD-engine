"""
CORD Engine — Core Models
Pydantic schemas for the full CORD v1.0 specification.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field, validator
import uuid


# ── Enums ────────────────────────────────────────────────────────────────────

class EnvelopeType(str, Enum):
    SNAPSHOT = "snapshot"
    DELTA = "delta"


class MappingStatus(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class FieldType(str, Enum):
    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    CODE = "code"
    CODE_ARRAY = "code_array"
    TEXT_ARRAY = "text_array"
    STRUCTURED = "structured"


class FieldSource(str, Enum):
    NLP = "nlp"
    USER_INPUT = "user_input"
    CLASSIFIER = "classifier"
    RULE = "rule"
    EXTERNAL = "external"


class EventType(str, Enum):
    UTTERANCE = "utterance"
    CLASSIFICATION = "classification"
    INPUT = "input"
    SIGNAL = "signal"
    HANDOFF = "handoff"
    ERROR = "error"


# ── Field Object ─────────────────────────────────────────────────────────────

class CORDField(BaseModel):
    name: str = Field(..., description="Machine-readable field identifier")
    value: Any = Field(..., description="Field value — string, number, array, or object")
    type: str = Field(..., description="Semantic type")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI confidence [0.0–1.0]")
    source: str = Field(..., description="Origin of the field value")
    changed: Optional[bool] = Field(None, description="True if changed from parent (delta only)")

    class Config:
        use_enum_values = True


# ── Field Mapping (in loss report) ──────────────────────────────────────────

class FieldMapping(BaseModel):
    field: str = Field(..., description="Source field name")
    status: MappingStatus = Field(..., description="FULL, PARTIAL, or NONE")
    note: Optional[str] = Field(None, description="Human-readable mapping description")
    partial_coefficient: Optional[float] = Field(
        None,
        description="Resolved PARTIAL coefficient in [0.5, 0.9] when status=PARTIAL. "
                    "Enables EFS auditability — shows which coefficient was used for this field."
    )

    class Config:
        use_enum_values = True


# ── Loss Report ──────────────────────────────────────────────────────────────

class LossReport(BaseModel):
    efs: float = Field(..., ge=0.0, le=1.0, description="Envelope Fidelity Score [0.0–1.0]")
    field_mappings: List[FieldMapping] = Field(default_factory=list)

    class Config:
        use_enum_values = True


# ── Event Log Entry ──────────────────────────────────────────────────────────

class EventLogEntry(BaseModel):
    event_type: str = Field(..., description="Type of event")
    timestamp: str = Field(..., description="UTC ISO 8601 timestamp")
    actor: str = Field(..., description="Entity that produced the event")
    content: Optional[str] = Field(None, description="Event content (utterance events)")
    field: Optional[str] = Field(None, description="Affected field name (classification events)")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional event data")


# ── CORD Envelope ────────────────────────────────────────────────────────────

class CORDEnvelope(BaseModel):
    cord_version: str = Field("1.0", description="CORD spec version")
    envelope_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    envelope_type: EnvelopeType = Field(..., description="snapshot or delta")
    version: int = Field(..., ge=1, description="Monotonic version counter")
    parent_envelope_id: Optional[str] = Field(None, description="Parent UUID; null for chain roots")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat() + "Z"
    )
    domain: str = Field(..., description="Classification domain")
    source_system: str = Field(..., description="Originating AI system identifier")
    target_system: str = Field(..., description="Target legacy system identifier")
    fields: List[CORDField] = Field(default_factory=list)
    legacy_output: Dict[str, Any] = Field(default_factory=dict)
    loss_report: LossReport = Field(
        default_factory=lambda: LossReport(efs=0.0, field_mappings=[])
    )
    event_log: Optional[List[EventLogEntry]] = Field(default_factory=list)
    x_cord_digest: Optional[str] = Field(
        None,
        description="SHA-256 digest of canonical JSON serialization (excluding this field). "
                    "Format: 'sha256:<hex_digest>'. Enables tamper detection at the data layer."
    )

    @validator("envelope_type", pre=True)
    def validate_envelope_type(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v

    @validator("parent_envelope_id", always=True)
    def validate_parent(cls, v, values):
        envelope_type = values.get("envelope_type")
        if envelope_type == EnvelopeType.DELTA and not v:
            raise ValueError("Delta envelopes must have a parent_envelope_id")
        if envelope_type == EnvelopeType.SNAPSHOT and v:
            raise ValueError("Snapshot chain roots must have parent_envelope_id = null")
        return v

    class Config:
        use_enum_values = True


# ── API Request / Response Models ─────────────────────────────────────────────

class TranslateRequest(BaseModel):
    """Request body for POST /translate"""
    domain: str = Field(..., description="Classification domain")
    source_system: str = Field(..., description="Originating AI system")
    target_system: str = Field(..., description="Target legacy system")
    fields: List[CORDField] = Field(..., description="Structured AI-collected fields")
    target_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Target system schema definition for mapping"
    )
    parent_envelope_id: Optional[str] = Field(None, description="Set for delta envelopes")
    parent_version: Optional[int] = Field(None, description="Parent version number")
    field_weights: Optional[Dict[str, float]] = Field(
        None,
        description="Optional per-field weight overrides for EFS computation"
    )
    event_log: Optional[List[EventLogEntry]] = Field(default_factory=list)


class TranslateResponse(BaseModel):
    """Response body from POST /translate"""
    ok: bool = True
    envelope: CORDEnvelope


class ValidateRequest(BaseModel):
    """Request body for POST /validate"""
    envelope: Dict[str, Any]


class ValidateResponse(BaseModel):
    """Response body from POST /validate"""
    ok: bool
    valid: bool
    errors: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    ok: bool = True
    product: str = "CORD Engine"
    version: str = "1.1.0"
    spec_version: str = "1.0"
    status: str = "healthy"
