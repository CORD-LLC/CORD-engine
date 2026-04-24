"""
CORD Engine — Test Suite v1.1
Validates all core engine components end-to-end.
Run: python -m pytest tests/ -v
Or:  python tests/test_engine.py

Tests 1-20:  Original functionality (updated for 0.5 baseline)
Tests 21-34: New — digest, replay, confidence, conformance, auditability
"""

import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.models import CORDField, FieldMapping, MappingStatus, EnvelopeType, LossReport
from envelope.builder import (
    EnvelopeBuilder, EnvelopeValidator,
    ReplayProtector, compute_digest, verify_digest,
)
from envelope.versioning import VersionChain
from translation.mapper import FieldMapper, LegacyTranslator
from efs.scorer import EFSScorer, PARTIAL_FLOOR, PARTIAL_CEILING, PARTIAL_BASELINE
from adapters.adapters import (
    HealthcareEHRAdapter, AutomotiveDMSAdapter,
    RealEstateMLSAdapter, HRATSAdapter, get_adapter
)
from event_log.logger import EventLogger
from conformance import ConformanceValidator, ConformanceTier


def make_field(name, value, ftype="text", confidence=0.9, source="nlp"):
    return CORDField(name=name, value=value, type=ftype, confidence=confidence, source=source)


# ═══════════════════════════════════════════════════════════════════
# TEST 1: EFS Scorer — basic computation (UPDATED: 0.5 baseline)
# ═══════════════════════════════════════════════════════════════════
def test_efs_basic():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="a", status=MappingStatus.FULL),
        FieldMapping(field="b", status=MappingStatus.PARTIAL),
        FieldMapping(field="c", status=MappingStatus.NONE),
    ]
    efs = scorer.compute(mappings)
    # (1.0 + 0.5 + 0.0) / 3 = 0.5
    assert efs == 0.5, f"Expected 0.5, got {efs}"
    print(f"  TEST 1 PASS — EFS basic: {efs} (FULL=1.0, PARTIAL=0.5, NONE=0.0)")


# ═══════════════════════════════════════════════════════════════════
# TEST 2: EFS Scorer — all FULL = 1.0
# ═══════════════════════════════════════════════════════════════════
def test_efs_all_full():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="x", status=MappingStatus.FULL),
        FieldMapping(field="y", status=MappingStatus.FULL),
    ]
    efs = scorer.compute(mappings)
    assert efs == 1.0, f"Expected 1.0, got {efs}"
    print(f"  TEST 2 PASS — EFS all FULL: {efs}")


# ═══════════════════════════════════════════════════════════════════
# TEST 3: EFS Scorer — all NONE = 0.0
# ═══════════════════════════════════════════════════════════════════
def test_efs_all_none():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="x", status=MappingStatus.NONE),
        FieldMapping(field="y", status=MappingStatus.NONE),
    ]
    efs = scorer.compute(mappings)
    assert efs == 0.0, f"Expected 0.0, got {efs}"
    print(f"  TEST 3 PASS — EFS all NONE: {efs}")


# ═══════════════════════════════════════════════════════════════════
# TEST 4: EFS Scorer — weighted fields
# ═══════════════════════════════════════════════════════════════════
def test_efs_weighted():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="critical", status=MappingStatus.FULL),
        FieldMapping(field="minor",    status=MappingStatus.NONE),
    ]
    # critical weight=3, minor weight=1 → (3*1.0 + 1*0.0) / 4 = 0.75
    efs = scorer.compute(mappings, field_weights={"critical": 3.0, "minor": 1.0})
    assert efs == 0.75, f"Expected 0.75, got {efs}"
    print(f"  TEST 4 PASS — EFS weighted: {efs}")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Field Mapper — NONE for missing fields
# ═══════════════════════════════════════════════════════════════════
def test_mapper_none():
    mapper = FieldMapper()
    fields = [make_field("unknown_field", "some value")]
    schema = {"known_field": {"type": "string"}}
    mappings = mapper.map_fields(fields, schema)
    assert mappings[0].status == MappingStatus.NONE
    print(f"  TEST 5 PASS — Mapper NONE for missing field")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: Field Mapper — FULL for exact match
