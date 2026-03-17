"""Provider A/B testing framework — shadow mode waterfall comparison.

Runs an alternative waterfall configuration in parallel with the
production configuration.  The production result is always returned
unchanged; the shadow result is logged for offline analysis.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from data.database import Database
    from enrichment.waterfall import WaterfallOrchestrator

from config.settings import ProviderName
from data.models import EnrichmentResult

logger = logging.getLogger(__name__)


@dataclass
class ABTestConfig:
    """Configuration for an A/B test between two waterfall orders."""

    name: str
    control_order: list[ProviderName]
    variant_order: list[ProviderName]
    enabled: bool = True
    # Fraction of rows to shadow-test (0.0 – 1.0).
    sample_rate: float = 1.0


@dataclass
class ABTestResult:
    """Comparison result for a single row."""

    row_input: dict
    control_found: bool
    variant_found: bool
    control_provider: Optional[str] = None
    variant_provider: Optional[str] = None
    control_credits: float = 0.0
    variant_credits: float = 0.0
    control_time_ms: int = 0
    variant_time_ms: int = 0


@dataclass
class ABTestReport:
    """Aggregate report for an A/B test run."""

    config_name: str
    total_rows: int = 0
    control_hits: int = 0
    variant_hits: int = 0
    both_hit: int = 0
    control_only: int = 0
    variant_only: int = 0
    neither: int = 0
    control_total_credits: float = 0.0
    variant_total_credits: float = 0.0
    results: list[ABTestResult] = field(default_factory=list)

    @property
    def control_hit_rate(self) -> float:
        return self.control_hits / self.total_rows * 100 if self.total_rows else 0.0

    @property
    def variant_hit_rate(self) -> float:
        return self.variant_hits / self.total_rows * 100 if self.total_rows else 0.0


class ABTestRunner:
    """Runs shadow-mode A/B tests alongside production enrichment."""

    def __init__(self, db: Database):
        self.db = db
        self._active_tests: dict[str, ABTestConfig] = {}

    def register_test(self, config: ABTestConfig) -> None:
        """Register an A/B test configuration."""
        self._active_tests[config.name] = config
        logger.info("Registered A/B test: %s", config.name)

    def remove_test(self, name: str) -> None:
        """Remove an A/B test."""
        self._active_tests.pop(name, None)

    def get_active_tests(self) -> list[ABTestConfig]:
        """Return all active test configs."""
        return [t for t in self._active_tests.values() if t.enabled]

    async def run_shadow(
        self,
        orchestrator: WaterfallOrchestrator,
        row: dict,
        production_result: EnrichmentResult,
        campaign_id: Optional[str] = None,
    ) -> None:
        """Run all active shadow tests for a single row.

        Runs asynchronously without blocking the production pipeline.
        Results are logged to the audit trail for later analysis.
        """
        for test_config in self.get_active_tests():
            import random
            if random.random() > test_config.sample_rate:
                continue

            try:
                start = time.monotonic()
                # Shadow run uses the variant waterfall order
                shadow_result = await orchestrator.enrich_single(
                    row, campaign_id=campaign_id,
                )
                elapsed = int((time.monotonic() - start) * 1000)

                ab_result = ABTestResult(
                    row_input=row,
                    control_found=production_result.found,
                    variant_found=shadow_result.found,
                    control_provider=production_result.source_provider.value,
                    variant_provider=shadow_result.source_provider.value,
                    control_credits=production_result.cost_credits,
                    variant_credits=shadow_result.cost_credits,
                    control_time_ms=production_result.response_time_ms or 0,
                    variant_time_ms=elapsed,
                )

                # Log to audit trail
                await self.db.log_action(
                    action="ab_test_shadow",
                    entity_type="enrichment",
                    details={
                        "test_name": test_config.name,
                        "control_found": ab_result.control_found,
                        "variant_found": ab_result.variant_found,
                        "control_provider": ab_result.control_provider,
                        "variant_provider": ab_result.variant_provider,
                        "control_credits": ab_result.control_credits,
                        "variant_credits": ab_result.variant_credits,
                        "campaign_id": campaign_id,
                    },
                )

            except Exception:
                logger.debug(
                    "A/B test shadow run failed for test %s",
                    test_config.name,
                    exc_info=True,
                )

    async def generate_report(self, test_name: str) -> ABTestReport:
        """Generate an aggregate report from audit log entries."""
        report = ABTestReport(config_name=test_name)

        # Query audit log for shadow results
        async with self.db._read() as conn:
            cursor = await conn.execute(
                """SELECT details FROM audit_log
                   WHERE action = 'ab_test_shadow'
                   ORDER BY timestamp DESC
                   LIMIT 10000""",
            )
            rows = await cursor.fetchall()

        import json
        for row in rows:
            try:
                details = json.loads(row["details"]) if isinstance(row["details"], str) else row["details"]
            except (json.JSONDecodeError, TypeError):
                continue

            if details.get("test_name") != test_name:
                continue

            report.total_rows += 1
            ctrl = details.get("control_found", False)
            var = details.get("variant_found", False)

            if ctrl:
                report.control_hits += 1
            if var:
                report.variant_hits += 1
            if ctrl and var:
                report.both_hit += 1
            elif ctrl:
                report.control_only += 1
            elif var:
                report.variant_only += 1
            else:
                report.neither += 1

            report.control_total_credits += details.get("control_credits", 0)
            report.variant_total_credits += details.get("variant_credits", 0)

        return report
