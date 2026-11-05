# JobsRSS

Phase 1 monorepo for a personal Job Intelligence platform.

Current release: **v2.2.3** ([release notes and test report](docs/RELEASE_V2.2.3.md))

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

## Updating a Local Install

`docker-compose.yml` mounts `./backend` over `/app` in the `api` and `worker`
containers, so they run the checked-out backend code rather than the copy baked
into the image. It also mounts the dashboard code (`frontend/app`,
`package.json`, `next.config.ts`) into the `frontend` container, which builds
it when it starts. Updates therefore apply without a rebuild and without
Docker Hub, npm or PyPI access:

```bash
git pull
docker compose up -d --force-recreate --no-build api worker frontend
docker compose exec -T worker cat app/scheduler/runner.py | diff -q - backend/app/scheduler/runner.py && echo "worker runs current code"
```

The dashboard is back about a minute after the recreate (`docker compose logs -f frontend`
shows the build; it is ready at `Ready in`). Reload the page with Cmd+Shift+R.

Recreating the worker starts a full cycle: platform collectors, the LLM rerank
and the freshness sweep run at once, and the official sources follow at
30-second intervals (about 12 minutes for all of them).

A rebuild (`docker compose build api worker`) is needed only when
`backend/requirements.txt` or `backend/Dockerfile` changes; it needs apt and
PyPI access. Likewise `docker compose build frontend` is needed only when
`frontend/package-lock.json` or `frontend/Dockerfile` changes; it pulls
`node:22-alpine` from Docker Hub and runs `npm ci`. If Docker Hub is
unreachable (`failed to resolve source metadata for docker.io/library/node:22-alpine`),
retry later or add a registry mirror in Docker Desktop (Settings → Docker
Engine → `"registry-mirrors"`); the existing image keeps working meanwhile.

The dashboard shows its version next to the title and a yellow warning when it
is older than the API. If the warning stays, the frontend container was not
recreated with the mounted code; run the recreate command above.

## Smoke Test

`scripts/smoke_test.sh` checks a running stack end to end and exits non-zero
if anything fails. It needs only `curl` and `docker`:

```bash
scripts/smoke_test.sh            # read-only
scripts/smoke_test.sh --write    # also sets and restores favorite/applied on one job
```

It checks:

- **Containers:** all four are up, none is restart-looping, and api, worker
  and frontend run the checked-out code.
- **API:** `/healthz` reports this release's version; the jobs endpoints,
  filters and mark filters respond; RSS feeds are well-formed.
- **Dashboard:** the page renders and its `/api/backend` proxy reaches the API.
- **Database:** every schema column exists, no official job has a region
  as its company, and location categories are valid.
- **Worker:** collectors ran in the last 6 hours, and the LLM settings are
  usable (enabled, key ASCII-only, no deployment or quota errors). The key is
  never printed.

Run it after every upgrade. A worker that was just recreated needs about 15
minutes to finish its first collection cycle. `API_URL`, `WEB_URL` and
`COMPOSE` override the defaults.

## DevOps Pipeline (Near Production)

GCP GKE is the supported cloud runtime. Use Cloud Shell plus Cloud Build
(no GitHub Actions install on GKE):

- `docs/DEVOPS_PIPELINE_GKE.md`

The older Azure VM + Docker Compose path remains documented at:

- `docs/DEVOPS_PIPELINE_AZURE.md`

## V2 Official Career Sources

V2 adds a 49-company registry and 16-source first wave. Fifteen first-wave
sources have operational collectors; Hengrui remains monitor-only because its
official site does not expose a current, stable job inventory.

Enable official collection:

```env
OFFICIAL_SOURCES_ENABLED=true
OFFICIAL_SOURCE_INTERVAL_MINUTES=360
OFFICIAL_SOURCE_MAX_JOBS_PER_SOURCE=150
OFFICIAL_SOURCE_SEA_MAX_JOBS_PER_SOURCE=150
OFFICIAL_SOURCE_MAX_PAGES_PER_SOURCE=20
OFFICIAL_SOURCE_STALE_AFTER_DAYS=30
```

`OFFICIAL_SOURCE_MAX_JOBS_PER_SOURCE` caps each company. Collectors that search
by location query each target separately (Amazon: Shanghai, Hangzhou, Nanjing,
Hong Kong, Malaysia; Microsoft: Shanghai, Suzhou, Hong Kong, Malaysia; Google:
Shanghai, Hong Kong, Malaysia; BCG and Roche: Shanghai, Malaysia); when they together exceed the cap,
results are taken alternately from each location (newest first) so none crowds
out the others.

