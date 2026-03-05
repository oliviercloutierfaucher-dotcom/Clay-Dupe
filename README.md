# Clay-Dupe

Self-hosted B2B data enrichment platform. Finds verified contact emails by cascading through multiple API providers (Apollo, Findymail, Icypeas, ContactOut) in cost-optimized order, with full cost tracking, caching, and budget controls. Built for teams prospecting niche businesses (A&D, medical device, niche industrial).

## Quick Start (Docker)

```bash
# 1. Clone and configure
git clone <repo-url> && cd clay-dupe
cp .env.example .env
# Edit .env with your API keys

# 2. Build and run
make build
make up

# 3. Open the web UI
# http://localhost:8501
```

## Manual Install

```bash
# Requires Python >= 3.11
pip install -r requirements.txt
pip install -e .

# Run the web UI
streamlit run ui/app.py

# Or use the CLI
clay-dupe --help
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your API keys:

| Variable | Required | Description |
|----------|----------|-------------|
| `APOLLO_API_KEY` | Yes | Apollo.io API key |
| `FINDYMAIL_API_KEY` | Yes | Findymail API key |
| `ICYPEAS_API_KEY` | Yes | Icypeas API key |
| `CONTACTOUT_API_KEY` | Yes | ContactOut API key |
| `WATERFALL_ORDER` | No | Provider cascade order (default: `apollo,icypeas,findymail,contactout`) |
| `CACHE_TTL_DAYS` | No | Cache expiry in days (default: `30`) |
| `DB_PATH` | No | SQLite database path (default: `clay_dupe.db`) |

## CLI Commands

```bash
# Enrich contacts from CSV/Excel
clay-dupe enrich contacts.csv --output results.csv

# Search for companies or people (via Apollo)
clay-dupe search companies --preset aerospace_defense --country US
clay-dupe search people --title "VP Engineering" --industry "Manufacturing"

# Verify a single email
clay-dupe verify john@acme.com

# View usage stats and analytics
clay-dupe stats --days 30
```

## Web UI

The Streamlit UI runs on port 8501 and includes:

- **Dashboard** -- enrichment stats and hit rates
- **Search** -- prospect for companies and people
- **Enrich** -- upload CSV/Excel for batch enrichment
- **Results** -- browse and export enrichment results
- **Analytics** -- provider performance and cost analysis
- **Settings** -- API keys, waterfall order, budget limits

## Running Tests

```bash
make test
# or directly:
pytest -v
```

236 tests across 13 test files covering CLI integration, concurrent database access, waterfall edge cases, malformed API responses, and more.

## Architecture

```
cli/            CLI tool (Typer)
ui/             Streamlit web app
providers/      API integrations (Apollo, Findymail, Icypeas, ContactOut)
enrichment/     Waterfall engine + pattern matching
data/           SQLite database + Pydantic models + CSV/Excel I/O
cost/           Budget management + credit tracking + caching
quality/        Email verification + circuit breakers
```

## Docker Commands

```bash
make build      # Build the Docker image
make up         # Start the container (detached)
make down       # Stop the container
make logs       # Follow container logs
make clean      # Remove container + image + volumes
```

To run CLI commands inside the container:

```bash
docker exec clay-dupe clay-dupe enrich /data/contacts.csv
docker exec clay-dupe clay-dupe stats
```

## License

Private -- internal team use only.
