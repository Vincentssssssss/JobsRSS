# JobsRSS

Phase 1 monorepo for a personal Job Intelligence platform.

Current release: **v2.0.0-beta**

## Services

- `postgres`: persistent PostgreSQL database
- `api`: FastAPI backend (`/healthz`, `/jobs`, `/rss/*`)
- `worker`: APScheduler collector runner
- `frontend`: Next.js dashboard (Apple-style minimal UI)

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
```

Open:

- API health: `http://localhost:8000/healthz`
- Jobs API: `http://localhost:8000/jobs`
- RSS all: `http://localhost:8000/rss/all.xml`
- Dashboard: `http://localhost:3000`
- Official source registry: `http://localhost:8000/sources/official`

## V2 Official Career Sources

V2 adds a 38-company registry and 16-source first wave. Fifteen first-wave
sources have operational collectors; Hengrui remains monitor-only because its
official site does not expose a current, stable job inventory.

Enable official collection:

```env
OFFICIAL_SOURCES_ENABLED=true
OFFICIAL_SOURCE_INTERVAL_MINUTES=360
OFFICIAL_SOURCE_MAX_JOBS_PER_SOURCE=50
OFFICIAL_SOURCE_MAX_PAGES_PER_SOURCE=10
OFFICIAL_SOURCE_STALE_AFTER_DAYS=30
```

Official jobs are classified before publication:

- `confirmed_shanghai`: explicitly includes Shanghai/上海.
- `unclassified`: broad China/APAC/Greater China/Remote or missing location.
- `excluded`: explicit non-Shanghai location.

Only confirmed Shanghai and unclassified jobs are ingested.

## LLM Targeted Matching (V2.1)

The optional LLM reranker keeps broad source recall, then performs cybersecurity
fit evaluation on active jobs. Results are stored on each job and can be
filtered by API/UI.

Supported provider modes:

- `openai`: OpenAI Chat Completions API
- `chatgpt`: alias of `openai` (OpenAI-compatible)
- `codex`: alias of `openai` (OpenAI-compatible)
- `qwen`: DashScope OpenAI-compatible endpoint

Configuration:

```env
LLM_RERANK_ENABLED=true
LLM_PROVIDER=openai
LLM_API_KEY=your_api_key
LLM_BASE_URL=
LLM_API_VERSION=
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=
LLM_TIMEOUT_SECONDS=30
LLM_VERIFY_TLS=true
LLM_RERANK_INTERVAL_MINUTES=30
LLM_MAX_JOBS_PER_RUN=60
LLM_MIN_RULE_SCORE=20
LLM_ONLY_UNSCORED=true
LLM_TARGET_PROFILE=Senior cybersecurity roles focused on cloud security across Shanghai/Jiangsu/Zhejiang, Hong Kong, and Singapore...
```

Qwen example:

```env
LLM_PROVIDER=qwen
LLM_API_KEY=your_dashscope_key
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

Azure OpenAI example:

```env
LLM_PROVIDER=openai
LLM_API_KEY=your_azure_key
LLM_MODEL=<your-azure-deployment-name>
LLM_BASE_URL=https://<resource>.openai.azure.com/openai/v1
LLM_API_VERSION=
```

When the base URL host ends with `.openai.azure.com`, the reranker
automatically uses `api-key` authentication header.

Azure AI Foundry + Entra ID example:

```env
LLM_PROVIDER=openai
LLM_API_KEY=
LLM_MODEL=gpt-5.6-luna
LLM_BASE_URL=https://<project>.services.ai.azure.com/openai/v1
LLM_AZURE_USE_DEFAULT_CREDENTIAL=true
LLM_AZURE_SCOPE=https://ai.azure.com/.default
```

When `LLM_AZURE_USE_DEFAULT_CREDENTIAL=true`, the reranker fetches a bearer token
from `DefaultAzureCredential` and uses `Authorization: Bearer <token>`.

API filtering:

- `GET /jobs?min_llm_score=70`
- `GET /jobs?llm_verdict=strong_fit`
- `GET /jobs/count?min_llm_score=70&llm_verdict=strong_fit`

## Authenticated Platform Collection (LinkedIn / 51job / Liepin)

The portal supports direct account-based collection through Playwright automation.

Recommended setup priority:

1. Use `*_AUTH_STORAGE_STATE_PATH` with an existing logged-in browser session export.
2. Use username/password only when login selectors are stable and permitted.

Key `.env` fields:

- LinkedIn:
  - `LINKEDIN_AUTH_ENABLED=true`
  - `LINKEDIN_AUTH_STORAGE_STATE_PATH=/absolute/path/to/linkedin_state.json`
  - `LINKEDIN_SEARCH_URLS=https://www.linkedin.com/jobs/search/?keywords=Cloud%20Security%20Architect&location=Hong%20Kong`
