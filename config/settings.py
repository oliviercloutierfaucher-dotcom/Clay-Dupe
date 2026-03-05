"""Load config from .env + provide ICP presets."""
import os
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from enum import Enum

load_dotenv()

class ProviderName(str, Enum):
    APOLLO = "apollo"
    FINDYMAIL = "findymail"
    ICYPEAS = "icypeas"
    CONTACTOUT = "contactout"

class ProviderConfig(BaseModel):
    name: ProviderName
    api_key: str = ""
    enabled: bool = True
    daily_credit_limit: Optional[int] = None
    monthly_credit_limit: Optional[int] = None

class ICPPreset(BaseModel):
    name: str
    display_name: str
    industries: list[str]
    keywords: list[str] = []
    employee_min: int = 10
    employee_max: int = 100
    ebitda_min: Optional[int] = 1_000_000
    ebitda_max: Optional[int] = 15_000_000
    countries: list[str] = Field(default_factory=lambda: ["US", "UK", "CA"])

class Settings(BaseModel):
    providers: dict[ProviderName, ProviderConfig]
    waterfall_order: list[ProviderName]
    cache_ttl_days: int = 30
    db_path: str = "clay_dupe.db"
    max_concurrent_requests: int = 5
    icp_presets: dict[str, ICPPreset]

    def reload_api_keys(self) -> dict[ProviderName, bool]:
        """Re-read API keys from .env without restarting.

        Returns a dict mapping each provider to whether its key changed.
        """
        load_dotenv(override=True)
        changed: dict[ProviderName, bool] = {}
        for pname in ProviderName:
            env_key = f"{pname.value.upper()}_API_KEY"
            new_key = os.getenv(env_key, "")
            pcfg = self.providers.get(pname)
            if pcfg is not None:
                old_key = pcfg.api_key
                if new_key != old_key:
                    pcfg.api_key = new_key
                    changed[pname] = True
                else:
                    changed[pname] = False
            else:
                changed[pname] = False
        return changed

def load_settings() -> Settings:
    """Load settings from environment variables."""
    # Build provider configs from env vars
    providers = {}
    for pname in ProviderName:
        env_key = f"{pname.value.upper()}_API_KEY"
        api_key = os.getenv(env_key, "")
        providers[pname] = ProviderConfig(name=pname, api_key=api_key)

    # Parse waterfall order
    order_str = os.getenv("WATERFALL_ORDER", "apollo,icypeas,findymail,contactout")
    waterfall_order = [ProviderName(p.strip()) for p in order_str.split(",") if p.strip()]

    cache_ttl = int(os.getenv("CACHE_TTL_DAYS", "30"))
    db_path = os.getenv("DB_PATH", "clay_dupe.db")

    return Settings(
        providers=providers,
        waterfall_order=waterfall_order,
        cache_ttl_days=cache_ttl,
        db_path=db_path,
        icp_presets=ICP_PRESETS,
    )

# Hardcoded ICP presets
ICP_PRESETS = {
    "aerospace_defense": ICPPreset(
        name="aerospace_defense",
        display_name="Aerospace & Defense",
        industries=["aerospace", "defense", "military", "aviation", "defense & space", "aerospace & defense"],
        keywords=["MRO", "avionics", "mil-spec", "DoD", "ITAR", "aerospace manufacturing"],
    ),
    "medical_device": ICPPreset(
        name="medical_device",
        display_name="Medical Device",
        industries=["medical devices", "medical equipment", "healthcare technology", "biotechnology", "hospital & health care"],
        keywords=["FDA", "Class II", "Class III", "510(k)", "surgical", "implant", "diagnostic"],
    ),
    "niche_industrial": ICPPreset(
        name="niche_industrial",
        display_name="Niche Industrial",
        industries=["industrial automation", "machinery", "electrical/electronic manufacturing",
                     "mechanical or industrial engineering", "plastics", "packaging and containers", "building materials"],
        keywords=["precision machining", "CNC", "injection molding", "OEM", "contract manufacturer", "fabrication"],
    ),
}
