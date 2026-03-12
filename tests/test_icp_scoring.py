"""Tests for ICP scoring engine."""
import pytest

from config.settings import ICPPreset
from data.models import Company
from enrichment.icp_scorer import score_company, batch_score_companies


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aerospace_preset() -> ICPPreset:
    return ICPPreset(
        name="aerospace_defense",
        display_name="Aerospace & Defense",
        industries=["aerospace", "defense", "military", "aviation",
                     "defense & space", "aerospace & defense"],
        keywords=["MRO", "avionics", "mil-spec", "DoD", "ITAR",
                   "aerospace manufacturing"],
        employee_min=10,
        employee_max=100,
        countries=["US", "UK", "CA"],
    )


@pytest.fixture
def custom_preset() -> ICPPreset:
    return ICPPreset(
        name="custom",
        display_name="Custom Test",
        industries=["software", "technology"],
        keywords=["SaaS", "cloud"],
        employee_min=50,
        employee_max=500,
        countries=["US", "DE", "FR"],
    )


@pytest.fixture
def perfect_company() -> Company:
    """Company that perfectly matches aerospace_defense preset."""
    return Company(
        name="AeroTech Corp",
        domain="aerotech.com",
        industry="aerospace",
        employee_count=50,
        country="US",
        description="Leading MRO and avionics provider specializing in mil-spec DoD ITAR aerospace manufacturing",
    )


@pytest.fixture
def partial_company() -> Company:
    """Company with some matching fields."""
    return Company(
        name="Partial Inc",
        domain="partial.com",
        industry="aerospace",
        employee_count=200,  # out of range
        country="US",
        description="General aviation services",
    )


@pytest.fixture
def none_company() -> Company:
    """Company with all optional fields as None."""
    return Company(
        name="Unknown Corp",
    )


# ---------------------------------------------------------------------------
# Employee count scoring (30 weight)
# ---------------------------------------------------------------------------

class TestEmployeeScoring:
    def test_employee_in_range_scores_30(self, aerospace_preset):
        """Company with employee_count in range gets full employee weight."""
        company = Company(name="InRange", employee_count=50, country="US",
                          industry="aerospace",
                          description="MRO avionics mil-spec DoD ITAR aerospace manufacturing")
        score = score_company(company, aerospace_preset)
        # Perfect match on all dimensions = 100
        assert score == 100

    def test_employee_in_range_only(self, aerospace_preset):
        """Company with ONLY employee_count in range (no other matches)."""
        company = Company(name="InRange", employee_count=50)
        score = score_company(company, aerospace_preset)
        # Only employee dimension has data, so score = 30/30 * 100 = 100
        # Wait -- only criteria with data count, so 30 is max, 30/30 = 100
        assert score == 100

    def test_employee_below_half_min_scores_zero(self, aerospace_preset):
        """Company with employee_count below 50% of min scores 0 on employee criteria."""
        # min is 10, 50% of 10 = 5, so employee_count < 5 = 0
        company = Company(name="TooSmall", employee_count=3)
        score = score_company(company, aerospace_preset)
        # Only dimension with data is employee, and it scores 0
        assert score == 0

    def test_employee_close_to_range_scores_partial(self, aerospace_preset):
        """Company near range boundary gets partial employee score."""
        # max is 100, employee_count = 150 is close but out of range
        company = Company(name="CloseEnough", employee_count=150)
        score = score_company(company, aerospace_preset)
        # Should get partial (15 out of 30), but only dim with data
        # 15/30 * 100 = 50
        assert score == 50


# ---------------------------------------------------------------------------
# Industry scoring (35 weight)
# ---------------------------------------------------------------------------

class TestIndustryScoring:
    def test_matching_industry_scores_35(self, aerospace_preset):
        """Company with matching industry gets full industry weight."""
        company = Company(name="AeroCo", industry="aerospace")
        score = score_company(company, aerospace_preset)
        # Only industry has data => 35/35 = 100
        assert score == 100

    def test_substring_industry_match(self, aerospace_preset):
        """Partial/substring industry match still scores."""
        company = Company(name="SubMatch", industry="Aerospace & Defense")
        score = score_company(company, aerospace_preset)
        assert score == 100  # substring "aerospace" matches

    def test_no_industry_match_scores_zero(self, aerospace_preset):
        """Company with non-matching industry scores 0 on industry."""
        company = Company(name="NoMatch", industry="retail")
        score = score_company(company, aerospace_preset)
        assert score == 0


# ---------------------------------------------------------------------------
# Geography scoring (20 weight)
# ---------------------------------------------------------------------------

