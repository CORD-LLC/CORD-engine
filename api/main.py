"""
CORD Engine — FastAPI Application
POST /translate   — Translate AI fields into a CORD envelope with EFS
POST /validate    — Validate a CORD envelope against the v1.0 spec
POST /conformance — Run three-category conformance assessment (Claims 15-16)
POST /score       — Compute EFS from pre-existing field mappings
GET  /health      — Health check
GET  /adapters    — List available domain adapters
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models import (
    TranslateRequest, TranslateResponse,
    ValidateRequest, ValidateResponse,
    HealthResponse,
)
from envelope.builder import EnvelopeBuilder, EnvelopeValidator, ReplayProtector, verify_digest
from translation.mapper import FieldMapper, LegacyTranslator
from efs.scorer import EFSScorer
from adapters.adapters import get_adapter, ADAPTER_REGISTRY
from conformance import ConformanceValidator

logger = logging.getLogger("cord_engine")

app = FastAPI(
    title="CORD Engine",
    description=(
        "The open protocol engine for preserving AI-generated data across systems. "
        "Implements CORD v1.0 — envelope construction, field translation, EFS computation, "
        "SHA-256 envelope integrity, replay protection, confidence-based PARTIAL coefficient "
        "propagation, and three-category conformance validation."
    ),
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Service instances ─────────────────────────────────────────────────────────
field_mapper = FieldMapper()
translator = LegacyTranslator()
scorer = EFSScorer()
validator = EnvelopeValidator()
replay_protector = ReplayProtector(staleness_seconds=3600)
conformance_validator = ConformanceValidator()


# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "Internal server error", "detail": str(exc)},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Health check — confirms the engine is running."""
    return HealthResponse()


@app.get("/adapters", tags=["System"])
async def list_adapters():
    """List all available domain adapters."""
    adapters = {}
    for domain, adapter_class in ADAPTER_REGISTRY.items():
        instance = adapter_class()
        adapters[domain] = {
            "domain": domain,
            "target_system": instance.target_system,
            "fields": list(instance.target_schema.keys()),
            "weighted_fields": list(instance.field_weights.keys()) if instance.field_weights else [],
        }
    return {"ok": True, "adapters": adapters}


@app.post(
    "/translate",
    response_model=TranslateResponse,
    tags=["CORD"],
    summary="Translate AI fields into a CORD envelope with EFS",
)
async def translate(req: TranslateRequest):
    """
    Core endpoint. Takes structured AI-collected fields and produces
    a complete CORD envelope with:
    - Full-fidelity field representation
    - Legacy-format output
    - Per-field mapping status (FULL / PARTIAL / NONE)
    - Envelope Fidelity Score (EFS) with confidence propagation
    - SHA-256 x_cord_digest for tamper detection

    If no target_schema is provided, the engine uses the registered
    adapter for the given domain. If no adapter exists for the domain,
    falls back to the generic flat adapter.

    Set parent_envelope_id + parent_version to produce a delta envelope.
    """

    # Resolve target schema
    target_schema = req.target_schema
    field_weights = req.field_weights

    if not target_schema:
        # Use domain adapter as default
        adapter = get_adapter(req.domain)
        target_schema = adapter.target_schema
        if not field_weights:
            field_weights = adapter.field_weights

    # Map fields → determine FULL / PARTIAL / NONE per field
    field_mappings = field_mapper.map_fields(req.fields, target_schema)

    # Translate → produce legacy_output
    legacy_output = translator.translate(req.fields, target_schema)

    # Build confidence map from source fields for PARTIAL propagation
    confidence_map = {f.name: f.confidence for f in req.fields}

    # Score → compute EFS with confidence propagation
    loss_report = scorer.build_loss_report(field_mappings, field_weights, confidence_map)

    # Build envelope (includes x_cord_digest automatically)
    is_delta = bool(req.parent_envelope_id and req.parent_version)

    if is_delta:
        envelope = EnvelopeBuilder.build_delta(
            parent_envelope_id=req.parent_envelope_id,
            parent_version=req.parent_version,
            domain=req.domain,
            source_system=req.source_system,
            target_system=req.target_system,
            changed_fields=req.fields,
            legacy_output=legacy_output,
            loss_report=loss_report,
            event_log=req.event_log,
        )
    else:
        envelope = EnvelopeBuilder.build_snapshot(
            domain=req.domain,
            source_system=req.source_system,
            target_system=req.target_system,
            fields=req.fields,
            legacy_output=legacy_output,
            loss_report=loss_report,
            event_log=req.event_log,
        )

    tier, interpretation = scorer.interpret(loss_report.efs)
    logger.info(
        f"Translated envelope | domain={req.domain} efs={loss_report.efs} "
        f"tier={tier} fields={len(req.fields)} "
        f"type={envelope.envelope_type} id={envelope.envelope_id} "
        f"digest={envelope.x_cord_digest[:20] if envelope.x_cord_digest else 'none'}..."
    )

    return TranslateResponse(envelope=envelope)


