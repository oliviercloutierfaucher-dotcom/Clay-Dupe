# Codebase Structure

## Directory Layout

```
Clay-Dupe/
├── .env.example              # API key template
├── .gitignore                # Python/env ignores
├── API_SPECS.md              # Comprehensive API documentation (1,421 lines)
├── PLAN.md                   # Implementation phases and architecture
├── README.md                 # Project overview
├── requirements.txt          # Python dependencies
│
├── config/
│   ├── __init__.py
│   └── settings.py           # Pydantic-based app config, ICP presets, waterfall order
│
├── providers/                # API provider integrations (one file per provider)
│   ├── __init__.py
│   ├── base.py               # Abstract BaseProvider class + ProviderResponse dataclass
│   ├── apollo.py             # Apollo.io — company/people search, email enrichment
│   ├── findymail.py          # Findymail — email finding + verification
│   ├── icypeas.py            # Icypeas — cheap email discovery, bulk ops
│   └── contactout.py         # ContactOut — LinkedIn-based email extraction
│
├── enrichment/               # Core enrichment logic
│   ├── __init__.py
│   ├── waterfall.py          # Waterfall orchestrator (787 lines, main engine)
│   ├── classifier.py         # Row classification by available fields (bitfield signals)
│   ├── router.py             # Dynamic provider sequence per route category
│   ├── pattern_engine.py     # Email pattern discovery/learning (512 lines)
│   ├── email_finder.py       # Email finding pipeline wrapper
│   ├── domain_finder.py      # Domain lookup pipeline (STUB)
│   ├── linkedin_finder.py    # LinkedIn URL pipeline (STUB)
│   └── company_enricher.py   # Company data enrichment (STUB)
│
├── data/                     # Data handling
│   ├── __init__.py
│   ├── models.py             # Pydantic v2 models (Company, Person, EnrichmentResult, etc.)
│   ├── database.py           # SQLite with WAL mode — cache, credits, campaigns, audit
│   └── io.py                 # CSV/Excel import/export with fuzzy column mapping
│
├── cost/                     # Cost management
│   ├── __init__.py
│   ├── budget.py             # Per-provider daily/monthly budget limits
│   ├── tracker.py            # Historical cost analysis
│   └── cache.py              # Cache hit/miss tracking, cost savings calc
│
├── quality/                  # Quality management
│   ├── __init__.py
│   ├── confidence.py         # Multi-factor confidence scoring (0-100)
│   ├── circuit_breaker.py    # Per-provider circuit breaker (CLOSED/OPEN/HALF_OPEN)
│   ├── verification.py       # Email validation and verification
│   └── anti_pattern.py       # Catch-all domain and role-based email detection
│
├── cli/                      # Command-line interface
│   ├── __init__.py
│   └── main.py               # Typer CLI — enrich, search, verify, stats commands
│
├── ui/                       # Streamlit web interface
│   ├── app.py                # Main Streamlit app with multi-page navigation
│   ├── pages/
│   │   ├── dashboard.py      # Key metrics, recent campaigns
│   │   ├── search.py         # Apollo company/people search
│   │   ├── enrich.py         # CSV upload → enrichment wizard
│   │   ├── results.py        # Results browser + export
│   │   ├── analytics.py      # Credit usage analytics
│   │   └── settings.py       # API key management, waterfall config
│   └── components/
│       └── data_table.py     # Interactive data table component
│
└── tests/                    # Test suite
    ├── test_classifier.py    # Route classification tests (176 lines)
    ├── test_confidence.py    # Confidence scoring tests (178 lines)
    ├── test_database.py      # Database operations tests (195 lines)
    ├── test_io.py            # CSV/Excel I/O tests (104 lines)
    ├── test_models.py        # Pydantic model validation tests (165 lines)
    ├── test_pattern_engine.py # Pattern matching tests (191 lines)
    ├── test_providers.py     # Provider integration tests (252 lines)
    └── test_waterfall.py     # Waterfall orchestration tests (96 lines)
```

## Key Locations

| What | Where |
|---|---|
| Main engine | `enrichment/waterfall.py` (787 lines) |
| Data models | `data/models.py` (303 lines) |
| Pattern learning | `enrichment/pattern_engine.py` (512 lines) |
| Provider interface | `providers/base.py` |
| App config | `config/settings.py` |
| Database layer | `data/database.py` |
| CLI entry point | `cli/main.py` |
| UI entry point | `ui/app.py` |
| API documentation | `API_SPECS.md` |

## Naming Conventions

| Element | Convention | Example |
|---|---|---|
| Files | `snake_case.py` | `email_finder.py`, `circuit_breaker.py` |
| Classes | `PascalCase` | `EnrichmentResult`, `BaseProvider` |
| Functions | `snake_case` | `find_email()`, `search_companies()` |
| Constants | `UPPER_SNAKE_CASE` | `WATERFALL_ORDER`, `CACHE_TTL_DAYS` |
| Test files | `test_*.py` | `test_waterfall.py` |
| Test classes | `Test*` | `TestCompany`, `TestWaterfallOrchestrator` |
| Provider files | `{provider_name}.py` | `apollo.py`, `findymail.py` |

## Module Dependencies

```
config/settings.py
    └── (no internal deps, reads .env)

data/models.py
    └── (standalone Pydantic models)

data/database.py
    └── data/models.py

providers/base.py
    └── (abstract interface)

providers/{apollo,findymail,icypeas,contactout}.py
    ├── providers/base.py
    └── data/models.py

enrichment/classifier.py
    └── (standalone, bitfield logic)

enrichment/router.py
    └── enrichment/classifier.py

enrichment/pattern_engine.py
    └── data/database.py

enrichment/waterfall.py
    ├── providers/*
    ├── enrichment/classifier.py
    ├── enrichment/router.py
    ├── enrichment/pattern_engine.py
    ├── data/database.py
    ├── cost/budget.py
    └── quality/circuit_breaker.py

cli/main.py
    ├── enrichment/waterfall.py
    ├── data/io.py
    └── config/settings.py

ui/app.py
    ├── ui/pages/*
    ├── data/database.py
    └── config/settings.py
```

## Stub Files (Not Yet Implemented)

These files exist but contain skeleton/placeholder code:
- `enrichment/domain_finder.py` — domain lookup from company name
- `enrichment/linkedin_finder.py` — LinkedIn URL from name + company
- `enrichment/company_enricher.py` — company data enrichment