Amazon, Microsoft and Google also search Singapore, Indonesia, Thailand,
Vietnam and the Philippines, with their own cap
(`OFFICIAL_SOURCE_SEA_MAX_JOBS_PER_SOURCE`, alternating between countries), so
these markets add to the jobs above instead of replacing them. A job already
taken by the first group does not use a Southeast Asia slot.
Set it to `0` to turn the Southeast Asia searches off.

Alibaba is collected from the social-recruitment portals as two sources.
`official_aliyun` (`careers.aliyun.com`) takes Alibaba Cloud roles in the
target locations, searching security, technical-service (TAM) and
solution-architect titles first so they survive the cap, then sweeping every
Shanghai and overseas role. `official_alibaba`
(`talent.alibaba.com`, ~4,000 roles, no function filter) keyword-searches
"安全" / "security" plus the security category for the rest of the group and
skips Alibaba Cloud roles, which both portals list under the same id. Any
remaining campus-portal rows are closed on the next run.

Deloitte, Yunnan Baiyao and Simcere use HotJob portals whose "company" field is
a practice region (中国大陆, 中国香港) or a business unit (药品事业群,
零售事业部), so their jobs always show the employer: `Deloitte / 德勤`,
`Yunnan Baiyao / 云南白药`, `Simcere / 先声药业`. Every api or worker start
(and `refresh_all.py`) rewrites stored rows of these sources that still carry
another value, so `docker compose up -d --force-recreate api worker` fixes old
rows without waiting for the next collection.

Official jobs are classified before publication:

- `confirmed_shanghai`: explicitly includes Shanghai/上海.
- `confirmed_yangtze_delta`: Jiangsu or Zhejiang (Hangzhou, Suzhou, Nanjing,
  Wuxi, Ningbo, ...).
- `confirmed_hong_kong`: Hong Kong/香港/Kowloon or the ISO code `HKG`.
- `confirmed_malaysia`: explicitly includes Malaysia or a Malaysian city
  (Kuala Lumpur, Selangor, Johor, Penang, ...).
- `confirmed_southeast_asia`: Singapore, Indonesia, Thailand, Vietnam or the
  Philippines (country names, major cities, or ISO codes such as `SGP` / `VN`);
  the job's `country` is set to the matched country.
- `unclassified`: broad China/APAC/Greater China/Remote or missing location.
- `excluded`: any other explicit location.

Only confirmed and unclassified jobs are ingested. A multi-city role is
classified by its first matching target in the order above, so "Beijing /
Hangzhou" is kept.

## LLM Targeted Matching (V2.1)

The optional LLM reranker keeps broad source recall, then evaluates each active
job against `LLM_TARGET_PROFILE` (role domain and seniority; seniority is a
hard gate). Only jobs whose rule score reaches `LLM_MIN_RULE_SCORE` are sent:
security titles earn 55, customer-facing cloud roles (solutions architect, TAM,
presales, customer engineer) 40, seniority words 20 and target locations 15. Results are stored on each job and can be
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
LLM_REQUEST_MAX_RETRIES=2
LLM_REQUEST_RETRY_BACKOFF_SECONDS=1.5
LLM_ABORT_AFTER_CONSECUTIVE_FAILURES=8
LLM_RERANK_INTERVAL_MINUTES=30
LLM_MAX_JOBS_PER_RUN=60
LLM_COMMIT_EVERY_JOBS=20
LLM_MIN_RULE_SCORE=20
LLM_ONLY_UNSCORED=true
LLM_REJECT_EARLY_CAREER=true
LLM_TARGET_PROFILE=Senior individual-contributor or manager-and-above cybersecurity roles ... customer-facing cloud roles (Solutions Architect, TAM, presales) when they centre on cloud or security ... large, well-known employers ... Shanghai, Jiangsu/Zhejiang, Hong Kong, Singapore, Malaysia, the rest of Southeast Asia...
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

Early-career guard:

- When `LLM_REJECT_EARLY_CAREER=true`, campus/new-grad/intern roles are hard
  rejected with `llm_verdict=not_fit` by deterministic rules.
