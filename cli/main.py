"""Clay-Dupe CLI -- Typer-based command-line interface for enrichment.

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
from data.io import read_input_file, ColumnMapper, apply_mapping, export_results
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
from providers.base import BaseProvider

# Allow asyncio.run() inside Typer callbacks (which may already have a loop)
nest_asyncio.apply()

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="clay-dupe",
    help="Clay-Dupe enrichment platform CLI.",
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


def _build_providers(settings: Settings) -> dict[ProviderName, BaseProvider]:
    """Build a mapping of ProviderName to initialised provider instances."""
    provider_classes: dict[ProviderName, type[BaseProvider]] = {
        ProviderName.APOLLO: ApolloProvider,
        ProviderName.FINDYMAIL: FindymailProvider,
        ProviderName.ICYPEAS: IcypeasProvider,
        ProviderName.CONTACTOUT: ContactOutProvider,
    }
    providers: dict[ProviderName, BaseProvider] = {}
    for pname, pconfig in settings.providers.items():
        if not pconfig.enabled:
            continue
        cls = provider_classes.get(pname)
        if cls is None:
            continue
        providers[pname] = cls(api_key=pconfig.api_key)
    return providers


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

    # --- Cost estimate ---
    providers = _build_providers(settings)
    cost_tracker = CostTracker(db)
    cache_mgr = CacheManager(db)

    records = apply_mapping(df, mapper.mapping)
    cache_stats = run_sync(cache_mgr.get_stats())

    estimate = run_sync(cost_tracker.estimate_campaign_cost(
        total_rows=len(records),
        cached_rows=cache_stats.get("active_entries", 0),
        waterfall_order=settings.waterfall_order,
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
        waterfall_order=settings.waterfall_order,
        column_mapping=mapper.mapping,
        status=CampaignStatus.CREATED,
        total_rows=len(records),
    )
    campaign = run_sync(db.create_campaign(campaign))
    run_sync(db.create_campaign_rows(campaign.id, records))
    run_sync(db.update_campaign_status(campaign.id, CampaignStatus.RUNNING))

    # --- Run enrichment ---
    async def _run_enrichment() -> tuple[list[Person], dict, dict]:
        verifier = EmailVerifier()
        budget_mgr = BudgetManager(db)
        pattern_engine = PatternEngine(db, verifier)

        # Apply budget limits from settings
        for pname, pconfig in settings.providers.items():
            if pconfig.daily_credit_limit is not None:
                budget_mgr.set_daily_limit(pname, pconfig.daily_credit_limit)
            if pconfig.monthly_credit_limit is not None:
                budget_mgr.set_monthly_limit(pname, pconfig.monthly_credit_limit)

        enriched_people: list[Person] = []
        companies: dict[str, object] = {}
        enrichment_meta: dict[str, dict] = {}

        total = len(records)
        found_count = 0
        failed_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            console=console,
        ) as progress:
            task = progress.add_task("Enriching...", total=total)

            pending_rows = await db.get_pending_rows(campaign.id, limit=total)

            for row_data in pending_rows:
                row_input = row_data.get("input_data", row_data)
                if isinstance(row_input, str):
                    import json
                    try:
                        row_input = json.loads(row_input)
                    except (ValueError, TypeError):
                        row_input = {}

                first_name = row_input.get("first_name", "")
                last_name = row_input.get("last_name", "")
                domain = row_input.get("company_domain", "") or row_input.get("domain", "")
                company_name = row_input.get("company_name", "")

                # Split full_name if first/last not present
                if not first_name and row_input.get("full_name"):
                    parts = row_input["full_name"].split(None, 1)
                    first_name = parts[0] if parts else ""
                    last_name = parts[1] if len(parts) > 1 else ""

                if not first_name or not (domain or company_name):
                    failed_count += 1
                    await db.update_campaign_row(
                        row_data["id"], "skipped", error="Insufficient data",
                    )
                    progress.advance(task)
                    continue

                email_found = None

                # Try pattern engine first (free)
                try:
                    if domain:
                        email_found = await pattern_engine.try_pattern_match(
                            first_name, last_name, domain,
                        )
                except Exception:
                    logger.debug("Pattern match failed", exc_info=True)

                # Try cache
                if not email_found and domain:
                    cached = await cache_mgr.get(
                        "any", "email_lookup",
                        {"first_name": first_name, "last_name": last_name, "domain": domain},
                    )
                    if cached and cached.get("email"):
                        email_found = cached["email"]

                # Waterfall through providers
                if not email_found:
                    lookup_domain = domain or company_name
                    for pname in settings.waterfall_order:
                        provider = providers.get(pname)
                        if provider is None:
                            continue
                        if not await budget_mgr.can_spend(pname, 1.0, campaign.id):
                            continue

                        try:
                            resp = await provider.find_email(
                                first_name, last_name, lookup_domain,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Provider %s failed: %s", pname.value, exc,
                            )
                            continue

                        await budget_mgr.record_spend(
                            pname, resp.credits_used,
                            campaign_id=campaign.id, found=resp.found,
                        )

                        if resp.found and resp.email:
                            email_found = resp.email

                            # Cache the result
                            await cache_mgr.set(
                                pname.value, "email_lookup",
                                {"first_name": first_name, "last_name": last_name, "domain": domain},
                                {"email": resp.email, "provider": pname.value},
                                found=True,
                            )

                            # Learn pattern
                            if domain:
                                await pattern_engine.learn_pattern(
                                    resp.email, first_name, last_name, domain,
                                )
                            break
                        else:
                            # Negative cache
                            await cache_mgr.set(
                                pname.value, "email_lookup",
                                {"first_name": first_name, "last_name": last_name, "domain": domain},
                                {"email": None, "provider": pname.value},
                                found=False,
                            )

                # Build person
                person = Person(
                    first_name=first_name,
                    last_name=last_name,
                    email=email_found,
                    company_name=company_name or None,
                    company_domain=domain or None,
                    title=row_input.get("title"),
                    linkedin_url=row_input.get("linkedin_url"),
                    city=row_input.get("city"),
                    state=row_input.get("state"),
                    country=row_input.get("country"),
                )
                person = await db.upsert_person(person)
                enriched_people.append(person)

                if email_found:
                    found_count += 1
                    await db.update_campaign_row(
                        row_data["id"], "completed", person_id=person.id,
                    )
                else:
                    await db.update_campaign_row(
                        row_data["id"], "completed", person_id=person.id,
                        error="No email found",
                    )

                enrichment_meta[person.id] = {
                    "source_provider": "",
                    "confidence_score": None,
                    "verification_status": "unknown",
                    "waterfall_position": None,
                    "found_at": None,
                    "cost_credits": 0,
                    "from_cache": False,
                }

                progress.advance(task)

        await db.update_campaign_status(
            campaign.id,
            CampaignStatus.COMPLETED,
            enriched_rows=len(enriched_people),
            found_rows=found_count,
            failed_rows=failed_count,
        )

        return enriched_people, companies, enrichment_meta

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
        result = verifier.verify(email)

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
