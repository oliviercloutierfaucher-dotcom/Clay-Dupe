"""Integration tests for CLI commands (enrich, search, verify, stats)."""
from __future__ import annotations

import os
import csv
import tempfile
import pytest
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock, MagicMock

from cli.main import app
from data.database import Database


runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_csv(rows: list[dict], path: str) -> str:
    """Write rows to a CSV file and return the path."""
    if not rows:
        return path
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


# ---------------------------------------------------------------------------
# verify command
# ---------------------------------------------------------------------------

class TestVerifyCommand:
    def test_verify_basic_invocation(self):
        """verify command runs and produces output for a valid-syntax email."""
        with patch("cli.main.run_sync") as mock_sync:
            mock_sync.return_value = {
                "email": "test@example.com",
                "valid": False,
                "mx_found": False,
                "catch_all": False,
                "smtp_result": "no_mx",
                "confidence_modifier": -40,
            }
            result = runner.invoke(app, ["verify", "test@example.com"])
            assert result.exit_code == 0
            assert "test@example.com" in result.output

    def test_verify_shows_result_fields(self):
        """verify output includes key fields."""
        with patch("cli.main.run_sync") as mock_sync:
            mock_sync.return_value = {
                "email": "valid@acme.com",
                "valid": True,
                "mx_found": True,
                "catch_all": False,
                "smtp_result": "valid",
                "confidence_modifier": 20,
            }
            result = runner.invoke(app, ["verify", "valid@acme.com"])
            assert result.exit_code == 0
            assert "True" in result.output or "valid" in result.output


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------

class TestStatsCommand:
    def test_stats_runs_against_test_db(self):
        """stats command runs successfully against a fresh test database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path=db_path)

            # Default return values for various run_sync calls
            dashboard = {"total_enriched": 0, "email_find_rate": 0, "total_campaigns": 0, "cost_30d": 0.0}
            budget_balance = {
                "daily_used": 0.0, "daily_limit": None,
                "monthly_used": 0.0, "monthly_limit": None,
                "at_daily_cap": False, "at_monthly_cap": False,
            }
            cache_stats = {
                "total_entries": 0, "active_entries": 0, "expired_entries": 0,
                "total_hits": 0, "hit_rate": 0, "oldest_entry": None,
                "newest_entry": None, "by_type": {}, "by_provider": {},
            }

            call_count = [0]
            def run_sync_stub(coro):
                """Return appropriate mock data for each run_sync call."""
                call_count[0] += 1
                if call_count[0] == 1:
                    return dashboard
                elif call_count[0] == 2:
                    return {}
                elif call_count[0] <= 6:
                    return budget_balance
                else:
                    return cache_stats

            with patch("cli.main._load_settings_safe") as mock_settings, \
                 patch("cli.main._init_db", return_value=db), \
                 patch("cli.main.CostTracker") as mock_tracker, \
                 patch("cli.main.CacheManager"), \
                 patch("cli.main.BudgetManager"), \
                 patch("cli.main.run_sync", side_effect=run_sync_stub):

                settings = MagicMock()
                settings.db_path = db_path
                settings.providers = {}
                settings.waterfall_order = []
                mock_settings.return_value = settings

                tracker_inst = MagicMock()
                mock_tracker.return_value = tracker_inst

                result = runner.invoke(app, ["stats"])
                assert result.exit_code == 0
                assert "Dashboard" in result.output


# ---------------------------------------------------------------------------
# enrich command
# ---------------------------------------------------------------------------

class TestEnrichCommand:
    def test_enrich_missing_file_fails(self):
        """enrich with non-existent file should fail."""
        result = runner.invoke(app, ["enrich", "/nonexistent/file.csv"])
        assert result.exit_code != 0

    def test_enrich_help(self):
        """enrich --help shows usage."""
        result = runner.invoke(app, ["enrich", "--help"])
        assert result.exit_code == 0
        assert "input" in result.output.lower() or "csv" in result.output.lower()


# ---------------------------------------------------------------------------
# search command
# ---------------------------------------------------------------------------

class TestSearchCommand:
    def test_search_help(self):
        """search --help shows usage."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "companies" in result.output.lower() or "people" in result.output.lower()


# ---------------------------------------------------------------------------
# No-args shows help
# ---------------------------------------------------------------------------

class TestAppHelp:
    def test_no_args_shows_help(self):
        """No-args shows help/usage text (exit code 0 or 2 depending on typer version)."""
        result = runner.invoke(app, [])
        # Typer may return 0 (help) or 2 (missing required args)
        assert result.exit_code in (0, 2)
        # The output should mention available commands
        output_lower = result.output.lower()
        assert "enrich" in output_lower or "usage" in output_lower
