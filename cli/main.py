"""Permanent Enrichment Tool CLI -- Typer-based command-line interface.

Commands
--------
- ``enrich``  : Import CSV, auto-detect columns, run waterfall, export.
- ``search``  : Search Apollo for companies/people by ICP preset or filters.
- ``verify``  : Verify a single email address.
- ``stats``   : Show credit usage, hit rates, and cache statistics.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import nest_asyncio
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.table import Table
from rich.panel import Panel
from rich import box

from config.settings import load_settings, ProviderName, Settings, ICP_PRESETS
from data.database import Database
from data.io import read_input_file, ColumnMapper, apply_mapping, export_results, deduplicate_rows
from data.models import (
    Campaign,
    CampaignStatus,
    EnrichmentType,
    Person,
)
from enrichment.pattern_engine import PatternEngine
from quality.verification import EmailVerifier
from quality.circuit_breaker import create_rate_limiters, create_circuit_breakers
from cost.budget import BudgetManager
from cost.tracker import CostTracker
from cost.cache import CacheManager
from data.sync import run_sync
from providers.apollo import ApolloProvider
from providers.findymail import FindymailProvider
from providers.icypeas import IcypeasProvider
from providers.contactout import ContactOutProvider
from providers.datagma import DatagmaProvider
from providers.base import BaseProvider

# Allow asyncio.run() inside Typer callbacks (which may already have a loop)
nest_asyncio.apply()

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="permanent-enrich",
    help="Permanent Enrichment Tool CLI.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# Shared bootstrap helpers
# ---------------------------------------------------------------------------

def _load_settings_safe() -> Settings:
    """Load settings, printing a friendly error on failure."""
    try:
        return load_settings()
    except Exception as exc:
        console.print(f"[bold red]Failed to load settings:[/] {exc}")
        raise typer.Exit(code=1)


def _init_db(settings: Settings) -> Database:
    """Initialise and return the database."""
    try:
        return Database(db_path=settings.db_path)
    except Exception as exc:
        console.print(f"[bold red]Database initialisation failed:[/] {exc}")
        raise typer.Exit(code=1)


PROVIDER_CLASSES: dict[ProviderName, type[BaseProvider]] = {
    ProviderName.APOLLO: ApolloProvider,
    ProviderName.FINDYMAIL: FindymailProvider,
    ProviderName.ICYPEAS: IcypeasProvider,
    ProviderName.CONTACTOUT: ContactOutProvider,
    ProviderName.DATAGMA: DatagmaProvider,
}


def _build_providers(settings: Settings) -> dict[ProviderName, BaseProvider]:
    """Build a mapping of ProviderName to initialised provider instances.

    Only builds providers that are enabled AND have an API key configured.
    """
    enabled = set(settings.get_enabled_providers())
    providers: dict[ProviderName, BaseProvider] = {}
    for pname, pconfig in settings.providers.items():
        if pname not in enabled:
            continue
        cls = PROVIDER_CLASSES.get(pname)
        if cls is None:
            continue
        providers[pname] = cls(api_key=pconfig.api_key)
    return providers


async def _run_health_checks(
    providers: dict[ProviderName, BaseProvider],
    settings: Settings,
) -> dict[ProviderName, str]:
    """Run health checks on all configured providers.

    Returns a dict of ProviderName -> status string for display.
    """
    results: dict[ProviderName, str] = {}

    # Report providers with no key configured
    for pname in ProviderName:
        pcfg = settings.providers.get(pname)
        if pcfg is None or not pcfg.enabled:
            continue
        if not pcfg.api_key:
            results[pname] = "No key configured"

    # Health-check providers that were built (have keys)
    for pname, provider in providers.items():
        try:
            ok = await provider.health_check()
            results[pname] = "OK" if ok else "Health check failed"
        except Exception as exc:
            results[pname] = f"Error ({exc})"

    return results


async def _close_providers(providers: dict[ProviderName, BaseProvider]) -> None:
    """Gracefully close all provider HTTP clients."""
    for provider in providers.values():
        try:
            await provider.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# enrich command
# ---------------------------------------------------------------------------

@app.command()
def enrich(
    input_file: Path = typer.Argument(
        ...,
        help="Path to input CSV or Excel file.",
        exists=True,
        readable=True,
    ),
    output: Path = typer.Option(
        Path("enriched_output.csv"),
        "--output", "-o",
        help="Output file path.",
    ),
    output_format: str = typer.Option(
        "csv",
        "--format", "-f",
        help="Output format: csv or excel.",
    ),
    campaign_name: Optional[str] = typer.Option(
        None,
        "--name", "-n",
        help="Campaign name (auto-generated if omitted).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show column mapping and cost estimate without running.",
    ),
) -> None:
    """Import a CSV/Excel file, auto-detect columns, run the waterfall enrichment pipeline, and export results."""
    settings = _load_settings_safe()
    db = _init_db(settings)

    # --- Read input ---
    console.print(f"\n[bold]Reading input file:[/] {input_file}")
    try:
        df = read_input_file(input_file, filename=input_file.name)
    except Exception as exc:
        console.print(f"[bold red]Failed to read file:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"  Rows: {len(df):,}  |  Columns: {len(df.columns)}")

    # --- Auto-detect columns ---
    mapper = ColumnMapper(list(df.columns))
    summary = mapper.get_mapping_summary()
    validation = mapper.validate()

    mapping_table = Table(
        title="Column Mapping", box=box.ROUNDED, show_lines=True,
    )
    mapping_table.add_column("Input Column", style="cyan")
    mapping_table.add_column("Mapped To", style="green")
    mapping_table.add_column("Score", justify="right")

    for input_col, canonical in summary["mapped"].items():
        score = summary["scores"].get(input_col, "")
        style = "green" if score == 100 else "yellow"
        mapping_table.add_row(input_col, canonical, f"[{style}]{score}[/]")

    for unmapped_col in summary["unmapped"]:
        mapping_table.add_row(unmapped_col, "[dim]-- unmapped --[/]", "")

    console.print(mapping_table)
    console.print(f"  Coverage: {summary['coverage']}%\n")

    if not validation["valid"]:
        console.print("[bold red]Validation failed:[/]")
        for msg in validation["missing"]:
            console.print(f"  - Missing: {msg}")
        raise typer.Exit(code=1)

    for warning in validation.get("warnings", []):
        console.print(f"  [yellow]Warning:[/] {warning}")

    # --- Build providers & health check ---
    providers = _build_providers(settings)
    valid_waterfall = settings.validate_waterfall_order()

    if not providers:
        console.print(
            "[bold red]No providers available.[/] "
            "All providers are missing API keys or are disabled.\n"
            "Configure keys in your .env file (e.g. APOLLO_API_KEY=...)."
        )
        raise typer.Exit(code=1)

    # Run health checks and display summary
    health = asyncio.run(_run_health_checks(providers, settings))
    status_parts = []
    healthy_providers: set[ProviderName] = set()
    for pname in ProviderName:
        pcfg = settings.providers.get(pname)
        if pcfg is None or not pcfg.enabled:
            continue
        status = health.get(pname, "Disabled")
        if status == "OK":
            style = "green"
            healthy_providers.add(pname)
        elif status == "No key configured":
            style = "yellow"
        else:
            style = "red"
        status_parts.append(f"{pname.value}: [{style}]{status}[/]")

    console.print(f"\n[bold]Provider status:[/]  {'  |  '.join(status_parts)}")

    # Filter waterfall to only healthy providers
    valid_waterfall = [p for p in valid_waterfall if p in healthy_providers]
    if not valid_waterfall:
        console.print(
            "[bold red]No healthy providers available for enrichment.[/] "
            "Check your API keys and provider status above."
        )
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=1)

    # --- Cost estimate ---
    cost_tracker = CostTracker(db)
    cache_mgr = CacheManager(db)

    records = apply_mapping(df, mapper.mapping)
    records, dupe_count = deduplicate_rows(records)
    if dupe_count > 0:
        console.print(f"[yellow]Removed {dupe_count} duplicate rows[/yellow]")
    cache_stats = run_sync(cache_mgr.get_stats())

    estimate = run_sync(cost_tracker.estimate_campaign_cost(
        total_rows=len(records),
        cached_rows=cache_stats.get("active_entries", 0),
        waterfall_order=valid_waterfall,
    ))

    est_table = Table(title="Cost Estimate", box=box.SIMPLE)
    est_table.add_column("Provider", style="cyan")
    est_table.add_column("Est. Lookups", justify="right")
    est_table.add_column("Est. Finds", justify="right")
    est_table.add_column("Est. Credits", justify="right")
    est_table.add_column("Est. Cost (USD)", justify="right")

    for prov_name, prov_est in estimate.get("per_provider", {}).items():
        est_table.add_row(
            prov_name,
            str(prov_est["estimated_lookups"]),
            str(prov_est["estimated_finds"]),
            str(prov_est["estimated_credits"]),
            f"${prov_est['estimated_cost_usd']:.4f}",
        )

    est_table.add_section()
    est_table.add_row(
        "[bold]Total[/]",
        str(estimate["rows_to_enrich"]),
        "",
        str(estimate["total_estimated_credits"]),
        f"[bold]${estimate['total_estimated_cost_usd']:.4f}[/]",
    )
    console.print(est_table)

    if dry_run:
        console.print("\n[dim]Dry run -- no enrichment performed.[/]")
        asyncio.run(_close_providers(providers))
        return

    # --- Confirm ---
    if not typer.confirm("\nProceed with enrichment?", default=True):
        console.print("[dim]Aborted.[/]")
        asyncio.run(_close_providers(providers))
        return

    # --- Create campaign ---
    name = campaign_name or f"CLI - {input_file.stem}"
    campaign = Campaign(
        name=name,
        input_file=str(input_file),
        input_row_count=len(records),
        enrichment_types=[EnrichmentType.EMAIL],
        waterfall_order=valid_waterfall,
        column_mapping=mapper.mapping,
        status=CampaignStatus.CREATED,
        total_rows=len(records),
    )
    campaign = run_sync(db.create_campaign(campaign))
    run_sync(db.create_campaign_rows(campaign.id, records))
    run_sync(db.update_campaign_status(campaign.id, CampaignStatus.RUNNING))

    # --- Run enrichment via WaterfallOrchestrator ---
    async def _run_enrichment() -> tuple[list[Person], dict, dict]:
        from enrichment.waterfall import WaterfallOrchestrator

        verifier = EmailVerifier()
        budget_mgr = BudgetManager(db)
        pattern_engine = PatternEngine(db, verifier)
        cost_tracker = CostTracker(db)
        circuit_breakers = create_circuit_breakers()
        rate_limiters = create_rate_limiters()

        # Apply budget limits from settings
        for pname, pconfig in settings.providers.items():
            if pconfig.daily_credit_limit is not None:
                budget_mgr.set_daily_limit(pname, pconfig.daily_credit_limit)
            if pconfig.monthly_credit_limit is not None:
                budget_mgr.set_monthly_limit(pname, pconfig.monthly_credit_limit)

        orchestrator = WaterfallOrchestrator(
            db=db,
            providers=providers,
            pattern_engine=pattern_engine,
            budget=budget_mgr,
            circuit_breakers=circuit_breakers,
            rate_limiters=rate_limiters,
            cost_tracker=cost_tracker,
            waterfall_order=valid_waterfall,
            verifier=verifier,
        )

        total = len(records)
        enriched_people: list[Person] = []
        enrichment_meta: dict[str, dict] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=console,
        ) as progress:
            task = progress.add_task("Enriching...", total=total)

            def _progress_cb(completed: int, total_rows: int, result) -> None:
                progress.update(task, completed=completed)

            # Get campaign row IDs for per-row status tracking
            pending_rows = await db.get_pending_rows(campaign.id, limit=total)
            row_ids = [r["id"] for r in pending_rows]

            results = await orchestrator.enrich_batch(
                rows=records,
                campaign_id=campaign.id,
                progress_callback=_progress_cb,
                campaign_row_ids=row_ids,
            )

        found_count = 0
        failed_count = 0
        for result in results:
            if result.found:
                found_count += 1
            else:
                failed_count += 1

            # Build person from result for export
            person_id = result.person_id
            if person_id:
                try:
                    person = await db.get_person(person_id)
                    if person:
                        enriched_people.append(person)
                        enrichment_meta[person.id] = {
                            "source_provider": result.source_provider.value if result.source_provider else "",
                            "confidence_score": result.confidence_score,
                            "verification_status": result.verification_status.value if result.verification_status else "unknown",
                            "waterfall_position": result.waterfall_position,
                            "found_at": result.found_at.isoformat() if hasattr(result, "found_at") and result.found_at else None,
                            "cost_credits": result.cost_credits,
                            "from_cache": result.from_cache,
                        }
                        continue
                except Exception:
                    pass

            # Fallback: build person from input row if no person_id
            idx = results.index(result)
            if idx < len(records):
                row_input = records[idx]
                person = Person(
                    first_name=row_input.get("first_name", ""),
                    last_name=row_input.get("last_name", ""),
                    email=result.result_data.get("email") if result.found else None,
                    company_name=row_input.get("company_name"),
                    company_domain=row_input.get("company_domain"),
                    title=row_input.get("title"),
                    linkedin_url=row_input.get("linkedin_url"),
                )
                enriched_people.append(person)
                enrichment_meta[person.id] = {
                    "source_provider": result.source_provider.value if result.source_provider else "",
                    "confidence_score": result.confidence_score,
                    "verification_status": result.verification_status.value if result.verification_status else "unknown",
                    "waterfall_position": result.waterfall_position,
                    "cost_credits": result.cost_credits,
                    "from_cache": result.from_cache,
                }

        await db.update_campaign_status(
            campaign.id,
            CampaignStatus.COMPLETED,
            enriched_rows=len(enriched_people),
            found_rows=found_count,
            failed_rows=failed_count,
        )

        return enriched_people, {}, enrichment_meta

    try:
        people, companies, meta = asyncio.run(_run_enrichment())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted -- saving partial results.[/]")
        run_sync(db.update_campaign_status(campaign.id, CampaignStatus.CANCELLED))
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=130)
    except Exception as exc:
        console.print(f"\n[bold red]Enrichment failed:[/] {exc}")
        run_sync(db.update_campaign_status(campaign.id, CampaignStatus.FAILED))
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=1)
    finally:
        asyncio.run(_close_providers(providers))

    # --- Export ---
    if people:
        out_path = export_results(people, companies, meta, output, format=output_format)
        console.print(f"\n[bold green]Results exported to:[/] {out_path}")

    # --- Summary ---
    found = sum(1 for p in people if p.email)
    total = len(people)
    rate = (found / total * 100) if total > 0 else 0.0

    summary_panel = Panel(
        f"Total: {total}  |  Found: {found}  |  Rate: {rate:.1f}%\n"
        f"Campaign: {campaign.id}",
        title="Enrichment Complete",
        border_style="green",
    )
    console.print(summary_panel)


# ---------------------------------------------------------------------------
# search command
# ---------------------------------------------------------------------------

@app.command()
def search(
    target: str = typer.Argument(
        ...,
        help="Search target: 'companies' or 'people'.",
    ),
    preset: Optional[str] = typer.Option(
        None,
        "--preset", "-p",
        help=f"ICP preset name: {', '.join(ICP_PRESETS.keys())}",
    ),
    industry: Optional[str] = typer.Option(None, "--industry", "-i"),
    country: Optional[str] = typer.Option(None, "--country", "-c"),
    employee_min: Optional[int] = typer.Option(None, "--emp-min"),
    employee_max: Optional[int] = typer.Option(None, "--emp-max"),
    title: Optional[str] = typer.Option(None, "--title", "-t", help="Person title filter (people search only)."),
    seniority: Optional[str] = typer.Option(None, "--seniority", "-s", help="Seniority level (people search only)."),
    domain: Optional[str] = typer.Option(None, "--domain", "-d", help="Company domain (people search only)."),
    page: int = typer.Option(1, "--page"),
    per_page: int = typer.Option(25, "--per-page"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Export results to CSV."),
) -> None:
    """Search Apollo for companies or people by ICP preset or custom filters."""
    if target not in ("companies", "people"):
        console.print("[bold red]Target must be 'companies' or 'people'.[/]")
        raise typer.Exit(code=1)

    settings = _load_settings_safe()
    providers = _build_providers(settings)

    apollo = providers.get(ProviderName.APOLLO)
    if apollo is None:
        console.print("[bold red]Apollo provider is not configured or enabled.[/]")
        raise typer.Exit(code=1)

    # Build filters from preset or CLI options
    filters: dict = {"page": page, "per_page": per_page}

    if preset:
        if preset not in ICP_PRESETS:
            console.print(
                f"[bold red]Unknown preset '{preset}'.[/] Available: {', '.join(ICP_PRESETS.keys())}",
            )
            raise typer.Exit(code=1)
        icp = ICP_PRESETS[preset]
        console.print(f"[bold]Using ICP preset:[/] {icp.display_name}")

        if target == "companies":
            filters["q_organization_keyword_tags"] = icp.keywords or icp.industries
            filters["organization_locations"] = icp.countries
            emp_range = f"{icp.employee_min},{icp.employee_max}"
            filters["organization_num_employees_ranges"] = [emp_range]
        else:
            filters["organization_locations"] = icp.countries
            emp_range = f"{icp.employee_min},{icp.employee_max}"
            filters["organization_num_employees_ranges"] = [emp_range]
    else:
        if country:
            filters["organization_locations"] = [country]
        if employee_min is not None or employee_max is not None:
            emp_min = employee_min or 1
            emp_max = employee_max or 1000000
            filters["organization_num_employees_ranges"] = [f"{emp_min},{emp_max}"]

    # People-specific filters
    if target == "people":
        if title:
            filters["person_titles"] = [title]
        if seniority:
            filters["person_seniorities"] = [seniority]
        if domain:
            filters["q_organization_domains_list"] = [domain]

    async def _search():
        try:
            if target == "companies":
                return await apollo.search_companies(**filters)
            else:
                return await apollo.search_people(**filters)
        finally:
            await _close_providers(providers)

    console.print(f"\n[bold]Searching Apollo for {target}...[/]\n")

    try:
        results = asyncio.run(_search())
    except Exception as exc:
        console.print(f"[bold red]Search failed:[/] {exc}")
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=1)

    if not results:
        console.print("[dim]No results found.[/]")
        return

    console.print(f"Found [bold]{len(results)}[/] {target}.\n")

    # Display results
    if target == "companies":
        table = Table(title=f"Companies (page {page})", box=box.ROUNDED)
        table.add_column("Name", style="cyan", max_width=30)
        table.add_column("Domain", style="green")
        table.add_column("Industry")
        table.add_column("Employees", justify="right")
        table.add_column("Country")

        for c in results:
            table.add_row(
                c.name or "",
                c.domain or "",
                c.industry or "",
                str(c.employee_count) if c.employee_count else "",
                c.country or "",
            )
    else:
        table = Table(title=f"People (page {page})", box=box.ROUNDED)
        table.add_column("Name", style="cyan", max_width=25)
        table.add_column("Title", max_width=30)
        table.add_column("Company", style="green")
        table.add_column("LinkedIn")

        for p in results:
            table.add_row(
                p.full_name or "",
                p.title or "",
                p.company_name or "",
                p.linkedin_url or "",
            )

    console.print(table)

    # Optional CSV export
    if output:
        import pandas as pd
        rows = [
            (r.model_dump() if hasattr(r, "model_dump") else vars(r))
            for r in results
        ]
        df = pd.DataFrame(rows)
        # Normalise enum values
        for col in df.columns:
            df[col] = df[col].apply(lambda v: v.value if hasattr(v, "value") else v)
        df.to_csv(output, index=False)
        console.print(f"\n[bold green]Exported to:[/] {output}")


# ---------------------------------------------------------------------------
# verify command
# ---------------------------------------------------------------------------

@app.command()
def verify(
    email: str = typer.Argument(..., help="Email address to verify."),
) -> None:
    """Verify a single email address using DNS + SMTP probing."""
    console.print(f"\n[bold]Verifying:[/] {email}\n")

    verifier = EmailVerifier()

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Running verification pipeline...")
        result = run_sync(verifier.verify(email))

    # Build result table
    table = Table(box=box.ROUNDED, show_header=False, title="Verification Result")
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    valid_style = "green" if result.get("valid") else "red"
    table.add_row("Email", email)
    table.add_row("Valid", f"[{valid_style}]{result.get('valid')}[/]")
    table.add_row("MX Found", str(result.get("mx_found", False)))
    table.add_row("Catch-All", str(result.get("catch_all", False)))
    table.add_row("SMTP Result", result.get("smtp_result", "unknown"))
    table.add_row("Confidence Modifier", str(result.get("confidence_modifier", 0)))

    console.print(table)


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------

@app.command()
def stats(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back."),
) -> None:
    """Show credit usage, hit rates, and cache statistics."""
    settings = _load_settings_safe()
    db = _init_db(settings)
    cost_tracker = CostTracker(db)
    cache_mgr = CacheManager(db)
    budget_mgr = BudgetManager(db)

    # --- Dashboard stats ---
    dash = run_sync(db.get_dashboard_stats())
    dash_panel = Panel(
        f"People Enriched: [bold]{dash['total_enriched']:,}[/]\n"
        f"Email Find Rate: [bold]{dash['email_find_rate']}%[/]\n"
        f"Campaigns: [bold]{dash['total_campaigns']}[/]\n"
        f"Credits (30d): [bold]{dash['cost_30d']:.1f}[/]",
        title="Dashboard",
        border_style="blue",
    )
    console.print(dash_panel)

    # --- Provider stats ---
    provider_stats = run_sync(cost_tracker.get_all_provider_stats(days=days))

    if provider_stats:
        prov_table = Table(
            title=f"Provider Stats (last {days} days)", box=box.ROUNDED,
        )
        prov_table.add_column("Provider", style="cyan")
        prov_table.add_column("Lookups", justify="right")
        prov_table.add_column("Found", justify="right")
        prov_table.add_column("Hit Rate", justify="right")
        prov_table.add_column("Credits", justify="right")
        prov_table.add_column("Cost (USD)", justify="right")
        prov_table.add_column("Marginal", justify="right")
        prov_table.add_column("Avg ms", justify="right")

        for pname, ps in provider_stats.items():
            hit_style = "green" if ps["hit_rate"] >= 50 else ("yellow" if ps["hit_rate"] >= 25 else "red")
            prov_table.add_row(
                pname,
                str(ps["total_lookups"]),
                str(ps["found_count"]),
                f"[{hit_style}]{ps['hit_rate']}%[/]",
                str(ps["total_credits"]),
                f"${ps['total_cost_usd']:.4f}",
                str(ps["marginal_finds"]),
                str(ps["avg_response_ms"]) if ps["avg_response_ms"] else "-",
            )
        console.print(prov_table)

        # Waterfall recommendation
        recommendation = run_sync(cost_tracker.get_waterfall_recommendation())
        if recommendation:
            rec_order = " -> ".join(p.value for p in recommendation)
            console.print(
                Panel(
                    f"Recommended waterfall order: [bold]{rec_order}[/]\n"
                    "This reordering could save >15% on costs.",
                    title="Optimization Suggestion",
                    border_style="yellow",
                )
            )
    else:
        console.print("[dim]No provider activity in the selected period.[/]")

    # --- Budget balances ---
    budget_table = Table(title="Budget Balances", box=box.SIMPLE)
    budget_table.add_column("Provider", style="cyan")
    budget_table.add_column("Daily Used", justify="right")
    budget_table.add_column("Daily Limit", justify="right")
    budget_table.add_column("Monthly Used", justify="right")
    budget_table.add_column("Monthly Limit", justify="right")
    budget_table.add_column("Status")

    for pname in ProviderName:
        balance = run_sync(budget_mgr.get_balance(pname))
        status_parts = []
        if balance["at_daily_cap"]:
            status_parts.append("[red]Daily cap[/]")
        if balance["at_monthly_cap"]:
            status_parts.append("[red]Monthly cap[/]")
        status_str = ", ".join(status_parts) if status_parts else "[green]OK[/]"

        budget_table.add_row(
            pname.value,
            f"{balance['daily_used']:.1f}",
            str(balance["daily_limit"]) if balance["daily_limit"] is not None else "-",
            f"{balance['monthly_used']:.1f}",
            str(balance["monthly_limit"]) if balance["monthly_limit"] is not None else "-",
            status_str,
        )

    console.print(budget_table)

    # --- Cache stats ---
    cs = run_sync(cache_mgr.get_stats())
    cache_table = Table(title="Cache Statistics", box=box.ROUNDED)
    cache_table.add_column("Metric", style="bold cyan")
    cache_table.add_column("Value", justify="right")

    cache_table.add_row("Total Entries", f"{cs['total_entries']:,}")
    cache_table.add_row("Active Entries", f"{cs['active_entries']:,}")
    cache_table.add_row("Expired Entries", f"{cs['expired_entries']:,}")
    cache_table.add_row("Total Hits", f"{cs['total_hits']:,}")
    cache_table.add_row("Hit Rate", f"{cs['hit_rate']}%")
    cache_table.add_row("Oldest Entry", str(cs.get("oldest_entry") or "-"))
    cache_table.add_row("Newest Entry", str(cs.get("newest_entry") or "-"))

    console.print(cache_table)

    if cs["by_type"]:
        type_table = Table(title="Cache by Type", box=box.SIMPLE)
        type_table.add_column("Data Type", style="cyan")
        type_table.add_column("Active Entries", justify="right")
        type_table.add_column("TTL (days)", justify="right")
        for dtype, count in cs["by_type"].items():
            type_table.add_row(dtype, str(count), str(cache_mgr.get_ttl(dtype)))
        console.print(type_table)

    if cs["by_provider"]:
        provider_cache_table = Table(title="Cache by Provider", box=box.SIMPLE)
        provider_cache_table.add_column("Provider", style="cyan")
        provider_cache_table.add_column("Active Entries", justify="right")
        for prov, count in cs["by_provider"].items():
            provider_cache_table.add_row(prov, str(count))
        console.print(provider_cache_table)

    # --- TTL policies ---
    ttl_table = Table(title="TTL Policies", box=box.SIMPLE)
    ttl_table.add_column("Data Type", style="cyan")
    ttl_table.add_column("TTL (days)", justify="right")
    for dtype, ttl in cache_mgr.list_ttl_policies().items():
        ttl_table.add_row(dtype, str(ttl))
    console.print(ttl_table)


# ---------------------------------------------------------------------------
# resume command
# ---------------------------------------------------------------------------

@app.command()
def resume(
    campaign_id: str = typer.Argument(..., help="Campaign ID to resume."),
) -> None:
    """Resume a crashed or paused campaign.

    Resets any rows stuck in 'processing' back to 'pending', then
    re-runs the waterfall enrichment for all pending/failed rows.
    """
    settings = _load_settings_safe()
    db = _init_db(settings)
    providers = _build_providers(settings)

    # Validate campaign exists
    campaign = run_sync(db.get_campaign(campaign_id))
    if campaign is None:
        console.print(f"[bold red]Campaign not found:[/] {campaign_id}")
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=1)

    console.print(f"\n[bold]Resuming campaign:[/] {campaign.name}  ({campaign.id})")
    console.print(f"  Previous status: {campaign.status.value}")

    # Reset stuck rows
    stuck_count = run_sync(db.reset_stuck_rows(campaign_id))
    if stuck_count:
        console.print(f"  Reset [yellow]{stuck_count}[/] stuck 'processing' rows back to 'pending'.")

    # Show row stats before resuming
    row_stats = run_sync(db.get_campaign_row_stats(campaign_id))
    remaining = row_stats["pending"] + row_stats["failed"]
    console.print(
        f"  Rows — pending: {row_stats['pending']}, failed: {row_stats['failed']}, "
        f"complete: {row_stats['complete']}, processing: {row_stats['processing']}"
    )

    if remaining == 0:
        console.print("[green]Nothing to resume — all rows are already complete.[/]")
        asyncio.run(_close_providers(providers))
        return

    # Update campaign status to RUNNING
    run_sync(db.update_campaign_status(campaign_id, CampaignStatus.RUNNING))

    async def _run_resume() -> list:
        from enrichment.waterfall import WaterfallOrchestrator

        verifier = EmailVerifier()
        budget_mgr = BudgetManager(db)
        pattern_engine = PatternEngine(db, verifier)
        cost_tracker_inner = CostTracker(db)
        circuit_breakers = create_circuit_breakers()
        rate_limiters = create_rate_limiters()

        for pname, pconfig in settings.providers.items():
            if pconfig.daily_credit_limit is not None:
                budget_mgr.set_daily_limit(pname, pconfig.daily_credit_limit)
            if pconfig.monthly_credit_limit is not None:
                budget_mgr.set_monthly_limit(pname, pconfig.monthly_credit_limit)

        orchestrator = WaterfallOrchestrator(
            db=db,
            providers=providers,
            pattern_engine=pattern_engine,
            budget=budget_mgr,
            circuit_breakers=circuit_breakers,
            rate_limiters=rate_limiters,
            cost_tracker=cost_tracker_inner,
            waterfall_order=settings.waterfall_order,
            verifier=verifier,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=console,
        ) as progress:
            task = progress.add_task("Resuming enrichment...", total=remaining)

            def _progress_cb(completed: int, total_rows: int, result) -> None:
                progress.update(task, completed=completed)

            results = await orchestrator.resume_batch(
                campaign_id=campaign_id,
                progress_callback=_progress_cb,
            )

        return results

    try:
        results = asyncio.run(_run_resume())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted -- partial progress saved.[/]")
        run_sync(db.update_campaign_status(campaign_id, CampaignStatus.PAUSED))
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=130)
    except Exception as exc:
        console.print(f"\n[bold red]Resume failed:[/] {exc}")
        run_sync(db.update_campaign_status(campaign_id, CampaignStatus.FAILED))
        asyncio.run(_close_providers(providers))
        raise typer.Exit(code=1)
    finally:
        asyncio.run(_close_providers(providers))

    # Summary
    found = sum(1 for r in results if r.found)
    failed = sum(1 for r in results if not r.found)

    # Update final campaign status
    row_stats_final = run_sync(db.get_campaign_row_stats(campaign_id))
    if row_stats_final["pending"] == 0 and row_stats_final["processing"] == 0:
        run_sync(db.update_campaign_status(
            campaign_id, CampaignStatus.COMPLETED,
            enriched_rows=row_stats_final["complete"],
            found_rows=found,
            failed_rows=row_stats_final["failed"],
        ))
        final_status = "COMPLETED"
    else:
        final_status = "RUNNING (rows still remaining)"

    summary_panel = Panel(
        f"Processed: {len(results)}  |  Found: {found}  |  Failed: {failed}\n"
        f"Campaign status: {final_status}",
        title="Resume Complete",
        border_style="green",
    )
    console.print(summary_panel)


# ---------------------------------------------------------------------------
# list-campaigns command
# ---------------------------------------------------------------------------

@app.command(name="list-campaigns")
def list_campaigns(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of campaigns to show."),
    status_filter: Optional[str] = typer.Option(
        None, "--status", "-s",
        help="Filter by status (created, running, paused, completed, failed, cancelled).",
    ),
) -> None:
    """List recent campaigns with their status and progress."""
    settings = _load_settings_safe()
    db = _init_db(settings)

    campaigns = run_sync(db.get_recent_campaigns(limit=limit))

    if status_filter:
        status_filter_lower = status_filter.lower()
        campaigns = [c for c in campaigns if c.status.value == status_filter_lower]

    if not campaigns:
        console.print("[dim]No campaigns found.[/]")
        return

    table = Table(title="Campaigns", box=box.ROUNDED, show_lines=True)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="cyan", max_width=30)
    table.add_column("Status")
    table.add_column("Progress", justify="right")
    table.add_column("Created", max_width=19)

    for c in campaigns:
        # Colour-code status
        status_val = c.status.value
        if status_val == "completed":
            status_display = f"[green]{status_val}[/]"
        elif status_val in ("failed", "cancelled"):
            status_display = f"[red]{status_val}[/]"
        elif status_val == "running":
            status_display = f"[yellow]{status_val}[/]"
        elif status_val == "paused":
            status_display = f"[blue]{status_val}[/]"
        else:
            status_display = status_val

        # Progress info
        total = c.total_rows or 0
        enriched = c.enriched_rows or 0
        if total > 0:
            pct = enriched / total * 100
            progress_str = f"{enriched}/{total} ({pct:.0f}%)"
        else:
            progress_str = "-"

        # Truncate ID for display
        short_id = c.id[:8] + "..."

        created_str = c.created_at.strftime("%Y-%m-%d %H:%M") if c.created_at else "-"

        table.add_row(short_id, c.name, status_display, progress_str, created_str)

    console.print(table)

    # Hint about resumable campaigns
    resumable = [c for c in campaigns if c.status.value in ("failed", "paused", "running")]
    if resumable:
        console.print(
            f"\n[dim]Tip: {len(resumable)} campaign(s) can be resumed with:[/] "
            "[bold]permanent-enrich resume <campaign_id>[/]"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app()


if __name__ == "__main__":
    main()