# ═══════════════════════════════════════════════════════════════════
def test_mapper_full():
    mapper = FieldMapper()
    fields = [make_field("name", "Jane Smith", ftype="text")]
    schema = {"name": {"type": "string", "max_length": 255}}
    mappings = mapper.map_fields(fields, schema)
    assert mappings[0].status == MappingStatus.FULL
    print(f"  TEST 6 PASS — Mapper FULL for exact match")


# ═══════════════════════════════════════════════════════════════════
# TEST 7: Field Mapper — PARTIAL for array → non-array
# ═══════════════════════════════════════════════════════════════════
def test_mapper_partial_array():
    mapper = FieldMapper()
    fields = [make_field("icd10_codes", ["R07.9", "R07.4", "I20.9"], ftype="code_array")]
    schema = {"icd10_codes": {"type": "string", "array": False}}
    mappings = mapper.map_fields(fields, schema)
    assert mappings[0].status == MappingStatus.PARTIAL
    print(f"  TEST 7 PASS — Mapper PARTIAL for array→scalar")


# ═══════════════════════════════════════════════════════════════════
# TEST 8: Field Mapper — PARTIAL for structured → string
# ═══════════════════════════════════════════════════════════════════
def test_mapper_partial_structured():
    mapper = FieldMapper()
    fields = [make_field("budget", {"max_monthly": 650, "down_payment": 5000}, ftype="structured")]
    schema = {"budget": {"type": "string"}}
    mappings = mapper.map_fields(fields, schema)
    assert mappings[0].status == MappingStatus.PARTIAL
    print(f"  TEST 8 PASS — Mapper PARTIAL for structured→string")


# ═══════════════════════════════════════════════════════════════════
# TEST 9: Legacy Translator — array flattening
# ═══════════════════════════════════════════════════════════════════
def test_translator_array_flatten():
    translator = LegacyTranslator()
    fields = [make_field("allergies", ["penicillin", "sulfa"], ftype="text_array")]
    schema = {"allergies": {"type": "string", "array": False}}
    output = translator.translate(fields, schema)
    assert output["allergies"] == "penicillin, sulfa"
    print(f"  TEST 9 PASS — Translator array flatten: {output['allergies']}")


# ═══════════════════════════════════════════════════════════════════
# TEST 10: Legacy Translator — max_length truncation
# ═══════════════════════════════════════════════════════════════════
def test_translator_truncation():
    translator = LegacyTranslator()
    long_value = "A" * 600
    fields = [make_field("notes", long_value, ftype="text")]
    schema = {"notes": {"type": "string", "max_length": 500}}
    output = translator.translate(fields, schema)
    assert len(output["notes"]) == 500
    print(f"  TEST 10 PASS — Translator truncation to max_length=500")


# ═══════════════════════════════════════════════════════════════════
# TEST 11: Envelope Builder — snapshot (now includes digest)
# ═══════════════════════════════════════════════════════════════════
def test_envelope_snapshot():
    fields = [make_field("patient_name", "Jane Smith")]
    loss_report = LossReport(
        efs=1.0,
        field_mappings=[FieldMapping(field="patient_name", status=MappingStatus.FULL)]
    )
    envelope = EnvelopeBuilder.build_snapshot(
        domain="healthcare",
        source_system="test-ai",
        target_system="test-ehr",
        fields=fields,
        legacy_output={"patient_name": "Jane Smith"},
        loss_report=loss_report,
    )
    assert envelope.envelope_type == EnvelopeType.SNAPSHOT
    assert envelope.version == 1
    assert envelope.parent_envelope_id is None
    assert envelope.cord_version == "1.0"
    assert envelope.domain == "healthcare"
    assert envelope.x_cord_digest is not None
    assert envelope.x_cord_digest.startswith("sha256:")
    print(f"  TEST 11 PASS — Snapshot with digest: {envelope.x_cord_digest[:30]}...")


