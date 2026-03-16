"""Shared test fixtures."""
from __future__ import annotations

import os
import sys

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Provide a fresh Database instance in a temporary directory."""
    from data.database import Database
    return Database(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def settings():
    """Provide a Settings instance with no real API keys."""
    from config.settings import Settings, ProviderConfig, ProviderName, ICP_PRESETS
    providers = {
        pname: ProviderConfig(name=pname, api_key="test_key")
        for pname in ProviderName
    }
    return Settings(
        providers=providers,
        waterfall_order=list(ProviderName),
        icp_presets=ICP_PRESETS,
    )


# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

@pytest.fixture
def make_person():
    """Factory fixture for creating Person instances with sensible defaults."""
    import uuid
    from data.models import Person

    def _make(
        first_name: str = "Jane",
        last_name: str = "Doe",
        domain: str = "acme.com",
        **overrides,
    ) -> Person:
        defaults = dict(
            id=str(uuid.uuid4()),
            first_name=first_name,
            last_name=last_name,
            company_domain=domain,
        )
        defaults.update(overrides)
        return Person(**defaults)

    return _make


@pytest.fixture
def make_company():
    """Factory fixture for creating Company instances with sensible defaults."""
    import uuid
    from data.models import Company

    def _make(
        name: str = "Acme Corp",
        domain: str = "acme.com",
        **overrides,
    ) -> Company:
        defaults = dict(
            id=str(uuid.uuid4()),
            name=name,
            domain=domain,
        )
        defaults.update(overrides)
        return Company(**defaults)

    return _make
