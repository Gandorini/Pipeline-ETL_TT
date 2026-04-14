# Pipeline-ETL_TT — Daily Incremental ETL Pipeline

A production-grade incremental ETL pipeline that extracts daily booking/charge records from a REST API, applies type normalisation and deduplication, and upserts the results into a **Supabase (PostgreSQL)** database.

Automated via **GitHub Actions** (scheduled cron) with a **Docker** alternative for self-hosted deployments.

---

## Architecture Overview

```
┌─────────────────────┐     REST API (JSON)     ┌──────────────────────┐
│   External Booking  │ ──────────────────────► │   loaddaily_TT.py    │
│       API           │   ?updated_at=YYYYMMDD  │   (ETL Script)       │
└─────────────────────┘                         └──────────┬───────────┘
                                                           │
                              ┌────────────────────────────┤
                              │                            │
                    ┌─────────▼──────────┐    ┌───────────▼──────────┐
                    │   1. EXTRACT       │    │   2. DEDUPLICATE     │
                    │  Fetch yesterday's │    │  Keep latest record  │
                    │  records from API  │    │  per order_code key  │
                    └─────────┬──────────┘    └───────────┬──────────┘
                              │                            │
                    ┌─────────▼────────────────────────────▼──────────┐
                    │                  3. TRANSFORM                    │
                    │   Normalise types: bool / int / float / datetime │
                    └─────────────────────────┬────────────────────────┘
                                              │
                                   ┌──────────▼──────────┐
                                   │      4. LOAD        │
                                   │  UPSERT → Supabase  │
                                   │  (conflict: order   │
                                   │   _code)            │
                                   └─────────────────────┘
```

---

## Data Engineering Concepts Demonstrated

| Concept | Implementation |
|---|---|
| **Incremental loading** | Fetches only yesterday's records using `?updated_at=YYYYMMDD` query parameter |
| **Idempotency / UPSERT** | `supabase.table().upsert(on_conflict='order_code')` — safe to re-run without duplicates |
| **Deduplication** | In-memory dict keyed on `order_code` removes duplicate records before load |
| **Type normalisation** | `normalize_value()` handles boolean, integer, float and datetime coercion with null safety |
| **Orchestration — cloud** | GitHub Actions scheduled cron (`0 6 * * *`) with `workflow_dispatch` for manual runs |
| **Orchestration — self-hosted** | Docker + cron daemon inside container as an alternative deployment strategy |
| **Secret management** | All credentials injected via environment variables / GitHub Secrets — never hardcoded |
| **Observability** | Structured logging with timestamps at every pipeline stage using Python `logging` |
| **Progress tracking** | `tqdm` progress bars for deduplication and normalisation steps |
| **Containerisation** | Dockerfile with `.env` deliberately excluded from image build for security |

---

## Data Flow — Step by Step

### 1. Extract
The script calculates **yesterday's date** at runtime and requests all records updated on that day from the external REST API.

```python
yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
url = f"{getenv('API_URL')}?updated_at={yesterday}"
response = requests.get(url, headers={"Authorization": getenv("TOKEN_KEY")})
```

### 2. Deduplicate
Records are loaded into a dictionary keyed by `order_code`. If the same order appears twice in the API response, only the last occurrence is kept — ensuring downstream uniqueness before the UPSERT.

```python
unique_records = {}
for row in data:
    key = row.get("order_code")
    if key:
        unique_records[key] = row
```

### 3. Transform — Type Normalisation
The `normalize_value()` function applies column-aware coercion:

| Target Type | Logic |
|---|---|
| `boolean` | Maps string variants (`"sim"/"não"`, `"true"/"false"`, `"1"/"0"`) → Python `bool` |
| `integer` | Handles comma-decimal strings (`"1,0"`) and empty strings → `int` or `None` |
| `float` | Same comma handling → `float` or `None` |
| `datetime` | Parses ISO format; appends `+00:00` timezone if naive |

### 4. Load — UPSERT to Supabase
Records are upserted into the `charges` table. On conflict with an existing `order_code`, all fields are updated — guaranteeing the table always reflects the latest API state.

```python
supabase.table('charges').upsert(
    normalized_records,
    on_conflict='order_code'
).execute()
```

---

## Orchestration Strategies

### Strategy A — GitHub Actions (Recommended for cloud)

The workflow (`.github/workflows/run.yml`) runs automatically every day at **06:00 UTC** and can also be triggered manually from the Actions tab.

**Required GitHub Secrets:**

| Secret | Description |
|---|---|
| `API_URL` | Base URL of the bookings REST API |
| `TOKEN_KEY` | Bearer token for API authentication |
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Supabase service role or anon key |

### Strategy B — Docker + Cron (Self-hosted)

For on-premise or server deployments, the pipeline runs inside a Docker container with a native cron daemon scheduled at 06:00 UTC daily.

```bash
docker-compose up --build -d
```

---

## Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/Gandorini/Pipeline-ETL_TT.git
cd Pipeline-ETL_TT

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env with your actual credentials

# 5. Run the pipeline
python loaddaily_TT.py
```

---

## Project Structure

```
Pipeline-ETL_TT/
├── loaddaily_TT.py          # Main ETL script (Extract → Deduplicate → Transform → Load)
├── Dockerfile               # Container definition (cron-based execution)
├── docker-compose.yml       # Local stack: pipeline + PostgreSQL
├── crontab                  # Cron schedule for Docker deployment
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template (no real values)
├── .gitignore               # Excludes .env and sensitive files
└── .github/
    └── workflows/
        └── run.yml          # GitHub Actions scheduled workflow
```

---

## Tech Stack

| Tool | Role |
|---|---|
| Python 3.10+ | Pipeline language |
| `requests` | HTTP client for REST API |
| `supabase-py` | Supabase client for UPSERT operations |
| `python-dotenv` | Environment variable management |
| `tqdm` | Progress bars for batch processing |
| PostgreSQL (Supabase) | Cloud-hosted destination database |
| Docker + cron | Self-hosted container orchestration |
| GitHub Actions | Cloud-native scheduled pipeline orchestration |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Incremental load over full load | Minimises API calls and processing time; only changed records are fetched daily |
| UPSERT over INSERT | Makes the pipeline idempotent — re-running on failure never creates duplicates |
| In-memory deduplication | Simple and effective for daily record volumes; avoids extra DB round-trips |
| Two orchestration strategies | GitHub Actions for zero-infrastructure deployments; Docker for full control on-premise |
| `.env` excluded from Docker image | Credentials are runtime-injected, never baked into the container image |