@app.post(
    "/validate",
    response_model=ValidateResponse,
    tags=["CORD"],
    summary="Validate a CORD envelope against the v1.0 specification",
)
async def validate(req: ValidateRequest):
    """
    Validates any JSON object against the CORD v1.0 envelope schema.
    Returns a list of validation errors. Empty errors = valid envelope.
    Includes x_cord_digest integrity verification when digest is present.
    """
    errors = validator.validate(req.envelope)
    return ValidateResponse(
        ok=True,
        valid=len(errors) == 0,
        errors=errors,
    )


@app.post(
    "/conformance",
    tags=["CORD"],
    summary="Run three-category conformance assessment (Claims 15-16)",
)
async def conformance(body: Dict[str, Any]):
    """
    Runs the full three-category conformance validation framework
    and classifies the envelope into one of four tiers:

    - CORD-Compliant: passes all three categories
    - CORD-Partial: passes Cat 2 + 3 but omits event logs, notes, or version chaining
    - CORD-Compatible: produces core fields without full EFS reporting
    - Non-Compliant: does not produce CORD-structured envelopes

    Body: a CORD envelope dict (or {"envelope": {...}})
    """
    envelope_dict = body.get("envelope", body)
    report = conformance_validator.assess(envelope_dict)
    return {"ok": True, **report.dict()}


@app.post(
    "/replay-check",
    tags=["CORD"],
    summary="Check envelope for replay attacks",
)
async def replay_check(body: Dict[str, Any]):
    """
    Validates envelope_id uniqueness and created_at staleness.
    Returns rejection reasons if the envelope fails replay protection.
    """
    envelope_dict = body.get("envelope", body)
    envelope_id = envelope_dict.get("envelope_id", "")
    created_at = envelope_dict.get("created_at", "")

    errors = replay_protector.check(envelope_id, created_at)
    return {
        "ok": len(errors) == 0,
        "accepted": len(errors) == 0,
        "errors": errors,
    }


@app.post(
    "/verify-digest",
    tags=["CORD"],
    summary="Verify SHA-256 envelope integrity",
)
async def verify_digest_endpoint(body: Dict[str, Any]):
    """
    Verifies the x_cord_digest of an envelope.
    Returns whether the digest matches the canonical serialization.
    """
    envelope_dict = body.get("envelope", body)
    digest = envelope_dict.get("x_cord_digest")

    if not digest:
        return {
            "ok": True,
            "verified": False,
            "reason": "No x_cord_digest present in envelope",
        }

    is_valid = verify_digest(envelope_dict)
    return {
        "ok": True,
        "verified": is_valid,
        "digest": digest,
        "reason": "Digest matches canonical serialization" if is_valid else "INTEGRITY FAILURE — envelope has been modified",
    }


@app.post(
    "/score",
    tags=["CORD"],
    summary="Compute EFS from a list of field mappings",
)
async def score(body: Dict[str, Any]):
    """
    Compute an EFS score from a pre-existing list of field mappings.
    Useful when you have already determined FULL/PARTIAL/NONE
    and just want the aggregate score.

    Body:
    {
        "field_mappings": [
            {"field": "name", "status": "FULL"},
            {"field": "symptoms", "status": "PARTIAL"},
            {"field": "history", "status": "NONE"}
        ],
        "field_weights": {"symptoms": 2.0},  // optional
        "confidence_map": {"symptoms": 0.85}  // optional — enables PARTIAL propagation
    }
    """
    from api.models import FieldMapping
    raw_mappings = body.get("field_mappings", [])
    field_weights = body.get("field_weights")
    confidence_map = body.get("confidence_map")

    try:
        mappings = [FieldMapping(**m) for m in raw_mappings]
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid field_mappings: {e}")

    efs = scorer.compute(mappings, field_weights, confidence_map)
    tier, interpretation = scorer.interpret(efs)

    return {
        "ok": True,
        "efs": efs,
        "tier": tier,
        "interpretation": interpretation,
        "field_count": len(mappings),
        "full_count": sum(1 for m in mappings if m.status == "FULL"),
        "partial_count": sum(1 for m in mappings if m.status == "PARTIAL"),
        "none_count": sum(1 for m in mappings if m.status == "NONE"),
    }