# ═══════════════════════════════════════════════════════════════════
# TEST 12: Envelope Builder — delta (now includes digest)
# ═══════════════════════════════════════════════════════════════════
def test_envelope_delta():
    loss_report = LossReport(
        efs=1.0,
        field_mappings=[FieldMapping(field="pain_score", status=MappingStatus.FULL)]
    )
    parent_id = "a3f9c201-7d42-4b1a-9e0f-2c88d3f5ab01"
    delta = EnvelopeBuilder.build_delta(
        parent_envelope_id=parent_id,
        parent_version=1,
        domain="healthcare",
        source_system="test-ai",
        target_system="test-ehr",
        changed_fields=[make_field("pain_score", 9, ftype="integer")],
        legacy_output={"pain_score": 9},
        loss_report=loss_report,
    )
    assert delta.envelope_type == EnvelopeType.DELTA
    assert delta.version == 2
    assert delta.parent_envelope_id == parent_id
    assert delta.x_cord_digest is not None
    print(f"  TEST 12 PASS — Delta with digest: v{delta.version}, parent={parent_id[:8]}...")


# ═══════════════════════════════════════════════════════════════════
# TEST 13: Envelope Validator — valid envelope
# ═══════════════════════════════════════════════════════════════════
def test_validator_valid():
    validator = EnvelopeValidator()
    fields = [make_field("name", "Jane")]
    loss_report = LossReport(
        efs=1.0,
        field_mappings=[FieldMapping(field="name", status=MappingStatus.FULL)]
    )
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Jane"},
        loss_report=loss_report,
    )
    errors = validator.validate(envelope.dict())
    assert len(errors) == 0, f"Valid envelope had errors: {errors}"
    print(f"  TEST 13 PASS — Validator accepts valid envelope (with digest)")


# ═══════════════════════════════════════════════════════════════════
# TEST 14: Envelope Validator — missing fields
# ═══════════════════════════════════════════════════════════════════
def test_validator_missing_fields():
    validator = EnvelopeValidator()
    bad_envelope = {"cord_version": "1.0", "envelope_type": "snapshot"}
    errors = validator.validate(bad_envelope)
    assert len(errors) > 0
    print(f"  TEST 14 PASS — Validator caught {len(errors)} errors in invalid envelope")


# ═══════════════════════════════════════════════════════════════════
# TEST 15: Envelope Validator — delta without parent fails
# ═══════════════════════════════════════════════════════════════════
def test_validator_delta_no_parent():
    validator = EnvelopeValidator()
    bad_delta = {
        "cord_version": "1.0",
        "envelope_id": "abc",
        "envelope_type": "delta",
        "version": 2,
        "parent_envelope_id": None,
        "created_at": "2025-09-14T10:22:00Z",
        "domain": "healthcare",
        "source_system": "s",
        "target_system": "t",
        "fields": [],
        "legacy_output": {},
        "loss_report": {"efs": 1.0, "field_mappings": []},
    }
    errors = validator.validate(bad_delta)
    assert any("parent_envelope_id" in e for e in errors)
    print(f"  TEST 15 PASS — Validator caught delta without parent_envelope_id")


# ═══════════════════════════════════════════════════════════════════
# TEST 16: Version Chain — materialization
# ═══════════════════════════════════════════════════════════════════
def test_version_chain():
    loss_report = LossReport(efs=1.0, field_mappings=[])

    snapshot = EnvelopeBuilder.build_snapshot(
        domain="healthcare", source_system="ai", target_system="ehr",
        fields=[
            make_field("pain_score", 7, ftype="integer"),
            make_field("name", "Jane Smith"),
        ],
        legacy_output={}, loss_report=loss_report,
    )

    delta = EnvelopeBuilder.build_delta(
        parent_envelope_id=snapshot.envelope_id,
        parent_version=snapshot.version,
        domain="healthcare", source_system="ai", target_system="ehr",
        changed_fields=[make_field("pain_score", 9, ftype="integer")],
        legacy_output={}, loss_report=loss_report,
    )

    chain = VersionChain()
    chain.add(snapshot)
    chain.add(delta)

    state = chain.materialize()
    assert state["pain_score"].value == 9
    assert state["name"].value == "Jane Smith"
    print(f"  TEST 16 PASS — Version chain materialization: pain_score={state['pain_score'].value}")


