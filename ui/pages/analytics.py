"""Analytics page -- cost, hit rate, and pattern engine charts."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.settings import ProviderName
from cost.tracker import CostTracker
from data.sync import run_sync

from ui.app import get_database, get_settings

# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.header("Analytics")

db = get_database()
settings = get_settings()
tracker = CostTracker(db)

# ---- Date range selector ----------------------------------------------------

range_cols = st.columns([2, 2, 4])
with range_cols[0]:
    days_back = st.selectbox(
        "Date range",
        options=[7, 14, 30, 60, 90],
        index=2,
        format_func=lambda d: f"Last {d} days",
    )
with range_cols[1]:
    st.markdown("")
    st.caption(
        f"{(date.today() - timedelta(days=days_back)).isoformat()} to {date.today().isoformat()}"
    )

# ---- Fetch data --------------------------------------------------------------

provider_stats = run_sync(tracker.get_all_provider_stats(days=days_back))
daily_history = run_sync(tracker.get_daily_spend_history(days=days_back))

# ===== Section 1: Cost Per Provider Bar Chart =================================

with st.container(border=True):
    st.subheader("Cost per Provider")

    if provider_stats:
        cost_data = []
        for prov, pstats in provider_stats.items():
            cost_data.append({
                "Provider": prov.title(),
                "Credits": pstats["total_credits"],
                "Cost (USD)": pstats["total_cost_usd"],
                "Lookups": pstats["total_lookups"],
                "Found": pstats["found_count"],
            })

        cost_df = pd.DataFrame(cost_data)

        # Bar chart: credits by provider
        chart_cols = st.columns(2)

        with chart_cols[0]:
            st.bar_chart(
                cost_df.set_index("Provider")["Credits"],
                color="#4f46e5",
            )
            st.caption("Total credits consumed per provider")

        with chart_cols[1]:
            st.bar_chart(
                cost_df.set_index("Provider")["Cost (USD)"],
                color="#6366f1",
            )
            st.caption("Estimated USD cost per provider")

        # Summary metrics
        metric_cols = st.columns(len(cost_data))
        for idx, row in enumerate(cost_data):
            with metric_cols[idx]:
                st.metric(
                    row["Provider"],
                    f"{row['Credits']:,.1f} credits",
                    delta=f"${row['Cost (USD)']:,.4f}",
                )
    else:
        st.info("No provider activity in the selected date range.")

# ===== Section 2: Hit Rate Line Chart ========================================

with st.container(border=True):
    st.subheader("Hit Rate by Provider")

    if provider_stats:
        hitrate_data = []
        for prov, pstats in provider_stats.items():
            hitrate_data.append({
                "Provider": prov.title(),
                "Hit Rate (%)": pstats["hit_rate"],
                "Avg Cost/Hit": pstats["avg_cost_per_hit"],
                "Marginal Finds": pstats["marginal_finds"],
                "Avg Response (ms)": pstats["avg_response_ms"] or 0,
            })

        hitrate_df = pd.DataFrame(hitrate_data)

        # Display hit rates as horizontal bar
        st.bar_chart(
            hitrate_df.set_index("Provider")["Hit Rate (%)"],
            color="#4f46e5",
            horizontal=True,
        )

        # Detailed stats table
        st.dataframe(
            hitrate_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Hit Rate (%)": st.column_config.ProgressColumn(
                    min_value=0, max_value=100, format="%.1f%%"
                ),
            },
        )
    else:
        st.info("No hit rate data available for the selected period.")

# ===== Section 3: Daily Spend Trend ==========================================

with st.container(border=True):
    st.subheader("Daily Spend Trend")

    if daily_history:
        daily_df = pd.DataFrame(daily_history)
        daily_df["date"] = pd.to_datetime(daily_df["date"])

        # Pivot for multi-line chart: one line per provider
        pivot_credits = daily_df.pivot_table(
            index="date",
            columns="provider",
            values="credits",
            aggfunc="sum",
            fill_value=0,
        )

        st.line_chart(pivot_credits)
        st.caption("Daily credits consumed per provider over time")

        # Also show daily cost
        pivot_cost = daily_df.pivot_table(
            index="date",
            columns="provider",
            values="cost_usd",
            aggfunc="sum",
            fill_value=0,
        )

        st.line_chart(pivot_cost)
        st.caption("Daily estimated USD cost per provider over time")
    else:
        st.info("No daily spend data available for the selected period.")

# ===== Section 4: Pattern Engine Savings =====================================

with st.container(border=True):
    st.subheader("Pattern Engine Savings")

    async def _fetch_pattern_stats():
        async with db._connect() as conn:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM enrichment_results WHERE from_cache = 1"
            )
            cache_hits = (await cur.fetchone())[0]

            cur = await conn.execute("SELECT COUNT(*) FROM enrichment_results")
            total_results = (await cur.fetchone())[0]

            cur = await conn.execute(
                "SELECT AVG(cost_credits) FROM enrichment_results WHERE cost_credits > 0"
            )
            avg_credit_row = await cur.fetchone()
            avg_credit = avg_credit_row[0] if avg_credit_row and avg_credit_row[0] else 1.0

            cur = await conn.execute("SELECT COUNT(*) FROM email_patterns")
            pattern_count = (await cur.fetchone())[0]
            cur = await conn.execute("SELECT COUNT(DISTINCT domain) FROM email_patterns")
            domain_count = (await cur.fetchone())[0]
            cur = await conn.execute("SELECT AVG(confidence) FROM email_patterns")
            avg_confidence = await cur.fetchone()
            avg_pattern_confidence = avg_confidence[0] if avg_confidence and avg_confidence[0] else 0.0

        return cache_hits, total_results, avg_credit, pattern_count, domain_count, avg_pattern_confidence

    cache_hits, total_results, avg_credit, pattern_count, domain_count, avg_pattern_confidence = run_sync(
        _fetch_pattern_stats()
    )

    estimated_credits_saved = cache_hits * avg_credit

    pattern_cols = st.columns(4)
    pattern_cols[0].metric("Cache Hits", f"{cache_hits:,}")
    pattern_cols[1].metric("Est. Credits Saved", f"{estimated_credits_saved:,.1f}")
    pattern_cols[2].metric(
        "Cache Hit Rate",
        f"{(cache_hits / total_results * 100):.1f}%" if total_results > 0 else "0%",
    )
    pattern_cols[3].metric("Total Results", f"{total_results:,}")

    pattern_detail_cols = st.columns(3)
    with pattern_detail_cols[0]:
        st.metric("Known Patterns", f"{pattern_count:,}")
    with pattern_detail_cols[1]:
        st.metric("Domains Covered", f"{domain_count:,}")
    with pattern_detail_cols[2]:
        st.metric("Avg Pattern Confidence", f"{avg_pattern_confidence:.1%}")

    # Show top patterns if available
    if pattern_count > 0:
        st.markdown("**Top Email Patterns by Domain Coverage**")
        async def _fetch_top_patterns():
            async with db._connect() as conn:
                cur = await conn.execute(
                    "SELECT pattern, COUNT(*) as domain_count, AVG(confidence) as avg_conf, "
                    "SUM(sample_count) as total_samples "
                    "FROM email_patterns "
                    "GROUP BY pattern "
                    "ORDER BY domain_count DESC "
                    "LIMIT 10"
                )
                return await cur.fetchall()

        top_patterns = run_sync(_fetch_top_patterns())

        pattern_rows = []
        for row in top_patterns:
            pattern_rows.append({
                "Pattern": row["pattern"],
                "Domains": row["domain_count"],
                "Avg Confidence": f"{row['avg_conf']:.1%}" if row["avg_conf"] else "N/A",
                "Total Samples": row["total_samples"] or 0,
            })

        st.dataframe(
            pd.DataFrame(pattern_rows),
            use_container_width=True,
            hide_index=True,
        )

# ===== Section 5: Waterfall Recommendation ===================================

with st.container(border=True):
    st.subheader("Waterfall Optimization")

    recommendation = run_sync(tracker.get_waterfall_recommendation())
    if recommendation:
        st.warning("A more cost-effective waterfall order has been detected (>15% savings).")
        rec_cols = st.columns(2)
        with rec_cols[0]:
            st.markdown("**Current Order**")
            for idx, p in enumerate(settings.waterfall_order):
                st.markdown(f"{idx + 1}. {p.value.title()}")
        with rec_cols[1]:
            st.markdown("**Recommended Order**")
            for idx, p in enumerate(recommendation):
                st.markdown(f"{idx + 1}. :green[**{p.value.title()}**]")

        if st.button("Apply Recommended Order", type="primary"):
            settings.waterfall_order = recommendation
            st.success("Waterfall order updated! Go to Settings to verify.")
            st.rerun()
    else:
        st.success("Current waterfall order is already optimal (or not enough data to recommend changes).")
