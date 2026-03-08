"""Tests for API key validation logic."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import ProviderName, ProviderConfig, Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_settings(provider_keys: dict[str, str]) -> Settings:
    """Create a Settings object with specified provider keys."""
    providers = {}
    for pname in ProviderName:
        api_key = provider_keys.get(pname.value, "")
        providers[pname] = ProviderConfig(name=pname, api_key=api_key)
    return Settings(
        providers=providers,
        waterfall_order=list(ProviderName),
        icp_presets={},
    )


# ---------------------------------------------------------------------------
# Test: validate_api_keys()
# ---------------------------------------------------------------------------

class TestValidateApiKeys:
    def test_returns_dict_of_provider_to_bool(self):
        """validate_api_keys returns dict mapping provider name -> bool."""
        from ui.validation import validate_api_keys

        settings = _make_settings({"apollo": "test-key-123"})
        with patch("ui.validation._check_provider_health", return_value=True):
            result = validate_api_keys(settings)
        assert isinstance(result, dict)
        assert "apollo" in result
        assert isinstance(result["apollo"], bool)

    def test_valid_key_returns_true(self):
        """Provider with valid key (health_check passes) returns True."""
        from ui.validation import validate_api_keys

        settings = _make_settings({"apollo": "valid-key"})
        with patch("ui.validation._check_provider_health", return_value=True):
            result = validate_api_keys(settings)
        assert result["apollo"] is True

    def test_empty_key_returns_false_without_health_check(self):
        """Provider with empty api_key returns False without calling health_check."""
        from ui.validation import validate_api_keys

        settings = _make_settings({})  # All empty keys
        mock_check = MagicMock(return_value=True)
        with patch("ui.validation._check_provider_health", mock_check):
            result = validate_api_keys(settings)
        # No health check calls for empty keys
        mock_check.assert_not_called()
        assert result["apollo"] is False

    def test_health_check_false_returns_false(self):
        """Provider with key but failing health_check returns False."""
        from ui.validation import validate_api_keys

        settings = _make_settings({"apollo": "bad-key"})

        def mock_health(pname, api_key):
            return False

        with patch("ui.validation._check_provider_health", side_effect=mock_health):
            result = validate_api_keys(settings)
        assert result["apollo"] is False


# ---------------------------------------------------------------------------
# Test: get_validated_providers()
# ---------------------------------------------------------------------------

class TestGetValidatedProviders:
    def test_filters_to_only_validated(self):
        """get_validated_providers returns only providers with True validation."""
        from ui.validation import get_validated_providers

        settings = _make_settings({"apollo": "valid-key", "findymail": "valid-key"})

        def mock_health(pname, api_key):
            return pname == "apollo"  # Only apollo passes

        with patch("ui.validation._check_provider_health", side_effect=mock_health):
            result = get_validated_providers(settings)
        assert ProviderName.APOLLO in result
        assert ProviderName.FINDYMAIL not in result

    def test_empty_when_no_valid_keys(self):
        """Returns empty list when no providers have valid keys."""
        from ui.validation import get_validated_providers

        settings = _make_settings({})
        result = get_validated_providers(settings)
        assert result == []