# ═══════════════════════════════════════════════════════════════════
# TEST 17: Healthcare adapter — EFS matches expected (UPDATED: 0.5)
# ═══════════════════════════════════════════════════════════════════
def test_healthcare_adapter_efs():
    adapter = HealthcareEHRAdapter()
    mapper = FieldMapper()
    scorer = EFSScorer()

    fields = [
        make_field("chief_complaint", "chest pain, onset 3h, left arm radiation", ftype="text"),
        make_field("icd10_codes", ["R07.9", "R07.4", "I20.9"], ftype="code_array"),
        make_field("pain_score", 7, ftype="integer"),
        make_field("allergy_list", ["penicillin", "sulfa"], ftype="text_array"),
    ]

    mappings = mapper.map_fields(fields, adapter.target_schema)
    efs = scorer.compute(mappings, adapter.field_weights)

    assert 0.0 < efs < 1.0
    print(f"  TEST 17 PASS — Healthcare adapter EFS: {efs}")


# ═══════════════════════════════════════════════════════════════════
# TEST 18: Event logger
# ═══════════════════════════════════════════════════════════════════
def test_event_logger():
    logger = EventLogger()
    logger.utterance("patient", "I have chest pain")
    logger.classification("intake-ai", "icd10_codes")
    logger.utterance("patient", "It started 3 hours ago")

    entries = logger.entries()
    assert len(entries) == 3
    assert entries[0].event_type == "utterance"
    assert entries[1].event_type == "classification"
    assert entries[1].field == "icd10_codes"
    print(f"  TEST 18 PASS — Event logger: {len(entries)} entries")


# ═══════════════════════════════════════════════════════════════════
# TEST 19: Adapter registry
# ═══════════════════════════════════════════════════════════════════
def test_adapter_registry():
    for domain in ["healthcare", "automotive", "real_estate", "hr", "generic"]:
        adapter = get_adapter(domain)
        assert adapter.target_schema
        assert adapter.domain == domain
    print(f"  TEST 19 PASS — All adapters registered and return schemas")


# ═══════════════════════════════════════════════════════════════════
# TEST 20: Full end-to-end — automotive
# ═══════════════════════════════════════════════════════════════════
def test_e2e_automotive():
    adapter = AutomotiveDMSAdapter()
    mapper = FieldMapper()
    translator = LegacyTranslator()
    scorer = EFSScorer()

    fields = [
        make_field("vehicle_interest", {"make": "Toyota", "model": "Camry", "year": 2025, "trim": "XSE"}, ftype="structured"),
        make_field("budget", {"max_monthly": 650, "down_payment": 5000}, ftype="structured"),
        make_field("trade_in", {"make": "Honda", "model": "Civic", "year": 2019, "mileage": 48200}, ftype="structured"),
        make_field("purchase_timeline", "within 2 weeks", ftype="text"),
        make_field("intent_signals", ["ready_to_buy", "financing_needed"], ftype="code_array"),
    ]

    mappings = mapper.map_fields(fields, adapter.target_schema)
    legacy_output = translator.translate(fields, adapter.target_schema)
    loss_report = scorer.build_loss_report(mappings, adapter.field_weights)

    envelope = EnvelopeBuilder.build_snapshot(
        domain="automotive",
        source_system="sales-ai-v3",
        target_system="dealer-dms",
        fields=fields,
        legacy_output=legacy_output,
        loss_report=loss_report,
    )

    assert envelope.cord_version == "1.0"
    assert envelope.domain == "automotive"
    assert 0.0 <= envelope.loss_report.efs <= 1.0
    assert len(envelope.loss_report.field_mappings) == len(fields)
    assert isinstance(envelope.legacy_output, dict)
    assert envelope.x_cord_digest is not None

    print(f"  TEST 20 PASS — E2E automotive: EFS={envelope.loss_report.efs} | "
          f"digest present | legacy_output fields={list(envelope.legacy_output.keys())}")


