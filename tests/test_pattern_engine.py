"""Tests for email pattern detection and generation."""
from __future__ import annotations

import pytest
from enrichment.pattern_engine import (
    normalize_ascii, parse_name, detect_pattern, compute_confidence,
    generate_candidates, generate_fallback_candidates,
    NICKNAMES, FORMAL_TO_NICKNAMES, PATTERN_TEMPLATES,
)


class TestNormalizeAscii:
    def test_accented_chars(self):
        assert normalize_ascii("José") == "jose"

    def test_umlaut(self):
        assert normalize_ascii("Müller") == "muller"

    def test_tilde(self):
        assert normalize_ascii("García") == "garcia"

    def test_plain_ascii(self):
        assert normalize_ascii("John") == "john"

    def test_uppercase(self):
        assert normalize_ascii("SMITH") == "smith"


class TestParseName:
    def test_basic(self):
        info = parse_name("John", "Doe")
        assert info["first"] == "john"
        assert info["last"] == "doe"
        assert info["f"] == "j"

    def test_suffix_stripped(self):
        info = parse_name("John Jr.", "Doe")
        assert info["first"] == "john"

    def test_phd_suffix(self):
        info = parse_name("John", "Doe PhD")
        assert info["last"] == "doe"

    def test_hyphenated_last(self):
        info = parse_name("Sarah", "Watson-Jones")
        assert "watson-jones" in info["last_variants"]
        assert "watsonjones" in info["last_variants"]
        assert "watson" in info["last_variants"]
        assert "jones" in info["last_variants"]

    def test_nickname_variants(self):
        info = parse_name("Bob", "Smith")
        assert "bob" in info["first_variants"]
        assert "robert" in info["first_variants"]

    def test_formal_to_nickname(self):
        info = parse_name("Robert", "Smith")
        # Robert should have bob, rob, etc. as variants
        assert "robert" in info["first_variants"]
        assert any(n in info["first_variants"] for n in ["bob", "rob", "robbie", "bobby"])

    def test_accented_name(self):
        info = parse_name("José", "García")
        assert info["first"] == "jose"
        assert info["last"] == "garcia"


class TestDetectPattern:
    def test_first_dot_last(self):
        assert detect_pattern("john.doe@acme.com", "John", "Doe") == "{first}.{last}"

    def test_flast(self):
        assert detect_pattern("jdoe@acme.com", "John", "Doe") == "{f}{last}"

    def test_firstlast(self):
        assert detect_pattern("johndoe@acme.com", "John", "Doe") == "{first}{last}"

    def test_first_only(self):
        assert detect_pattern("john@acme.com", "John", "Doe") == "{first}"

    def test_f_dot_last(self):
        assert detect_pattern("j.doe@acme.com", "John", "Doe") == "{f}.{last}"

    def test_last_dot_first(self):
        assert detect_pattern("doe.john@acme.com", "John", "Doe") == "{last}.{first}"

    def test_first_underscore_last(self):
        assert detect_pattern("john_doe@acme.com", "John", "Doe") == "{first}_{last}"

    def test_nickname_bob_robert(self):
        result = detect_pattern("robert.smith@acme.com", "Bob", "Smith")
        assert result == "{first}.{last}"

    def test_accented_name(self):
        result = detect_pattern("jose.garcia@acme.com", "José", "García")
        assert result == "{first}.{last}"

    def test_no_match(self):
        assert detect_pattern("sales@acme.com", "John", "Doe") is None

    def test_invalid_email(self):
        assert detect_pattern("not-an-email", "John", "Doe") is None

    def test_empty_email(self):
        assert detect_pattern("", "John", "Doe") is None


class TestComputeConfidence:
    def test_single_observation(self):
        result = compute_confidence({"{first}.{last}": 1})
        conf = result["{first}.{last}"]
        assert 0.55 < conf < 0.65  # ~0.59 expected

    def test_two_observations(self):
        result = compute_confidence({"{first}.{last}": 2})
        conf = result["{first}.{last}"]
        assert 0.78 < conf < 0.86  # ~0.82 expected

    def test_three_observations(self):
        result = compute_confidence({"{first}.{last}": 3})
        conf = result["{first}.{last}"]
        assert 0.88 < conf < 0.95  # ~0.91 expected (actually 0.9375)

    def test_five_observations(self):
        result = compute_confidence({"{first}.{last}": 5})
        conf = result["{first}.{last}"]
        assert conf > 0.95  # ~0.97

    def test_multiple_patterns(self):
        result = compute_confidence({"{first}.{last}": 3, "{f}{last}": 1})
        assert result["{first}.{last}"] > result["{f}{last}"]


class TestGenerateCandidates:
    def test_generates_from_known_pattern(self):
        patterns = {"{first}.{last}": 0.90}
        candidates = generate_candidates("John", "Doe", "acme.com", patterns)
        assert len(candidates) >= 1
        assert candidates[0]["email"] == "john.doe@acme.com"
        assert candidates[0]["is_primary"] is True

    def test_filters_low_confidence(self):
        patterns = {"{first}.{last}": 0.30}  # Below 0.5 threshold
        candidates = generate_candidates("John", "Doe", "acme.com", patterns)
        assert len(candidates) == 0

    def test_sorted_by_confidence(self):
        patterns = {"{f}{last}": 0.80, "{first}.{last}": 0.95}
        candidates = generate_candidates("John", "Doe", "acme.com", patterns)
        assert candidates[0]["confidence"] > candidates[1]["confidence"]

    def test_primary_flag(self):
        patterns = {"{first}.{last}": 0.90, "{f}{last}": 0.70}
        candidates = generate_candidates("John", "Doe", "acme.com", patterns)
        primary_count = sum(1 for c in candidates if c["is_primary"])
        assert primary_count == 1


class TestGenerateFallbackCandidates:
    def test_generates_top_5(self):
        candidates = generate_fallback_candidates("John", "Doe", "acme.com")
        assert len(candidates) == 5

    def test_halved_confidence(self):
        candidates = generate_fallback_candidates("John", "Doe", "acme.com")
        # Highest frequency pattern is {first}.{last} at 0.45
        # Halved = 0.225
        assert candidates[0]["confidence"] == pytest.approx(0.225, abs=0.01)

    def test_first_is_primary(self):
        candidates = generate_fallback_candidates("John", "Doe", "acme.com")
        assert candidates[0]["is_primary"] is True
        assert all(not c["is_primary"] for c in candidates[1:])

    def test_emails_have_domain(self):
        candidates = generate_fallback_candidates("Jane", "Smith", "corp.io")
        for c in candidates:
            assert c["email"].endswith("@corp.io")


class TestNicknameMappings:
    def test_nicknames_dict_not_empty(self):
        assert len(NICKNAMES) > 40

    def test_reverse_mapping_built(self):
        assert "robert" in FORMAL_TO_NICKNAMES
        assert "bob" in FORMAL_TO_NICKNAMES["robert"]

    def test_pattern_templates_ordered(self):
        assert PATTERN_TEMPLATES[0] == "{first}.{last}"
        assert len(PATTERN_TEMPLATES) >= 10