class TestGeographyScoring:
    def test_country_in_target_scores_20(self, aerospace_preset):
        """Company with country in target geography gets full geo weight."""
        company = Company(name="USCo", country="US")
        score = score_company(company, aerospace_preset)
        # Only geo has data => 20/20 = 100
        assert score == 100

    def test_country_normalized(self, aerospace_preset):
        """Geography check uses normalized country codes."""
        # Company model normalizes "United States" -> "US"
        company = Company(name="NormCo", country="United States")
        score = score_company(company, aerospace_preset)
        assert score == 100

    def test_ireland_included(self):
        """IE (Ireland) is supported as a valid country code."""
        preset = ICPPreset(
            name="test",
            display_name="Test",
            industries=["tech"],
            countries=["US", "UK", "CA", "IE"],
        )
        company = Company(name="IrishCo", country="IE")
        score = score_company(company, preset)
        assert score == 100

    def test_non_target_country_scores_zero(self, aerospace_preset):
        """Company outside target geography scores 0 on geo."""
        company = Company(name="AusCo", country="AU")
        score = score_company(company, aerospace_preset)
        assert score == 0


# ---------------------------------------------------------------------------
# Keyword scoring (15 weight)
# ---------------------------------------------------------------------------

class TestKeywordScoring:
    def test_all_keywords_match_scores_15(self, aerospace_preset):
        """Company description matching all keywords gets full keyword weight."""
        company = Company(
            name="KeyCo",
            description="MRO avionics mil-spec DoD ITAR aerospace manufacturing",
        )
        score = score_company(company, aerospace_preset)
        assert score == 100  # only keyword dim has data

    def test_partial_keywords_scores_proportional(self, aerospace_preset):
        """Matching some keywords scores proportionally."""
        # 3 of 6 keywords: MRO, avionics, DoD
        company = Company(
            name="PartialKey",
            description="We do MRO and avionics work for DoD contracts",
        )
        score = score_company(company, aerospace_preset)
        # 3/6 keywords => 7.5/15 => 50% of keyword weight
        assert score == 50

    def test_no_keywords_match_scores_zero(self, aerospace_preset):
        """Description with no matching keywords scores 0."""
        company = Company(name="NoKey", description="We sell shoes and handbags")
        score = score_company(company, aerospace_preset)
        assert score == 0


# ---------------------------------------------------------------------------
# Combined / edge cases
# ---------------------------------------------------------------------------

class TestCombinedScoring:
    def test_perfect_match_scores_100(self, aerospace_preset, perfect_company):
        """Company matching all criteria perfectly scores 100."""
        score = score_company(perfect_company, aerospace_preset)
        assert score == 100

    def test_all_none_fields_scores_zero(self, aerospace_preset, none_company):
        """Company with all None fields scores 0."""
        score = score_company(none_company, aerospace_preset)
        assert score == 0

    def test_mixed_match(self, aerospace_preset):
        """Company with some matching and some non-matching dimensions."""
        company = Company(
            name="MixedCo",
            industry="aerospace",       # match (35)
            employee_count=50,           # match (30)
            country="AU",                # no match (0)
            description="We sell shoes",  # no match (0)
        )
        score = score_company(company, aerospace_preset)
        # 65 / 100 total weight = 65
        assert score == 65

    def test_score_is_integer(self, aerospace_preset, perfect_company):
        """Score is always an integer."""
        score = score_company(perfect_company, aerospace_preset)
        assert isinstance(score, int)

    def test_empty_preset_industries(self):
        """Preset with empty industries list: industry dimension excluded."""
        preset = ICPPreset(
            name="empty",
            display_name="Empty Industries",
            industries=[],
            employee_min=10,
            employee_max=100,
            countries=["US"],
        )
        company = Company(name="Test", employee_count=50, country="US")
        score = score_company(company, preset)
        # employee (30) + geo (20) = 50 max weight, both match
        assert score == 100


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------

class TestBatchScoring:
    def test_batch_scores_multiple(self, aerospace_preset):
        """batch_score_companies scores multiple companies."""
        companies = [
            Company(name="A", industry="aerospace", employee_count=50,
                    country="US",
                    description="MRO avionics mil-spec DoD ITAR aerospace manufacturing"),
            Company(name="B", industry="retail"),
            Company(name="C"),
        ]
        results = batch_score_companies(companies, aerospace_preset)
        assert len(results) == 3
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        # First should be 100, second > 0 (industry match only), third 0
        assert results[0][1] == 100
        assert results[0][0].name == "A"
        assert results[2][1] == 0

    def test_batch_returns_company_score_tuples(self, aerospace_preset):
        """Each result is (Company, int) tuple."""
        companies = [Company(name="X", country="US")]
        results = batch_score_companies(companies, aerospace_preset)
        company, score = results[0]
        assert isinstance(company, Company)
        assert isinstance(score, int)