- This guard runs both during ingestion and before LLM network calls, so model
  timeouts do not leave early-career roles in AI-positive states.
- LLM HTTP calls include retry with exponential backoff for transient status
  codes (408/425/429/500/502/503/504), and rerank aborts early after too many
  consecutive failures to avoid long outage loops.

API filtering:

- `GET /jobs?min_llm_score=70`
- `GET /jobs?llm_verdict=strong_fit`
- `GET /jobs/count?min_llm_score=70&llm_verdict=strong_fit`

## Full Refresh (Re-collect + Re-score Everything)

The scheduler only scores `LLM_MAX_JOBS_PER_RUN` jobs per interval, so a backlog
takes many intervals to clear. To re-collect every enabled source and re-evaluate
the whole history in one command, run it in its own container with the worker
stopped (otherwise the scheduler scores the same jobs concurrently and doubles
token spend):

```bash
docker compose stop worker
docker compose run -d --name jobsrss-refresh worker python scripts/refresh_all.py --reset-scores --linkedin-verify-max 200
docker logs -f jobsrss-refresh
```

When the log prints `refresh_rescore_done`, clean up and resume the scheduler:

```bash
docker rm jobsrss-refresh
docker compose up -d --force-recreate worker
```

`docker compose start worker` would restart the existing container with the
environment and mounts it was created with, ignoring later `.env` or compose
changes; recreating picks them up.

- `--reset-scores` clears stored LLM verdicts first so historical jobs become
  candidates again. Deterministic early-career rejections are kept (they cost no
  tokens); add `--reset-early-career-guard` to revisit them too.
