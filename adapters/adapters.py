"""
CORD Engine — Domain Adapters
Pre-built target schema definitions for common legacy system types.

Each adapter defines:
  - target_schema: the legacy system's field definitions
  - field_weights: domain-specific EFS weight overrides

Any system can define its own adapter by following the same pattern.
These are reference implementations — not exhaustive production schemas.
"""

from __future__ import annotations
from typing import Any, Dict, Optional


class BaseAdapter:
    """
    Abstract base for all CORD domain adapters.
    An adapter defines a target system's schema and optional field weights.
    """
    domain: str = "generic"
    target_system: str = "legacy-system"

    @property
    def target_schema(self) -> Dict[str, Any]:
        raise NotImplementedError

    @property
    def field_weights(self) -> Optional[Dict[str, float]]:
        return None


# ── Generic Flat Schema Adapter ───────────────────────────────────────────────

class GenericFlatAdapter(BaseAdapter):
    """
    Generic adapter for flat-schema legacy systems.
    Accepts common field names as plain strings.
    Use this as a starting point for custom adapters.
    """
    domain = "generic"
    target_system = "generic-legacy"

    @property
    def target_schema(self) -> Dict[str, Any]:
        return {
            "name":         {"type": "string", "max_length": 255},
            "email":        {"type": "string", "max_length": 255},
            "phone":        {"type": "string", "max_length": 20},
            "notes":        {"type": "text",   "max_length": 2000},
            "status":       {"type": "string", "max_length": 50},
            "created_at":   {"type": "string", "max_length": 50},
            "source":       {"type": "string", "max_length": 100},
        }


# ── Healthcare — EHR Adapter ──────────────────────────────────────────────────

class HealthcareEHRAdapter(BaseAdapter):
    """
    Adapter for legacy EHR systems (Epic, Cerner, etc.)
    Models a constrained flat-schema patient record.
    """
    domain = "healthcare"
    target_system = "ehr-legacy"

    @property
    def target_schema(self) -> Dict[str, Any]:
        return {
            # Demographics
            "patient_name":       {"type": "string",  "max_length": 255},
            "date_of_birth":      {"type": "string",  "max_length": 20},
            "mrn":                {"type": "string",  "max_length": 50},

            # Clinical
            "chief_complaint":    {"type": "text",    "max_length": 500},
            "icd10_primary":      {"type": "string",  "max_length": 10},
            "pain_score":         {"type": "string",  "max_length": 5},
            "allergies":          {"type": "text",    "max_length": 500},
            "medications":        {"type": "text",    "max_length": 1000},
            "vitals_bp":          {"type": "string",  "max_length": 20},
            "vitals_hr":          {"type": "integer"},
            "vitals_temp":        {"type": "float"},

            # Admin
            "insurance":          {"type": "string",  "max_length": 5},
            "insurance_id":       {"type": "string",  "max_length": 50},
            "provider_id":        {"type": "string",  "max_length": 50},
            "visit_type":         {"type": "string",  "max_length": 50},
        }

    @property
    def field_weights(self) -> Dict[str, float]:
        # Clinical fields weighted higher than administrative
        return {
            "chief_complaint":  2.0,
            "icd10_primary":    2.0,
            "pain_score":       1.5,
            "allergies":        2.0,
            "medications":      2.0,
            "vitals_bp":        1.5,
            "vitals_hr":        1.5,
            "patient_name":     1.0,
            "insurance":        0.5,
        }


# ── Automotive — DMS Adapter ─────────────────────────────────────────────────

class AutomotiveDMSAdapter(BaseAdapter):
    """
    Adapter for legacy DMS systems (CDK, Reynolds & Reynolds, Dealertrack, etc.)
    Models a flat lead record schema.
    """
    domain = "automotive"
    target_system = "dms-legacy"

    @property
    def target_schema(self) -> Dict[str, Any]:
        return {
            # Lead contact
            "first_name":           {"type": "string",  "max_length": 100},
            "last_name":            {"type": "string",  "max_length": 100},
            "email":                {"type": "string",  "max_length": 255},
            "phone":                {"type": "string",  "max_length": 20},

            # Vehicle interest
            "vehicle_interest":     {"type": "string",  "max_length": 255},
            "vehicle_make":         {"type": "string",  "max_length": 50},
            "vehicle_model":        {"type": "string",  "max_length": 50},
            "vehicle_year":         {"type": "integer"},
            "vehicle_trim":         {"type": "string",  "max_length": 50},

            # Budget
            "monthly_budget":       {"type": "float"},
            "purchase_timeline":    {"type": "string",  "max_length": 100},

            # Trade-in
            "trade_make":           {"type": "string",  "max_length": 50},
            "trade_model":          {"type": "string",  "max_length": 50},
            "trade_year":           {"type": "integer"},
            "trade_mileage":        {"type": "integer"},

            # Lead metadata
            "lead_source":          {"type": "string",  "max_length": 50},
            "salesperson_id":       {"type": "string",  "max_length": 50},
            "notes":                {"type": "text",    "max_length": 2000},
        }

    @property
    def field_weights(self) -> Dict[str, float]:
        return {
            "vehicle_interest":  2.0,
            "vehicle_make":      1.5,
            "vehicle_model":     1.5,
            "monthly_budget":    1.5,
            "purchase_timeline": 1.5,
            "trade_make":        1.0,
            "trade_model":       1.0,
            "phone":             1.0,
            "email":             1.0,
        }


