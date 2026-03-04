"""Per-provider and per-campaign budget management."""
from __future__ import annotations

import sqlite3
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database

from config.settings import ProviderName


class BudgetManager:
    """Manages credit budgets per provider and per campaign."""

    def __init__(self, db: Database):
        self.db = db
        # Default limits (can be overridden via settings)
        self._daily_limits: dict[ProviderName, float] = {}
        self._monthly_limits: dict[ProviderName, float] = {}
        self._campaign_budgets: dict[str, float] = {}  # campaign_id -> max credits

    def set_daily_limit(self, provider: ProviderName, limit: float):
        self._daily_limits[provider] = limit

    def set_monthly_limit(self, provider: ProviderName, limit: float):
        self._monthly_limits[provider] = limit

    def set_campaign_budget(self, campaign_id: str, max_credits: float):
        self._campaign_budgets[campaign_id] = max_credits

    def can_spend(self, provider: ProviderName, credits: float = 1.0,
                  campaign_id: Optional[str] = None) -> bool:
        """Check if we can spend credits without exceeding any limit.
        Checks daily limit, monthly limit, and campaign budget."""
        # Check daily limit
        if provider in self._daily_limits:
            daily_used = self._get_daily_used(provider)
            if daily_used + credits > self._daily_limits[provider]:
                return False

        # Check monthly limit
        if provider in self._monthly_limits:
            monthly_used = self._get_monthly_used(provider)
            if monthly_used + credits > self._monthly_limits[provider]:
                return False

        # Check campaign budget
        if campaign_id and campaign_id in self._campaign_budgets:
            campaign_used = self._get_campaign_used(campaign_id)
            if campaign_used + credits > self._campaign_budgets[campaign_id]:
                return False

        return True

    def record_spend(self, provider: ProviderName, credits: float,
                     campaign_id: Optional[str] = None, found: bool = False):
        """Record credit expenditure in the database."""
        today = date.today().isoformat()
        with self.db._connect() as conn:
            # Upsert credit_usage for today
            conn.execute("""
                INSERT INTO credit_usage (id, provider, date, credits_used, api_calls_made, successful_lookups, failed_lookups)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(provider, date) DO UPDATE SET
                    credits_used = credit_usage.credits_used + excluded.credits_used,
                    api_calls_made = credit_usage.api_calls_made + 1,
                    successful_lookups = credit_usage.successful_lookups + excluded.successful_lookups,
                    failed_lookups = credit_usage.failed_lookups + excluded.failed_lookups,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                f"{provider.value}_{today}",
                provider.value, today, credits,
                1 if found else 0,
                0 if found else 1,
            ))

    def get_balance(self, provider: ProviderName) -> dict:
        """Returns daily/monthly usage and limits."""
        daily_used = self._get_daily_used(provider)
        monthly_used = self._get_monthly_used(provider)
        daily_limit = self._daily_limits.get(provider)
        monthly_limit = self._monthly_limits.get(provider)
        return {
            "provider": provider.value,
            "daily_used": daily_used,
            "daily_limit": daily_limit,
            "daily_remaining": (daily_limit - daily_used) if daily_limit else None,
            "monthly_used": monthly_used,
            "monthly_limit": monthly_limit,
            "monthly_remaining": (monthly_limit - monthly_used) if monthly_limit else None,
            "at_daily_cap": daily_limit is not None and daily_used >= daily_limit * 0.95,
            "at_monthly_cap": monthly_limit is not None and monthly_used >= monthly_limit * 0.95,
        }

    def get_campaign_spend(self, campaign_id: str) -> dict:
        """Returns per-provider breakdown for a campaign."""
        # Query enrichment_results grouped by source_provider for this campaign
        with self.db._connect() as conn:
            rows = conn.execute("""
                SELECT source_provider, SUM(cost_credits) as total_credits,
                       COUNT(*) as total_calls,
                       SUM(CASE WHEN found = 1 THEN 1 ELSE 0 END) as found_count
                FROM enrichment_results
                WHERE campaign_id = ?
                GROUP BY source_provider
            """, (campaign_id,)).fetchall()

        result = {}
        total = 0.0
        for row in rows:
            result[row["source_provider"]] = {
                "credits": row["total_credits"] or 0,
                "calls": row["total_calls"],
                "found": row["found_count"],
            }
            total += row["total_credits"] or 0

        return {"by_provider": result, "total_credits": total,
                "budget": self._campaign_budgets.get(campaign_id)}

    def _get_daily_used(self, provider: ProviderName) -> float:
        today = date.today().isoformat()
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT credits_used FROM credit_usage WHERE provider = ? AND date = ?",
                (provider.value, today)
            ).fetchone()
        return row["credits_used"] if row else 0.0

    def _get_monthly_used(self, provider: ProviderName) -> float:
        month_start = date.today().replace(day=1).isoformat()
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT SUM(credits_used) as total FROM credit_usage WHERE provider = ? AND date >= ?",
                (provider.value, month_start)
            ).fetchone()
        return row["total"] if row and row["total"] else 0.0

    def _get_campaign_used(self, campaign_id: str) -> float:
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT SUM(cost_credits) as total FROM enrichment_results WHERE campaign_id = ?",
                (campaign_id,)
            ).fetchone()
        return row["total"] if row and row["total"] else 0.0
