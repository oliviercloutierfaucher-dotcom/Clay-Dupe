"""Tests for input classification and routing."""
from __future__ import annotations

import pytest
from data.models import RouteCategory
from enrichment.classifier import (
    FieldSignal, detect_fields, classify_row, classify_batch, split_full_name,
)


class TestDetectFields:
    def test_email_detected(self):
        signals = detect_fields({"email": "john@acme.com"})
        assert signals & FieldSignal.EMAIL

    def test_invalid_email_not_detected(self):
        signals = detect_fields({"email": "not-an-email"})
        assert not (signals & FieldSignal.EMAIL)

    def test_domain_detected(self):
        signals = detect_fields({"company_domain": "acme.com"})
        assert signals & FieldSignal.DOMAIN

    def test_invalid_domain_not_detected(self):
        signals = detect_fields({"company_domain": "not a domain"})
        assert not (signals & FieldSignal.DOMAIN)

    def test_linkedin_detected(self):
        signals = detect_fields({"linkedin_url": "https://linkedin.com/in/johndoe"})
        assert signals & FieldSignal.LINKEDIN

    def test_linkedin_not_detected_wrong_url(self):
        signals = detect_fields({"linkedin_url": "https://twitter.com/johndoe"})
        assert not (signals & FieldSignal.LINKEDIN)

    def test_phone_detected(self):
        signals = detect_fields({"phone": "+1 (555) 123-4567"})
        assert signals & FieldSignal.PHONE

    def test_short_phone_not_detected(self):
        signals = detect_fields({"phone": "123"})
        assert not (signals & FieldSignal.PHONE)

    def test_full_name_needs_space(self):
        signals = detect_fields({"full_name": "John Doe"})
        assert signals & FieldSignal.FULL_NAME

    def test_single_word_not_full_name(self):
        signals = detect_fields({"full_name": "John"})
        assert not (signals & FieldSignal.FULL_NAME)

    def test_first_name_detected(self):
        signals = detect_fields({"first_name": "John"})
        assert signals & FieldSignal.FIRST_NAME

    def test_empty_first_name_not_detected(self):
        signals = detect_fields({"first_name": ""})
        assert not (signals & FieldSignal.FIRST_NAME)

    def test_multiple_fields(self):
        signals = detect_fields({
            "first_name": "John",
            "last_name": "Doe",
            "company_domain": "acme.com",
            "title": "VP Sales",
        })
        assert signals & FieldSignal.FIRST_NAME
        assert signals & FieldSignal.LAST_NAME
        assert signals & FieldSignal.DOMAIN
        assert signals & FieldSignal.JOB_TITLE

    def test_none_values_ignored(self):
        signals = detect_fields({"first_name": None, "email": None})
        assert signals == 0

    def test_empty_dict(self):
        assert detect_fields({}) == 0


class TestClassifyRow:
    def test_email_only(self):
        signals = detect_fields({"email": "john@acme.com"})
        assert classify_row(signals) == RouteCategory.EMAIL_ONLY

    def test_email_takes_priority_over_name_domain(self):
        """Even with name+domain, if email exists, classify as EMAIL_ONLY."""
        signals = detect_fields({
            "email": "john@acme.com",
            "first_name": "John",
            "company_domain": "acme.com",
        })
        assert classify_row(signals) == RouteCategory.EMAIL_ONLY

    def test_linkedin_person(self):
        signals = detect_fields({"linkedin_url": "https://linkedin.com/in/johndoe"})
        assert classify_row(signals) == RouteCategory.LINKEDIN_PERSON

    def test_name_and_domain(self):
        signals = detect_fields({
            "first_name": "John",
            "last_name": "Doe",
            "company_domain": "acme.com",
        })
        assert classify_row(signals) == RouteCategory.NAME_AND_DOMAIN

    def test_full_name_and_domain(self):
        signals = detect_fields({
            "full_name": "John Doe",
            "company_domain": "acme.com",
        })
        assert classify_row(signals) == RouteCategory.NAME_AND_DOMAIN

    def test_name_and_company(self):
        signals = detect_fields({
            "first_name": "John",
            "last_name": "Doe",
            "company_name": "Acme Inc",
        })
        assert classify_row(signals) == RouteCategory.NAME_AND_COMPANY

    def test_company_only(self):
        signals = detect_fields({"company_name": "Acme Inc"})
        assert classify_row(signals) == RouteCategory.COMPANY_ONLY

    def test_domain_only(self):
        signals = detect_fields({"company_domain": "acme.com"})
        assert classify_row(signals) == RouteCategory.DOMAIN_ONLY

    def test_name_only(self):
        signals = detect_fields({"first_name": "John", "last_name": "Doe"})
        assert classify_row(signals) == RouteCategory.NAME_ONLY

    def test_unroutable_empty(self):
        signals = detect_fields({})
        assert classify_row(signals) == RouteCategory.UNROUTABLE

    def test_unroutable_only_title(self):
        signals = detect_fields({"title": "VP Sales"})
        assert classify_row(signals) == RouteCategory.UNROUTABLE


class TestClassifyBatch:
    def test_groups_correctly(self):
        rows = [
            {"email": "john@acme.com"},
            {"first_name": "Jane", "company_domain": "corp.com"},
            {"linkedin_url": "https://linkedin.com/in/bob"},
            {},
        ]
        grouped = classify_batch(rows)
        assert len(grouped[RouteCategory.EMAIL_ONLY]) == 1
        assert len(grouped[RouteCategory.NAME_AND_DOMAIN]) == 1
        assert len(grouped[RouteCategory.LINKEDIN_PERSON]) == 1
        assert len(grouped[RouteCategory.UNROUTABLE]) == 1

    def test_adds_route_category_to_row(self):
        rows = [{"email": "john@acme.com"}]
        classify_batch(rows)
        assert rows[0]["_route_category"] == RouteCategory.EMAIL_ONLY


class TestSplitFullName:
    def test_two_parts(self):
        assert split_full_name("John Doe") == ("John", "Doe")

    def test_single_part(self):
        assert split_full_name("Madonna") == ("Madonna", "")

    def test_three_parts(self):
        assert split_full_name("John Van Doe") == ("John", "Van Doe")

    def test_empty(self):
        assert split_full_name("") == ("", "")

    def test_extra_spaces(self):
        assert split_full_name("  John   Doe  ") == ("John", "Doe")