# ═══════════════════════════════════════════════════════════════════
# TEST 21: PARTIAL coefficient floor enforcement
# ═══════════════════════════════════════════════════════════════════
def test_partial_floor_enforcement():
    """CORD v1.0 RFC: PARTIAL coefficient MUST NOT go below 0.5"""
    try:
        EFSScorer(partial_coefficient=0.3)
        assert False, "Should have raised ValueError for coefficient below 0.5"
    except ValueError as e:
        assert "0.5" in str(e)
    print(f"  TEST 21 PASS — PARTIAL floor enforced: coefficient < 0.5 raises ValueError")


# ═══════════════════════════════════════════════════════════════════
# TEST 22: PARTIAL coefficient ceiling enforcement
# ═══════════════════════════════════════════════════════════════════
def test_partial_ceiling_enforcement():
    """CORD v1.0 RFC: PARTIAL coefficient must be <= 0.9"""
    try:
        EFSScorer(partial_coefficient=0.95)
        assert False, "Should have raised ValueError for coefficient above 0.9"
    except ValueError as e:
        assert "0.9" in str(e)
    print(f"  TEST 22 PASS — PARTIAL ceiling enforced: coefficient > 0.9 raises ValueError")


# ═══════════════════════════════════════════════════════════════════
# TEST 23: SHA-256 digest computation
# ═══════════════════════════════════════════════════════════════════
def test_digest_computation():
    fields = [make_field("name", "Test")]
    loss_report = LossReport(efs=1.0, field_mappings=[])
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Test"},
        loss_report=loss_report,
    )

    assert envelope.x_cord_digest is not None
    assert envelope.x_cord_digest.startswith("sha256:")
    assert len(envelope.x_cord_digest) == 71  # "sha256:" + 64 hex chars

    print(f"  TEST 23 PASS — SHA-256 digest: {envelope.x_cord_digest[:30]}...")


# ═══════════════════════════════════════════════════════════════════
# TEST 24: Digest verification — valid envelope
# ═══════════════════════════════════════════════════════════════════
def test_digest_verification_valid():
    fields = [make_field("name", "Test")]
    loss_report = LossReport(efs=1.0, field_mappings=[])
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Test"},
        loss_report=loss_report,
    )

    envelope_dict = envelope.dict()
    assert verify_digest(envelope_dict) == True
    print(f"  TEST 24 PASS — Digest verification: valid envelope passes")


# ═══════════════════════════════════════════════════════════════════
# TEST 25: Digest verification — tampered envelope
# ═══════════════════════════════════════════════════════════════════
def test_digest_verification_tampered():
    fields = [make_field("name", "Test")]
    loss_report = LossReport(efs=1.0, field_mappings=[])
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Test"},
        loss_report=loss_report,
    )

    # Tamper with the envelope
    envelope_dict = envelope.dict()
    envelope_dict["domain"] = "TAMPERED"
    assert verify_digest(envelope_dict) == False
    print(f"  TEST 25 PASS — Digest verification: tampered envelope detected")


# ═══════════════════════════════════════════════════════════════════
# TEST 26: Validator catches tampered digest
# ═══════════════════════════════════════════════════════════════════
def test_validator_catches_tamper():
    validator = EnvelopeValidator()
    fields = [make_field("name", "Test")]
    loss_report = LossReport(efs=1.0, field_mappings=[
        FieldMapping(field="name", status=MappingStatus.FULL)
    ])
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Test"},
        loss_report=loss_report,
    )

    envelope_dict = envelope.dict()
    envelope_dict["domain"] = "TAMPERED"
    errors = validator.validate(envelope_dict)
    assert any("integrity" in e.lower() or "tamper" in e.lower() for e in errors)
    print(f"  TEST 26 PASS — Validator catches tampered digest")


