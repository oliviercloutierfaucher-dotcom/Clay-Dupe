"""API key validation logic -- separated from Streamlit for testability.

Validates provider API keys by calling health_check() on each configured
provider. Results are cached by the caller (Streamlit cache in app.py).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config.settings import ProviderName, Settings
from data.sync import run_sync

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider class registry (lazy import to avoid circular deps)
# ---------------------------------------------------------------------------

_PROVIDER_CLASSES: dict[ProviderName, type] | None = None


def _get_provider_classes() -> dict:
    global _PROVIDER_CLASSES
    if _PROVIDER_CLASSES is None:
        from providers.apollo import ApolloProvider
        from providers.findymail import FindymailProvider
        from providers.icypeas import IcypeasProvider
        from providers.contactout import ContactOutProvider
        from providers.datagma import DatagmaProvider

        _PROVIDER_CLASSES = {
            ProviderName.APOLLO: ApolloProvider,
            ProviderName.FINDYMAIL: FindymailProvider,
            ProviderName.ICYPEAS: IcypeasProvider,
            ProviderName.CONTACTOUT: ContactOutProvider,
            ProviderName.DATAGMA: DatagmaProvider,
        }
    return _PROVIDER_CLASSES


def _check_provider_health(provider_name: str, api_key: str) -> bool:
    """Instantiate a provider and run health_check synchronously.

    Returns True if health_check passes, False otherwise.
    """
    try:
        pname = ProviderName(provider_name)
        cls = _get_provider_classes().get(pname)
        if cls is None:
            return False
        provider = cls(api_key=api_key)
        return run_sync(provider.health_check())
    except Exception:
        logger.warning("Health check failed for %s", provider_name, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_api_keys(settings: Settings) -> dict[str, bool]:
    """Validate all configured provider API keys.

    Returns a dict mapping provider name (str) to validation status (bool).
    Providers with empty keys are marked False without calling health_check.
    """
    results: dict[str, bool] = {}
    for pname in ProviderName:
        pcfg = settings.providers.get(pname)
        if pcfg is None or not pcfg.api_key:
            results[pname.value] = False
            continue
        results[pname.value] = _check_provider_health(pname.value, pcfg.api_key)
    return results


def get_validated_providers(settings: Settings) -> list[ProviderName]:
    """Return waterfall_order filtered to only providers with valid API keys."""
    validation = validate_api_keys(settings)
    return [
        p for p in settings.waterfall_order
        if validation.get(p.value, False)
    ]
