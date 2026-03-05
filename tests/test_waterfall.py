"""Tests for waterfall orchestrator."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from config.settings import ProviderName
from data.models import EnrichmentType, VerificationStatus
from providers.base import ProviderResponse
from enrichment.router import get_provider_sequence, estimate_steps_cost
from data.models import RouteCategory


class TestGetProviderSequence:
    def test_name_and_domain_starts_with_pattern_match(self):
        order = [ProviderName.APOLLO, ProviderName.ICYPEAS, ProviderName.FINDYMAIL]
        steps = get_provider_sequence(RouteCategory.NAME_AND_DOMAIN, order)
        assert steps[0]["action"] == "pattern_match"
        assert steps[0]["is_free"] is True
        assert len(steps) == 4  # pattern_match + 3 providers

    def test_name_and_company_starts_with_domain_lookup(self):
        order = [ProviderName.APOLLO, ProviderName.FINDYMAIL]
        steps = get_provider_sequence(RouteCategory.NAME_AND_COMPANY, order)
        assert steps[0]["action"] == "find_domain"
        assert steps[0]["is_free"] is True

    def test_linkedin_person_contactout_first(self):
        order = [ProviderName.APOLLO, ProviderName.FINDYMAIL, ProviderName.CONTACTOUT]
        steps = get_provider_sequence(RouteCategory.LINKEDIN_PERSON, order)
        assert steps[0]["provider"] == ProviderName.CONTACTOUT
        # ContactOut should not appear again in the remaining steps
        remaining_providers = [s["provider"] for s in steps[1:]]
        assert ProviderName.CONTACTOUT not in remaining_providers

    def test_email_only_verify(self):
        order = [ProviderName.APOLLO]
        steps = get_provider_sequence(RouteCategory.EMAIL_ONLY, order)
        # First step is free local verification, then paid external
        assert steps[0]["action"] == "verify_email_local"
        assert steps[0]["is_free"] is True

    def test_domain_only_enrich(self):
        order = [ProviderName.APOLLO]
        steps = get_provider_sequence(RouteCategory.DOMAIN_ONLY, order)
        assert steps[0]["action"] == "enrich_company"

    def test_unroutable_empty(self):
        order = [ProviderName.APOLLO]
        steps = get_provider_sequence(RouteCategory.UNROUTABLE, order)
        assert len(steps) == 0

    def test_name_only_search_people(self):
        order = [ProviderName.APOLLO]
        steps = get_provider_sequence(RouteCategory.NAME_ONLY, order)
        assert steps[0]["action"] == "search_people"
        assert steps[0]["is_free"] is True


class TestEstimateStepsCost:
    def test_free_steps_only(self):
        steps = [{"action": "pattern_match", "provider": None, "is_free": True, "description": ""}]
        cost = estimate_steps_cost(steps)
        assert cost["max_credits"] == 0
        assert cost["min_credits"] == 0

    def test_single_paid_step(self):
        steps = [
            {"action": "find_email", "provider": ProviderName.APOLLO, "is_free": False, "description": ""},
        ]
        cost = estimate_steps_cost(steps)
        assert cost["max_credits"] == 1
        assert cost["min_credits"] == 1

    def test_multiple_paid_steps(self):
        steps = [
            {"action": "pattern_match", "provider": None, "is_free": True, "description": ""},
            {"action": "find_email", "provider": ProviderName.APOLLO, "is_free": False, "description": ""},
            {"action": "find_email", "provider": ProviderName.FINDYMAIL, "is_free": False, "description": ""},
        ]
        cost = estimate_steps_cost(steps)
        assert cost["max_credits"] == 2
        assert cost["min_credits"] == 1


class TestProviderResponse:
    def test_found_response(self):
        r = ProviderResponse(found=True, data={"email": "john@acme.com"}, email="john@acme.com")
        assert r.found is True
        assert r.email == "john@acme.com"

    def test_not_found_response(self):
        r = ProviderResponse(found=False, data={})
        assert r.found is False
        assert r.email is None

    def test_error_response(self):
        r = ProviderResponse(found=False, data={}, error="Rate limited")
        assert r.error == "Rate limited"