# ═══════════════════════════════════════════════════════════════════
# TEST 27: Replay protection — duplicate rejection
# ═══════════════════════════════════════════════════════════════════
def test_replay_duplicate():
    rp = ReplayProtector(staleness_seconds=3600)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat() + "Z"

    # First submission — accepted
    errors = rp.check("envelope-001", now)
    assert len(errors) == 0

    # Replay — rejected
    errors = rp.check("envelope-001", now)
    assert len(errors) > 0
    assert any("already been ingested" in e for e in errors)
    print(f"  TEST 27 PASS — Replay protection: duplicate envelope_id rejected")


# ═══════════════════════════════════════════════════════════════════
# TEST 28: Replay protection — staleness rejection
# ═══════════════════════════════════════════════════════════════════
def test_replay_staleness():
    rp = ReplayProtector(staleness_seconds=60)  # 60 second threshold

    # Old timestamp — rejected
    old_ts = "2020-01-01T00:00:00Z"
    errors = rp.check("envelope-stale", old_ts)
    assert len(errors) > 0
    assert any("staleness" in e.lower() for e in errors)
    print(f"  TEST 28 PASS — Replay protection: stale envelope rejected")


# ═══════════════════════════════════════════════════════════════════
# TEST 29: Confidence → PARTIAL propagation — low confidence
# ═══════════════════════════════════════════════════════════════════
def test_confidence_propagation_low():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="symptoms", status=MappingStatus.PARTIAL),
    ]
    # Low confidence → coefficient should be at floor (0.5)
    efs = scorer.compute(mappings, confidence_map={"symptoms": 0.3})
    assert efs == 0.5, f"Expected 0.5 (floor), got {efs}"
    assert mappings[0].partial_coefficient == PARTIAL_FLOOR
    print(f"  TEST 29 PASS — Low confidence → PARTIAL coefficient at floor: {mappings[0].partial_coefficient}")


# ═══════════════════════════════════════════════════════════════════
# TEST 30: Confidence → PARTIAL propagation — high confidence
# ═══════════════════════════════════════════════════════════════════
def test_confidence_propagation_high():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="diagnosis", status=MappingStatus.PARTIAL),
    ]
    # High confidence → coefficient should be at ceiling (0.9)
    efs = scorer.compute(mappings, confidence_map={"diagnosis": 0.98})
    assert efs == 0.9, f"Expected 0.9 (ceiling), got {efs}"
    assert mappings[0].partial_coefficient == PARTIAL_CEILING
    print(f"  TEST 30 PASS — High confidence → PARTIAL coefficient at ceiling: {mappings[0].partial_coefficient}")


# ═══════════════════════════════════════════════════════════════════
# TEST 31: Confidence → PARTIAL propagation — mid confidence
# ═══════════════════════════════════════════════════════════════════
def test_confidence_propagation_mid():
    scorer = EFSScorer(confidence_low_threshold=0.5, confidence_high_threshold=0.95)
    mappings = [
        FieldMapping(field="notes", status=MappingStatus.PARTIAL),
    ]
    # Mid confidence (0.725 = halfway between 0.5 and 0.95)
    efs = scorer.compute(mappings, confidence_map={"notes": 0.725})
    # t = (0.725 - 0.5) / (0.95 - 0.5) = 0.225 / 0.45 = 0.5
    # coefficient = 0.5 + 0.5 * 0.4 = 0.7
    assert mappings[0].partial_coefficient == 0.7, f"Expected 0.7, got {mappings[0].partial_coefficient}"
    assert efs == 0.7, f"Expected 0.7, got {efs}"
    print(f"  TEST 31 PASS — Mid confidence → interpolated coefficient: {mappings[0].partial_coefficient}")


# ═══════════════════════════════════════════════════════════════════
# TEST 32: Partial coefficient auditability on FieldMapping
# ═══════════════════════════════════════════════════════════════════
def test_partial_coefficient_auditability():
    scorer = EFSScorer()
    mappings = [
        FieldMapping(field="a", status=MappingStatus.FULL),
        FieldMapping(field="b", status=MappingStatus.PARTIAL),
        FieldMapping(field="c", status=MappingStatus.NONE),
    ]
    scorer.compute(mappings, confidence_map={"b": 0.8})

    # FULL and NONE should not have partial_coefficient set by scorer
    assert mappings[0].partial_coefficient is None
    # PARTIAL should have the resolved coefficient
    assert mappings[1].partial_coefficient is not None
    assert PARTIAL_FLOOR <= mappings[1].partial_coefficient <= PARTIAL_CEILING
    assert mappings[2].partial_coefficient is None
    print(f"  TEST 32 PASS — Partial coefficient auditable: b={mappings[1].partial_coefficient}")


