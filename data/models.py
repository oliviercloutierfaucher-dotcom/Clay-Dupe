"""All Pydantic v2 data models."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.settings import ProviderName


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VerificationStatus(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    RISKY = "risky"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class EnrichmentType(str, Enum):
    EMAIL = "email"
    DOMAIN = "domain"
    LINKEDIN = "linkedin"
    PHONE = "phone"
    COMPANY = "company"


class CampaignStatus(str, Enum):
    CREATED = "created"
    MAPPING = "mapping"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RouteCategory(str, Enum):
    NAME_AND_DOMAIN = "name_and_domain"
    NAME_AND_COMPANY = "name_and_company"
    LINKEDIN_PERSON = "linkedin_person"
    EMAIL_ONLY = "email_only"
    COMPANY_ONLY = "company_only"
    DOMAIN_ONLY = "domain_only"
    NAME_ONLY = "name_only"
    UNROUTABLE = "unroutable"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class Company(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    industry_tags: list[str] = Field(default_factory=list)
    employee_count: Optional[int] = None
    employee_range: Optional[str] = None
    revenue_usd: Optional[Decimal] = None
    ebitda_usd: Optional[Decimal] = None
    founded_year: Optional[int] = None
    description: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    full_address: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    phone: Optional[str] = None
    source_provider: Optional[ProviderName] = None
    apollo_id: Optional[str] = None
    source_type: Optional[str] = None  # "apollo_search", "csv_import", "manual"
    icp_score: Optional[int] = None    # 0-100
    status: str = "new"                # "new", "contacted", "skipped"
    sf_account_id: Optional[str] = None
    sf_status: Optional[str] = None      # "in_sf" or None
    sf_instance_url: Optional[str] = None
    enriched_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @field_validator("domain", mode="before")
    @classmethod
    def normalize_domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        for prefix in ("https://", "http://"):
            if v.startswith(prefix):
                v = v[len(prefix):]
        if v.startswith("www."):
            v = v[4:]
        v = v.rstrip("/")
        return v

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        mapping = {
            "united states": "US",
            "united states of america": "US",
            "usa": "US",
            "us": "US",
            "gb": "UK",
            "great britain": "UK",
            "united kingdom": "UK",
            "england": "UK",
            "canada": "CA",
            "ca": "CA",
            "australia": "AU",
            "au": "AU",
            "germany": "DE",
            "de": "DE",
            "france": "FR",
            "fr": "FR",
        }
        normalized = v.strip().lower()
        return mapping.get(normalized, v.strip())


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------

class Person(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    company_id: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    email: Optional[str] = None
    email_status: VerificationStatus = VerificationStatus.UNKNOWN
    personal_email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    source_provider: Optional[ProviderName] = None
    apollo_id: Optional[str] = None
    enriched_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def build_full_name(self) -> "Person":
        if not self.full_name and (self.first_name or self.last_name):
            parts = [p for p in (self.first_name, self.last_name) if p]
            self.full_name = " ".join(parts)
        return self

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.strip().lower()

    @field_validator("linkedin_url", mode="before")
    @classmethod
    def normalize_linkedin_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith("https://"):
            if v.startswith("http://"):
                v = "https://" + v[7:]
            elif not v.startswith("https://"):
                v = "https://" + v
        return v


# ---------------------------------------------------------------------------
# EnrichmentResult
# ---------------------------------------------------------------------------

class EnrichmentResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    person_id: Optional[str] = None
    company_id: Optional[str] = None
    campaign_id: Optional[str] = None
    enrichment_type: EnrichmentType
    query_input: dict = Field(default_factory=dict)
    source_provider: ProviderName
    result_data: dict = Field(default_factory=dict)
    found: bool = False
    confidence_score: float = Field(default=0.0, ge=0, le=100)
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    cost_credits: float = 0.0
    cost_usd: Optional[float] = None
    response_time_ms: Optional[int] = None
    found_at: datetime = Field(default_factory=_utcnow)
    waterfall_position: Optional[int] = None
    from_cache: bool = False


# ---------------------------------------------------------------------------
# Campaign
# ---------------------------------------------------------------------------

class Campaign(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(default_factory=_new_uuid)
    name: str
    description: Optional[str] = None
    input_file: Optional[str] = None
    input_row_count: int = 0
    enrichment_types: list[EnrichmentType] = Field(default_factory=list)
    waterfall_order: list[ProviderName] = Field(default_factory=list)
    column_mapping: dict[str, str] = Field(default_factory=dict)
    status: CampaignStatus = CampaignStatus.CREATED
    total_rows: int = 0
    enriched_rows: int = 0
    found_rows: int = 0
    failed_rows: int = 0
    skipped_rows: int = 0
    total_credits_used: float = 0.0
    estimated_cost_usd: Optional[float] = None
    cost_by_provider: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    last_processed_row: int = 0


# ---------------------------------------------------------------------------
# CreditUsage
# ---------------------------------------------------------------------------

class CreditUsage(BaseModel):
    id: str = Field(default_factory=_new_uuid)
    provider: ProviderName
    date: str  # YYYY-MM-DD
    credits_used: float = 0.0
    credits_remaining: Optional[float] = None
    api_calls_made: int = 0
    successful_lookups: int = 0
    failed_lookups: int = 0
    cost_usd: Optional[float] = None
    budget_limit: Optional[float] = None
    updated_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# CacheEntry
# ---------------------------------------------------------------------------

class CacheEntry(BaseModel):
    cache_key: str
    provider: ProviderName
    enrichment_type: EnrichmentType
    query_hash: str
    response_data: dict = Field(default_factory=dict)
    found: bool = False
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: Optional[datetime] = None
    hit_count: int = 0


# ---------------------------------------------------------------------------
# EmailPattern
# ---------------------------------------------------------------------------

class EmailPattern(BaseModel):
    id: str = Field(default_factory=_new_uuid)
    domain: str
    pattern: str  # e.g. "{first}.{last}"
    confidence: float = 0.0
    sample_count: int = 0
    examples: list[str] = Field(default_factory=list)
    discovered_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
