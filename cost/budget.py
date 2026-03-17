"""Per-provider and per-campaign budget management."""
from __future__ import annotations

import time
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
        # In-memory cache: key -> (value, timestamp)
        self._cache: dict[str, tuple[float, float]] = {}
        self._cache_ttl: float = 60.0  # seconds

    def set_daily_limit(self, provider: ProviderName, limit: float):
        self._daily_limits[provider] = limit

    def set_monthly_limit(self, provider: ProviderName, limit: float):
        self._monthly_limits[provider] = limit

    def set_campaign_budget(self, campaign_id: str, max_credits: float):
        self._campaign_budgets[campaign_id] = max_credits

    async def can_spend(self, provider: ProviderName, credits: float = 1.0,
                        campaign_id: Optional[str] = None) -> bool:
        """Check if we can spend credits without exceeding any limit.
        Checks daily limit, monthly limit, and campaign budget."""
        # Check daily limit
        if provider in self._daily_limits:
            daily_used = await self._get_daily_used(provider)
            if daily_used + credits > self._daily_limits[provider]:
                return False

        # Check monthly limit
        if provider in self._monthly_limits:
            monthly_used = await self._get_monthly_used(provider)
            if monthly_used + credits > self._monthly_limits[provider]:
                return False

        # Check campaign budget
        if campaign_id and campaign_id in self._campaign_budgets:
            campaign_used = await self._get_campaign_used(campaign_id)
            if campaign_used + credits > self._campaign_budgets[campaign_id]:
                return False

        return True

    def clear_cache(self):
        """Clear the entire budget check cache."""
        self._cache.clear()

    def _cache_get(self, key: str) -> Optional[float]:
        """Return cached value if present and not expired, else None."""
        entry = self._cache.get(key)
        if entry is not None:
            value, ts = entry
            if (time.monotonic() - ts) < self._cache_ttl:
                return value
            del self._cache[key]
        return None

    def _cache_set(self, key: str, value: float):
        """Store a value in the cache with the current timestamp."""
        self._cache[key] = (value, time.monotonic())

    async def record_spend(self, provider: ProviderName, credits: float,
                           campaign_id: Optional[str] = None, found: bool = False):
        """Record credit expenditure in the database."""
        today = date.today().isoformat()
        async with self.db._connect() as conn:
            # Upsert credit_usage for today
            await conn.execute("""
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

        # Increment cached values so subsequent can_spend() calls stay accurate
        # without needing a DB round-trip.
        daily_key = f"daily:{provider.value}:{today}"
        daily_cached = self._cache_get(daily_key)
        if daily_cached is not None:
            self._cache_set(daily_key, daily_cached + credits)

        monthly_key = f"monthly:{provider.value}:{date.today().replace(day=1).isoformat()}"
        monthly_cached = self._cache_get(monthly_key)
        if monthly_cached is not None:
            self._cache_set(monthly_key, monthly_cached + credits)

        if campaign_id:
            campaign_key = f"campaign:{campaign_id}"
            campaign_cached = self._cache_get(campaign_key)
            if campaign_cached is not None:
                self._cache_set(campaign_key, campaign_cached + credits)

    async def get_balance(self, provider: ProviderName) -> dict:
        """Returns daily/monthly usage and limits."""
        daily_used = await self._get_daily_used(provider)
        monthly_used = await self._get_monthly_used(provider)
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

    async def get_campaign_spend(self, campaign_id: str) -> dict:
        """Returns per-provider breakdown for a campaign."""
        async with self.db._read() as conn:
            cursor = await conn.execute("""
                SELECT source_provider, SUM(cost_credits) as total_credits,
                       COUNT(*) as total_calls,
                       SUM(CASE WHEN found = 1 THEN 1 ELSE 0 END) as found_count
                FROM enrichment_results
                WHERE campaign_id = ?
                GROUP BY source_provider
            """, (campaign_id,))
            rows = await cursor.fetchall()

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

    async def _get_daily_used(self, provider: ProviderName) -> float:
        today = date.today().isoformat()
        cache_key = f"daily:{provider.value}:{today}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        async with self.db._read() as conn:
            cursor = await conn.execute(
                "SELECT credits_used FROM credit_usage WHERE provider = ? AND date = ?",
                (provider.value, today)
            )
            row = await cursor.fetchone()
        value = row["credits_used"] if row else 0.0
        self._cache_set(cache_key, value)
        return value

    async def _get_monthly_used(self, provider: ProviderName) -> float:
        month_start = date.today().replace(day=1).isoformat()
        cache_key = f"monthly:{provider.value}:{month_start}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        async with self.db._read() as conn:
            cursor = await conn.execute(
                "SELECT SUM(credits_used) as total FROM credit_usage WHERE provider = ? AND date >= ?",
                (provider.value, month_start)
            )
            row = await cursor.fetchone()
        value = row["total"] if row and row["total"] else 0.0
        self._cache_set(cache_key, value)
        return value

    async def _get_campaign_used(self, campaign_id: str) -> float:
        cache_key = f"campaign:{campaign_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        async with self.db._read() as conn:
            cursor = await conn.execute(
                "SELECT SUM(cost_credits) as total FROM enrichment_results WHERE campaign_id = ?",
                (campaign_id,)
            )
            row = await cursor.fetchone()
        value = row["total"] if row and row["total"] else 0.0
        self._cache_set(cache_key, value)
        return value