- 51job:
  - `JOB51_AUTH_ENABLED=true`
  - `JOB51_AUTH_STORAGE_STATE_PATH=/absolute/path/to/job51_state.json`
  - `JOB51_SEARCH_URLS=https://search.51job.com/...`
- Liepin:
  - `LIEPIN_AUTH_ENABLED=true`
  - `LIEPIN_AUTH_STORAGE_STATE_PATH=/absolute/path/to/liepin_state.json`
  - `LIEPIN_SEARCH_URLS=https://www.liepin.com/...`

Multiple search pages can be configured as comma-separated URLs.

## LinkedIn Official-Source Enrichment

V1.1 uses LinkedIn for discovery, then enriches eligible jobs from the external
company career page or ATS linked by the job's Apply action.

Supported structured enrichment includes:

- Workday
- Greenhouse
- Lever
- SmartRecruiters
- SuccessFactors

V1.1 live fetching is restricted to recognized ATS domains. Generic company
career pages are retained as a future opt-in capability after per-domain
allowlisting is added.

Field priority:

1. Official ATS/company career page
2. LinkedIn job detail page
3. LinkedIn search card

The LinkedIn URL remains the source URL, while `apply_url` uses the official
application URL when enrichment succeeds.

Configuration:

- `LINKEDIN_EXTERNAL_ENRICHMENT_ENABLED=true`
- `LINKEDIN_EXTERNAL_ENRICHMENT_TIMEOUT_SECONDS=20`
- `LINKEDIN_STRICT_LOCATION_FILTER=true`
- `LINKEDIN_ALLOWED_LOCATIONS=Singapore,Hong Kong,Shanghai,Jiangsu,Zhejiang`

With strict filtering enabled, LinkedIn jobs outside Singapore, Hong Kong,
Shanghai, Jiangsu, and Zhejiang are discarded before database ingestion.

## Refreshing Liepin Login State

Start a dedicated Chrome debugging session on macOS:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-jobsrss-profile
```

Log in to Liepin in that Chrome window. In another terminal:

```bash
cd backend
source .venv/bin/activate
python scripts/export_storage_state.py \
  --site liepin \
  --out ../secrets/liepin_state.json
```

The exporter keeps only Liepin cookies/origins, writes the file with mode
`0600`, and never commits it. Docker should mount `./secrets:/secrets:ro`, and
`.env` should contain:

```env
LIEPIN_AUTH_ENABLED=true
LIEPIN_AUTH_STORAGE_STATE_PATH=/secrets/liepin_state.json
```

## V1.0 Recommended Source Mode

Current stable recommendation:

- Primary: `linkedin_auth`, `liepin_auth`
- Deferred: `job51_auth` (keep disabled until source-specific parser tuning is complete)

Recommended `.env` values for V1.0:

- `LINKEDIN_AUTH_ENABLED=true`
- `LIEPIN_AUTH_ENABLED=true`
- `JOB51_AUTH_ENABLED=false`

## LinkedIn Job Alerts via IMAP (Fallback)

If direct authenticated collection is temporarily unavailable, keep this fallback enabled.

1. Create a mailbox with IMAP enabled (for example Gmail or Outlook).
2. Configure LinkedIn job alerts to deliver to that mailbox.
3. Fill these `.env` fields:
   - `LINKEDIN_EMAIL_ENABLED=true`
   - `LINKEDIN_EMAIL_IMAP_HOST`
   - `LINKEDIN_EMAIL_IMAP_PORT`
   - `LINKEDIN_EMAIL_USERNAME`
   - `LINKEDIN_EMAIL_PASSWORD` (app password recommended)
   - `LINKEDIN_EMAIL_FOLDER`
   - `LINKEDIN_EMAIL_SENDER_FILTER`
4. Restart services:

```bash
docker compose up -d --build
```

When disabled or not fully configured, the LinkedIn email collector is skipped safely.

## Daily 24h Digest Email

Enable daily summary email for jobs discovered in the last 24 hours:

- `DIGEST_EMAIL_ENABLED=true`
- `DIGEST_EMAIL_SMTP_HOST`
- `DIGEST_EMAIL_SMTP_PORT`
- `DIGEST_EMAIL_SMTP_USERNAME`
- `DIGEST_EMAIL_SMTP_PASSWORD`
- `DIGEST_EMAIL_SENDER`
- `DIGEST_EMAIL_RECIPIENTS=mail1@example.com,mail2@example.com`
- `SCHEDULER_DIGEST_HOUR_UTC`
- `SCHEDULER_DIGEST_MINUTE_UTC`

The dashboard also exposes a portal summary endpoint:

- `GET /jobs/summary/last-24h`