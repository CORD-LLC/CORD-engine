# CORD Engine

**The reference implementation of the CORD v1.0 specification.**

[![Spec](https://img.shields.io/badge/spec-v1.0-2563eb)](https://cordspec.org)
[![Tests](https://img.shields.io/badge/tests-35%2F35-16a34a)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()

This engine is one implementation of the [CORD specification](https://cordspec.org). The spec is the standard. Any system can implement CORD independently. This engine is not the only valid implementation.

## What's in the box

| Module | Purpose |
|---|---|
| `api/main.py` | FastAPI app — `/translate`, `/validate`, `/conformance`, `/score`, `/replay-check`, `/verify-digest`, `/health`, `/adapters` |
| `api/models.py` | Pydantic schemas for the full CORD v1.0 spec |
| `envelope/builder.py` | Snapshot and delta envelope construction with SHA-256 digest |
| `envelope/versioning.py` | Version chain materialization |
| `efs/scorer.py` | EFS computation with confidence-based PARTIAL propagation |
| `translation/mapper.py` | Field mapping (FULL/PARTIAL/NONE) and legacy translation |
| `conformance/__init__.py` | Three-category conformance validation and four-tier classification |
| `adapters/adapters.py` | Domain adapters (healthcare, automotive, real estate, HR, generic) |
| `event_log/logger.py` | Typed event logging |
| `tests/test_engine.py` | 35 tests covering all components |

## Features

- **Envelope Fidelity Score (EFS)** — PARTIAL coefficient in [0.5, 0.9] with 0.5 baseline floor enforced
- **Confidence propagation** — AI confidence scores drive PARTIAL coefficient selection via linear interpolation
- **Auditable coefficients** — `partial_coefficient` recorded on every PARTIAL mapping entry
- **SHA-256 envelope integrity** — `x_cord_digest` computed and attached on every envelope build
- **Tamper detection** — `verify_digest()` recomputes and compares
- **Replay protection** — `ReplayProtector` validates envelope_id uniqueness and created_at staleness
- **Conformance validation** — three-category assessment (structure, EFS, mapping completeness) with four-tier classification
- **Domain adapters** — pluggable target schemas for healthcare, automotive, real estate, HR

## Quick start

```bash
# Clone
git clone https://github.com/CORD-LLC/cord-engine.git
cd cord-engine

# Install
pip install -r requirements.txt

# Test
python tests/test_engine.py

# Run
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

API docs at `http://localhost:8000/docs`.

## Docker

```bash
docker-compose up
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/translate` | Translate AI fields → CORD envelope with EFS |
| POST | `/validate` | Validate envelope against v1.0 spec |
| POST | `/conformance` | Run three-category conformance assessment |
| POST | `/score` | Compute EFS from pre-existing mappings |
| POST | `/replay-check` | Check envelope for replay attacks |
| POST | `/verify-digest` | Verify SHA-256 envelope integrity |
| GET | `/health` | Health check |
| GET | `/adapters` | List available domain adapters |

## Tests

```
═══ CORD Engine v1.1 — Test Suite ═══

  TEST 1  — EFS basic: 0.5 (FULL=1.0, PARTIAL=0.5, NONE=0.0)
  TEST 2  — EFS all FULL: 1.0
  TEST 3  — EFS all NONE: 0.0
  TEST 4  — EFS weighted: 0.75
  TEST 5  — Mapper NONE for missing field
  TEST 6  — Mapper FULL for exact match
  TEST 7  — Mapper PARTIAL for array→scalar
  TEST 8  — Mapper PARTIAL for structured→string
  TEST 9  — Translator array flatten
  TEST 10 — Translator truncation to max_length
  TEST 11 — Snapshot with SHA-256 digest
  TEST 12 — Delta with SHA-256 digest
  TEST 13 — Validator accepts valid envelope
  TEST 14 — Validator catches invalid envelope
  TEST 15 — Validator catches delta without parent
  TEST 16 — Version chain materialization
  TEST 17 — Healthcare adapter EFS
  TEST 18 — Event logger
  TEST 19 — All adapters registered
  TEST 20 — E2E automotive with digest
  TEST 21 — PARTIAL floor enforced (< 0.5 raises ValueError)
  TEST 22 — PARTIAL ceiling enforced (> 0.9 raises ValueError)
  TEST 23 — SHA-256 digest computation
  TEST 24 — Digest verification: valid
  TEST 25 — Digest verification: tampered
  TEST 26 — Validator catches tampered digest
  TEST 27 — Replay protection: duplicate rejected
  TEST 28 — Replay protection: stale rejected
  TEST 29 — Confidence → PARTIAL at floor (0.5)
  TEST 30 — Confidence → PARTIAL at ceiling (0.9)
  TEST 31 — Confidence → PARTIAL interpolated (0.7)
  TEST 32 — Partial coefficient auditability
  TEST 33 — Conformance: CORD-Compliant
  TEST 34 — Conformance: CORD-Partial
  TEST 35 — Conformance: Non-Compliant

═══ Results: 35/35 passed ✓
```

## Relationship to the CORD specification

This engine implements the [CORD v1.0 specification](https://cordspec.org). The spec is the standard. This engine is one implementation of it. Any other system can implement CORD independently using the spec. This engine is not the only valid implementation.

## License

Apache 2.0 — see [LICENSE](LICENSE).