# ── Real Estate — MLS Adapter ────────────────────────────────────────────────

class RealEstateMLSAdapter(BaseAdapter):
    """
    Adapter for legacy MLS systems.
    Models a flat property listing record.
    """
    domain = "real_estate"
    target_system = "mls-legacy"

    @property
    def target_schema(self) -> Dict[str, Any]:
        return {
            # Property
            "list_price":           {"type": "integer"},
            "address":              {"type": "string",  "max_length": 255},
            "bedrooms":             {"type": "integer"},
            "bathrooms":            {"type": "float"},
            "sqft":                 {"type": "integer"},
            "lot_size":             {"type": "string",  "max_length": 50},
            "year_built":           {"type": "integer"},
            "remarks":              {"type": "text",    "max_length": 2000},

            # Listing
            "listing_agent_id":     {"type": "string",  "max_length": 50},
            "listing_date":         {"type": "string",  "max_length": 20},
            "status":               {"type": "string",  "max_length": 20},
            "showing_instructions": {"type": "text",    "max_length": 500},

            # Contact
            "seller_name":          {"type": "string",  "max_length": 255},
            "seller_phone":         {"type": "string",  "max_length": 20},
            "seller_email":         {"type": "string",  "max_length": 255},
        }

    @property
    def field_weights(self) -> Dict[str, float]:
        return {
            "list_price":    2.0,
            "address":       2.0,
            "bedrooms":      1.5,
            "bathrooms":     1.5,
            "sqft":          1.5,
            "remarks":       1.0,
            "seller_name":   1.0,
            "seller_phone":  1.0,
        }


# ── HR / Recruiting — ATS Adapter ────────────────────────────────────────────

class HRATSAdapter(BaseAdapter):
    """
    Adapter for legacy ATS systems (Greenhouse, Lever, Taleo, Workday, etc.)
    Models a flat candidate record with text-blob fields.
    """
    domain = "hr"
    target_system = "ats-legacy"

    @property
    def target_schema(self) -> Dict[str, Any]:
        return {
            # Candidate
            "first_name":           {"type": "string",  "max_length": 100},
            "last_name":            {"type": "string",  "max_length": 100},
            "email":                {"type": "string",  "max_length": 255},
            "phone":                {"type": "string",  "max_length": 20},
            "linkedin_url":         {"type": "string",  "max_length": 255},

            # Screening
            "skills_text":          {"type": "text",    "max_length": 1000},
            "salary_min":           {"type": "integer"},
            "salary_max":           {"type": "integer"},
            "availability":         {"type": "string",  "max_length": 100},
            "visa_status":          {"type": "string",  "max_length": 50},
            "years_experience":     {"type": "integer"},

            # Metadata
            "source":               {"type": "string",  "max_length": 50},
            "recruiter_notes":      {"type": "text",    "max_length": 2000},
            "stage":                {"type": "string",  "max_length": 50},
            "requisition_id":       {"type": "string",  "max_length": 50},
        }

    @property
    def field_weights(self) -> Dict[str, float]:
        return {
            "skills_text":       2.0,
            "salary_min":        1.5,
            "salary_max":        1.5,
            "availability":      1.5,
            "visa_status":       2.0,
            "years_experience":  1.5,
            "email":             1.0,
            "phone":             1.0,
        }


# ── Adapter Registry ──────────────────────────────────────────────────────────

ADAPTER_REGISTRY: Dict[str, type] = {
    "generic":      GenericFlatAdapter,
    "healthcare":   HealthcareEHRAdapter,
    "automotive":   AutomotiveDMSAdapter,
    "real_estate":  RealEstateMLSAdapter,
    "hr":           HRATSAdapter,
}


def get_adapter(domain: str) -> BaseAdapter:
    """
    Return the adapter for a given domain.
    Falls back to GenericFlatAdapter if domain is not registered.
    """
    adapter_class = ADAPTER_REGISTRY.get(domain.lower(), GenericFlatAdapter)
    return adapter_class()