# ═══════════════════════════════════════════════════════════════════
# TEST 33: Conformance — CORD-Compliant tier (Claims 15-16)
# ═══════════════════════════════════════════════════════════════════
def test_conformance_compliant():
    cv = ConformanceValidator()

    from event_log.logger import EventLogger
    el = EventLogger()
    el.utterance("patient", "I have chest pain")

    fields = [make_field("name", "Jane")]
    loss_report = LossReport(
        efs=1.0,
        field_mappings=[FieldMapping(
            field="name", status=MappingStatus.FULL,
            note="Fully mapped to target"
        )]
    )
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Jane"},
        loss_report=loss_report, event_log=el.entries(),
    )

    report = cv.assess(envelope.dict())
    assert report.tier == ConformanceTier.COMPLIANT
    assert all(c.passed for c in report.categories)
    print(f"  TEST 33 PASS — Conformance: {report.tier.value} (3/3 categories)")


# ═══════════════════════════════════════════════════════════════════
# TEST 34: Conformance — CORD-Partial tier (no event log or notes)
# ═══════════════════════════════════════════════════════════════════
def test_conformance_partial():
    cv = ConformanceValidator()

    fields = [make_field("name", "Jane")]
    loss_report = LossReport(
        efs=1.0,
        field_mappings=[FieldMapping(field="name", status=MappingStatus.FULL)]
        # No notes on mappings
    )
    envelope = EnvelopeBuilder.build_snapshot(
        domain="test", source_system="ai", target_system="crm",
        fields=fields, legacy_output={"name": "Jane"},
        loss_report=loss_report,
        # No event_log
    )

    report = cv.assess(envelope.dict())
    assert report.tier == ConformanceTier.PARTIAL
    print(f"  TEST 34 PASS — Conformance: {report.tier.value} (missing event_log/notes)")


# ═══════════════════════════════════════════════════════════════════
# TEST 35: Conformance — Non-Compliant
# ═══════════════════════════════════════════════════════════════════
def test_conformance_non_compliant():
    cv = ConformanceValidator()
    report = cv.assess({"random": "garbage"})
    assert report.tier == ConformanceTier.NON_COMPLIANT
    print(f"  TEST 35 PASS — Conformance: {report.tier.value} for invalid input")


# ═══════════════════════════════════════════════════════════════════
# RUN ALL
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    tests = [
        test_efs_basic,
        test_efs_all_full,
        test_efs_all_none,
        test_efs_weighted,
        test_mapper_none,
        test_mapper_full,
        test_mapper_partial_array,
        test_mapper_partial_structured,
        test_translator_array_flatten,
        test_translator_truncation,
        test_envelope_snapshot,
        test_envelope_delta,
        test_validator_valid,
        test_validator_missing_fields,
        test_validator_delta_no_parent,
        test_version_chain,
        test_healthcare_adapter_efs,
        test_event_logger,
        test_adapter_registry,
        test_e2e_automotive,
        test_partial_floor_enforcement,
        test_partial_ceiling_enforcement,
        test_digest_computation,
        test_digest_verification_valid,
        test_digest_verification_tampered,
        test_validator_catches_tamper,
        test_replay_duplicate,
        test_replay_staleness,
        test_confidence_propagation_low,
        test_confidence_propagation_high,
        test_confidence_propagation_mid,
        test_partial_coefficient_auditability,
        test_conformance_compliant,
        test_conformance_partial,
        test_conformance_non_compliant,
    ]

    print("\n═══ CORD Engine v1.1 — Test Suite ═══\n")
    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL — {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n═══ Results: {passed}/{len(tests)} passed", "✓" if failed == 0 else f"| {failed} failed ✗")
    sys.exit(0 if failed == 0 else 1)