- After collecting and before the rerank, the script closes dead postings so
  no tokens are spent on them: rows from removed sources, stale and outdated
  rows (see [Closing Dead and Outdated Postings](#closing-dead-and-outdated-postings)),
  and LinkedIn rows the public job page reports as closed.
  `--linkedin-verify-max N` sets how many LinkedIn rows to re-check (default
  `LINKEDIN_VERIFY_MAX_PER_RUN`; `0` skips). It also applies schema changes
  first, so it works even if the worker has not started on the new code.
- The rerank then runs repeated passes until no job is left unscored, printing
  `refresh_rescore_pass ... remaining=N` after each pass.
- `--skip-collect` re-scores without touching the collectors;
  `--skip-rescore` only refreshes job data.
- `--batch-size` overrides `LLM_MAX_JOBS_PER_RUN` for this run only.

Track progress from another terminal:

```bash
docker compose exec -T postgres psql -U jobsrss -d jobsrss -c \
  "SELECT llm_verdict, count(*) FROM jobs WHERE status='active' GROUP BY llm_verdict;"
```

To stop LLM spend, stop the worker (`docker compose stop worker`) or set
`LLM_RERANK_ENABLED=false` and recreate it with
`docker compose up -d --force-recreate worker`. `docker compose restart` does not
reload `env_file`.

## Authenticated Platform Collection (LinkedIn / 51job / Liepin)

The portal supports direct account-based collection through Playwright automation.

Recommended setup priority:

1. Use `*_AUTH_STORAGE_STATE_PATH` with an existing logged-in browser session export.
2. Use username/password only when login selectors are stable and permitted.

Key `.env` fields:

- LinkedIn:
  - `LINKEDIN_AUTH_ENABLED=true`
  - `LINKEDIN_AUTH_STORAGE_STATE_PATH=/absolute/path/to/linkedin_state.json`
  - `LINKEDIN_REQUIRE_STORAGE_STATE=true`
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

51job and Liepin only expose search result pages, so a posting that has been
filled or withdrawn simply stops appearing. Rows not seen for
`PLATFORM_STALE_AFTER_DAYS` (default 7) are closed after any run that returned
results; a run that returns nothing (for example, an expired cookie) closes
nothing. Cards that say 停止招聘 / 职位已关闭 are closed immediately.

## Job List and Details

Jobs are listed as two-line cards: title, then company, standardized location
and source, with the AI score (solid blue for `strong_fit`) and the posting date
under it, and Apply Now, Details, Favorite and Mark Applied buttons. Clicking a title or
**Details** on a window at least 1024px wide splits the page: the list narrows
to a compact column and the job's details (AI reasons, description) stay
pinned on the right while you scroll. **J** / **K** move to the next or
previous job and **Esc** (or Close) returns to the full-width list. Narrower
windows show the details as a dialog instead.

### Posting dates

Each card shows the date and age, for example `Posted Nov 2 · 3d ago`; the
details pane shows the full date. The label says where the date comes from:

- **Posted**: the source's publish date.
- **Updated**: Tencent and Huawei only give the date a posting was last
  updated, which can be later than when it first went up.
- **First seen** (italic): the source gives no date (LinkedIn email alerts
  without one, for example), so this is when JobsRSS first collected the job.

### Sorting

**Sort By** orders the list by **Newest posted first** (the default) or
**AI score, highest first**. With AI score, ties are broken by the newest
posting, and jobs without an AI score come last, ordered by rule score. Newest
first uses the first-seen date for jobs without a posting date. The choice is
saved in the browser. The API takes the same values: `GET /jobs?sort=newest`
or `GET /jobs?sort=ai_score`.

## Favorites, Applied and View History

Each job card and the detail panel have **Favorite** and **Mark Applied**
toggles. Opening a job's details or clicking **Apply Now** records a view: the card
title turns purple and a "Viewed N× · last …" badge shows how often and when
you opened it. Marks are stored on the job row (`favorited_at`, `applied_at`,
`last_viewed_at`, `view_count`), so they survive re-collection and
`refresh_all --reset-scores`.

The **My Marks** filter narrows the list to Favorites, Applied, Not applied or
Not viewed yet. Favorites and Applied also include closed postings (shown with
a Closed badge) and ignore the AI and rule-score filters, so a job you applied
to stays findable after it is taken down.

API: `PUT /jobs/{id}/marks` with `{"favorited": true|false, "applied": true|false}`
(either field may be omitted; setting a mark again keeps its first timestamp),
`POST /jobs/{id}/view`, and `mark=favorited|applied|not_applied|viewed|not_viewed`
on `/jobs`, `/jobs/count` and `/jobs/source-counts`. The API container adds
the columns when it starts, so after pulling run
`docker compose up -d --force-recreate --no-build api frontend`.

## Searching and Filtering by Location

Sources write places differently (`上海-浦东新区`, `Shanghai, Shanghai, CN`,
`Shanghai, CHN`, `China\Shanghai-Shanghai`). Every job is mapped to standard
cities and a country (`backend/app/normalization/location_standard.py`: Chinese
and English names, pinyin variants, districts, ISO codes), and cards show the
result, for example `上海 Shanghai · 中国 China`. A multi-city role keeps all
its cities, with the target-region city first.

- **Search**: a place name in either language (`上海`, `Shanghai`, `杭州`,
  `Hong Kong`, `香港`, `吉隆坡`, `KL`, `新加坡`) matches the standard location as
  well as the text, and every word must match. `安全 杭州` finds Hangzhou
  security roles whatever the source wrote; `上海安全` works without a space.
  Keywords are not translated (`security` does not match `安全`), and
  districts and provinces (`浦东`, `浙江`) match as plain text only.
- **Location** picker: countries and cities with job counts under the other
  filters. "All of 中国 China" includes multi-city roles that list a Chinese
  city anywhere.
- **Target Region** keeps the coarse categories (Shanghai, Jiangsu/Zhejiang,
  Hong Kong, Malaysia, Southeast Asia, Outside target areas). LinkedIn, Liepin
  and 51job rows are now classified too; before they were all Unclassified.

API: `city=` and `country=` on `/jobs`, `/jobs/count` and
`/jobs/source-counts` (comma-separated; any listed spelling, such as
`city=上海` or `country=HKG`), and `GET /jobs/locations` for the counts. Stored
rows are standardized when the api or worker starts.

## Closing Dead and Outdated Postings

Closed rows disappear from the dashboard, RSS and the digest, except under the
Favorites and Applied filters described above. A posting is
closed when any of these applies:

- **LinkedIn says it is closed.** The logged-in collector checks each job
  page for LinkedIn's closed badge ("No longer accepting applications",
  已停止接受求职申请, 不再受理應徵 and variants) and stores the job as closed.
- **LinkedIn re-verification.** Every `LINKEDIN_VERIFY_INTERVAL_MINUTES` the
  worker re-checks up to `LINKEDIN_VERIFY_MAX_PER_RUN` active `linkedin_auth`
  / `linkedin_email` rows on LinkedIn's public job page
  (`/jobs-guest/jobs/api/jobPosting/{id}`), dashboard-visible rows
  (strong/possible fit, LLM score >= 60) and never-checked rows first, each
  row at most once per `LINKEDIN_VERIFY_RECHECK_HOURS`. Requests are
  anonymous: no cookie or storage state is ever sent, so they cannot affect
  your LinkedIn account. Requests are spaced `LINKEDIN_VERIFY_DELAY_SECONDS`
  (plus jitter) apart. Only the closed badge or a 404/410 closes a row. A 404
  for a posting the collector saw in the last 24 hours is ignored, a
  429/999 (rate limit) stops the run, and redirects, other errors and pages
  that don't parse never close anything.
- **Not seen any more.** Rows a collector stops returning are closed after
  `LINKEDIN_AUTH_STALE_AFTER_DAYS` (14), `LINKEDIN_EMAIL_STALE_AFTER_DAYS`
  (14), `PLATFORM_STALE_AFTER_DAYS` (7, Liepin/51job) or
  `OFFICIAL_SOURCE_STALE_AFTER_DAYS` (30). For a disabled collector the same
  window is applied by an hourly sweep, because the collector itself never
  runs.
- **Too old.** The hourly sweep closes rows whose `posted_at` is older than
  `JOB_MAX_AGE_DAYS` (60). Rows without a posting date are aged from when
  JobsRSS first saw them, with the longer `JOB_MAX_AGE_UNDATED_DAYS` (90),
  because without a date a repost under the same job ID looks exactly like
  an old listing. The age rule
  applies even if a collector still lists the posting, and ingestion enforces
  it too, so a site that keeps an old listing up cannot reopen it. A repost
  with a fresh date (LinkedIn reposts, ATS "last updated" dates) comes back
  as active. Set either value to `0` to disable that rule.

60 days leaves room for senior searches, which often run six to eight weeks,
while dropping evergreen and forgotten listings. Most roles that are still
hiring after two months get reposted, which refreshes the date.

```env
LINKEDIN_VERIFY_ENABLED=true
LINKEDIN_VERIFY_INTERVAL_MINUTES=60
LINKEDIN_VERIFY_MAX_PER_RUN=20
LINKEDIN_VERIFY_RECHECK_HOURS=24
LINKEDIN_VERIFY_DELAY_SECONDS=4
LINKEDIN_EMAIL_STALE_AFTER_DAYS=14
JOB_MAX_AGE_DAYS=60
JOB_MAX_AGE_UNDATED_DAYS=90
```

The worker applies schema changes (for example the `last_verified_at`
column) when it starts, so no manual migration is needed after pulling (see
[Updating a Local Install](#updating-a-local-install)).

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
- `LINKEDIN_ALLOWED_LOCATIONS=Singapore,Malaysia,Hong Kong,Shanghai,Jiangsu,Zhejiang`

With strict filtering enabled, LinkedIn jobs outside Singapore, Malaysia,
Hong Kong, Shanghai, Jiangsu, and Zhejiang are discarded before database
ingestion. `Malaysia` also matches Malaysian cities such as Kuala Lumpur,
Petaling Jaya, Cyberjaya, Penang and Johor Bahru.

## Refreshing LinkedIn Login State

Start a dedicated Chrome debugging session:

macOS:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-jobsrss-profile
```

Linux:

```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-jobsrss-profile
```

Log in to LinkedIn in that browser window, then export state:

```bash
cd backend
source .venv/bin/activate
python scripts/export_storage_state.py \
  --site linkedin \
  --out ../secrets/linkedin_state.json
```

If CDP mode fails with `Browser context management is not supported`, use
interactive mode (no CDP dependency):

```bash
cd backend
source .venv/bin/activate
python scripts/export_storage_state.py \
  --site linkedin \
  --mode interactive \
  --out ../secrets/linkedin_state.json
```

Set `.env`:

```env
LINKEDIN_AUTH_ENABLED=true
LINKEDIN_AUTH_STORAGE_STATE_PATH=/secrets/linkedin_state.json
LINKEDIN_REQUIRE_STORAGE_STATE=true
```

When `LINKEDIN_REQUIRE_STORAGE_STATE=true` and the state file is missing, the
LinkedIn collector is skipped safely and existing `linkedin_auth` active jobs
are closed to avoid publishing stale cached results.

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