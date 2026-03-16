"""API key validation logic -- separated from Streamlit for testability.

Validates provider API keys by calling health_check() on each configured
provider. Results are cached by the caller (Streamlit cache in app.py).
"""
from __future__ import annotations

import logging

from config.settings import ProviderName, Settings
from data.sync import run_sync

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


def validate_salesforce() -> dict[str, object]:
    """Validate Salesforce connection if configured.

    Returns a dict with keys:
    - configured (bool): Whether SF credentials are present.
    - connected (bool): Whether health_check succeeded.
    - org_name (str | None): SF org name on success.
    - account_count (int | None): Number of accounts on success.
    - error (str | None): Error message on failure.
    """
    from config.settings import load_salesforce_config

    sf_config = load_salesforce_config()

    if not sf_config.is_configured():
        return {
            "configured": False,
            "connected": False,
            "org_name": None,
            "account_count": None,
            "error": None,
        }

    try:
        from providers.salesforce import SalesforceClient

        client = SalesforceClient(
            sf_config.username, sf_config.password, sf_config.security_token,
        )
        result = client.health_check()
        return {
            "configured": True,
            "connected": True,
            "org_name": result.get("org_name"),
            "account_count": result.get("account_count"),
            "error": None,
        }
    except Exception as exc:
        logger.warning("Salesforce health check failed: %s", exc)
        return {
            "configured": True,
            "connected": False,
            "org_name": None,
            "account_count": None,
            "error": str(exc),
        }


def get_validated_providers(settings: Settings) -> list[ProviderName]:
    """Return waterfall_order filtered to only providers with valid API keys."""
    validation = validate_api_keys(settings)
    return [
        p for p in settings.waterfall_order
        if validation.get(p.value, False)
    ]
