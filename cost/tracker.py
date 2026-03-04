"""Cost tracking, ROI analysis, and waterfall optimization."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database

from config.settings import ProviderName


# Approximate USD cost per credit for each provider (used for cost estimation)
_PROVIDER_COST_PER_CREDIT: dict[ProviderName, float] = {
    ProviderName.APOLLO: 0.01,
    ProviderName.FINDYMAIL: 0.02,
    ProviderName.ICYPEAS: 0.015,
    ProviderName.CONTACTOUT: 0.05,
}


class CostTracker:
    def __init__(self, db: Database):
        self.db = db

    def get_provider_stats(self, provider: ProviderName, days: int = 30) -> dict:
        """Returns hit_rate, avg_cost_per_hit, total_credits, total_lookups, marginal_finds."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self.db._connect() as conn:
            # Basic stats: total lookups, found count, total credits
            row = conn.execute("""
                SELECT COUNT(*) as total_lookups,
                       SUM(CASE WHEN found = 1 THEN 1 ELSE 0 END) as found_count,
                       SUM(cost_credits) as total_credits,
                       AVG(response_time_ms) as avg_response_ms
                FROM enrichment_results
                WHERE source_provider = ? AND found_at >= ?
            """, (provider.value, cutoff)).fetchone()

            total_lookups = row["total_lookups"] or 0
            found_count = row["found_count"] or 0
            total_credits = row["total_credits"] or 0.0
            avg_response_ms = row["avg_response_ms"]

            # Marginal finds: results found by this provider where no earlier
            # waterfall step (lower waterfall_position) found a result for the
            # same person_id in the same campaign.
            marginal_row = conn.execute("""
                SELECT COUNT(*) as marginal
                FROM enrichment_results er
                WHERE er.source_provider = ?
                  AND er.found = 1
                  AND er.found_at >= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM enrichment_results earlier
                      WHERE earlier.person_id = er.person_id
                        AND earlier.campaign_id = er.campaign_id
                        AND earlier.found = 1
                        AND earlier.waterfall_position < er.waterfall_position
                  )
            """, (provider.value, cutoff)).fetchone()

            marginal_finds = marginal_row["marginal"] or 0

        hit_rate = (found_count / total_lookups * 100) if total_lookups > 0 else 0.0
        avg_cost_per_hit = (total_credits / found_count) if found_count > 0 else 0.0
        cost_per_credit = _PROVIDER_COST_PER_CREDIT.get(provider, 0.01)

        return {
            "provider": provider.value,
            "days": days,
            "total_lookups": total_lookups,
            "found_count": found_count,
            "hit_rate": round(hit_rate, 2),
            "total_credits": round(total_credits, 2),
            "total_cost_usd": round(total_credits * cost_per_credit, 4),
            "avg_cost_per_hit": round(avg_cost_per_hit, 4),
            "avg_cost_per_hit_usd": round(avg_cost_per_hit * cost_per_credit, 4),
            "marginal_finds": marginal_finds,
            "avg_response_ms": round(avg_response_ms, 1) if avg_response_ms else None,
        }

    def get_all_provider_stats(self, days: int = 30) -> dict[str, dict]:
        """Get stats for all providers."""
        result = {}
        for provider in ProviderName:
            stats = self.get_provider_stats(provider, days=days)
            # Only include providers that have activity
            if stats["total_lookups"] > 0:
                result[provider.value] = stats
        return result

    def get_waterfall_recommendation(self) -> Optional[list[ProviderName]]:
        """If reordering providers by (hit_rate/cost) would save >15%, return recommended order.

        The efficiency score is hit_rate / avg_cost_per_hit. Providers with
        higher efficiency should come first in the waterfall so that cheaper,
        higher-hit-rate providers are tried before expensive ones. We compare
        the estimated total cost of the current order against the optimal order;
        if savings exceed 15%, we return the new order.
        """
        stats = self.get_all_provider_stats(days=30)
        if len(stats) < 2:
            return None

        # Build efficiency ranking: hit_rate / cost_per_hit (higher = better)
        provider_efficiency: list[tuple[ProviderName, float, dict]] = []
        for pname_str, pstats in stats.items():
            provider = ProviderName(pname_str)
            avg_cost = pstats["avg_cost_per_hit"] if pstats["avg_cost_per_hit"] > 0 else 0.001
            efficiency = pstats["hit_rate"] / avg_cost
            provider_efficiency.append((provider, efficiency, pstats))

        # Current order: as they appear in DB (by average waterfall_position)
        with self.db._connect() as conn:
            order_rows = conn.execute("""
                SELECT source_provider, AVG(waterfall_position) as avg_pos
                FROM enrichment_results
                WHERE waterfall_position IS NOT NULL
                GROUP BY source_provider
                ORDER BY avg_pos ASC
            """).fetchall()

        if not order_rows:
            return None

        current_order = [ProviderName(r["source_provider"]) for r in order_rows
                         if r["source_provider"] in stats]

        # Optimal order: sort by efficiency descending
        optimal_order = [p for p, _, _ in sorted(provider_efficiency,
                                                  key=lambda x: x[1],
                                                  reverse=True)]

        # Estimate cost for each ordering using a simple waterfall simulation.
        # For N lookups, each step only processes rows not found by prior steps.
        def _estimate_cost(order: list[ProviderName]) -> float:
            total_cost = 0.0
            remaining_fraction = 1.0  # fraction of rows still needing lookup
            for p in order:
                if p.value not in stats:
                    continue
                pstats = stats[p.value]
                hit_rate_frac = pstats["hit_rate"] / 100.0
                avg_cost = pstats["avg_cost_per_hit"] if pstats["avg_cost_per_hit"] > 0 else 0.001
                # Cost for this step: remaining rows * avg_cost (every lookup costs)
                # but we approximate cost as: remaining * (total_credits / total_lookups)
                cost_per_lookup = (pstats["total_credits"] / pstats["total_lookups"]
                                   if pstats["total_lookups"] > 0 else 0)
                total_cost += remaining_fraction * cost_per_lookup
                # After this step, the found fraction is removed
                remaining_fraction *= (1 - hit_rate_frac)
            return total_cost

        current_cost = _estimate_cost(current_order)
        optimal_cost = _estimate_cost(optimal_order)

        if current_cost <= 0:
            return None

        savings_pct = (current_cost - optimal_cost) / current_cost * 100

        if savings_pct > 15:
            return optimal_order
        return None

    def estimate_campaign_cost(self, total_rows: int, cached_rows: int,
                               waterfall_order: list[ProviderName]) -> dict:
        """Estimate credits/cost for a new campaign based on historical hit rates.
        Returns per-provider estimates and total."""
        stats = self.get_all_provider_stats(days=30)
        rows_to_enrich = total_rows - cached_rows
        remaining = float(rows_to_enrich)
        per_provider = {}
        total_credits = 0.0
        total_cost_usd = 0.0

        for provider in waterfall_order:
            pstats = stats.get(provider.value)
            if pstats and pstats["total_lookups"] > 0:
                hit_rate_frac = pstats["hit_rate"] / 100.0
                cost_per_lookup = pstats["total_credits"] / pstats["total_lookups"]
            else:
                # No historical data -- use conservative defaults
                hit_rate_frac = 0.3
                cost_per_lookup = 1.0

            estimated_lookups = remaining
            estimated_finds = remaining * hit_rate_frac
            estimated_credits = estimated_lookups * cost_per_lookup
            cost_per_credit = _PROVIDER_COST_PER_CREDIT.get(provider, 0.01)
            estimated_usd = estimated_credits * cost_per_credit

            per_provider[provider.value] = {
                "estimated_lookups": round(estimated_lookups),
                "estimated_finds": round(estimated_finds),
                "estimated_credits": round(estimated_credits, 2),
                "estimated_cost_usd": round(estimated_usd, 4),
                "hit_rate_used": round(hit_rate_frac * 100, 2),
            }

            total_credits += estimated_credits
            total_cost_usd += estimated_usd
            # Remaining rows shrink by the expected finds
            remaining -= estimated_finds
            if remaining <= 0:
                remaining = 0

        return {
            "total_rows": total_rows,
            "cached_rows": cached_rows,
            "rows_to_enrich": rows_to_enrich,
            "per_provider": per_provider,
            "total_estimated_credits": round(total_credits, 2),
            "total_estimated_cost_usd": round(total_cost_usd, 4),
            "estimated_unfound_rows": round(remaining),
        }

    def get_daily_spend_history(self, days: int = 30) -> list[dict]:
        """Returns daily spend data for charts. List of {date, provider, credits, cost}."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        with self.db._connect() as conn:
            rows = conn.execute("""
                SELECT date, provider, credits_used,
                       api_calls_made, successful_lookups, failed_lookups
                FROM credit_usage
                WHERE date >= ?
                ORDER BY date ASC, provider ASC
            """, (cutoff,)).fetchall()

        result = []
        for row in rows:
            provider_name = row["provider"]
            credits = row["credits_used"] or 0.0
            # Look up cost per credit for this provider
            try:
                prov = ProviderName(provider_name)
                cost_per_credit = _PROVIDER_COST_PER_CREDIT.get(prov, 0.01)
            except ValueError:
                cost_per_credit = 0.01

            result.append({
                "date": row["date"],
                "provider": provider_name,
                "credits": round(credits, 2),
                "cost_usd": round(credits * cost_per_credit, 4),
                "api_calls": row["api_calls_made"] or 0,
                "successful_lookups": row["successful_lookups"] or 0,
                "failed_lookups": row["failed_lookups"] or 0,
            })

        return result
