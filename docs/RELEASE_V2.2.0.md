# JobsRSS v2.2.0

## Release Focus

Make the local Docker install the supported way to run JobsRSS and make what it
shows trustworthy. It covers wider target markets, seniority-aware AI scoring,
correct company names, automatic closing of dead postings, and personal
favorite/applied tracking. It also adds a smoke test that proves an install
works.

Changes since v2.1.0 (2026-09-04): 90 commits.

## Highlights

### Collection

- Official sources collect up to 150 jobs each (was 50) in Shanghai,
  Jiangsu/Zhejiang (Hangzhou, Suzhou, Nanjing, ...), Hong Kong, Malaysia and
  Southeast Asia. Amazon, Microsoft and Google have a separate 150-job
  Southeast Asia cap, so Singapore/Indonesia/Thailand/Vietnam/Philippines
  roles do not crowd out Shanghai.
- New `official_aliyun` source (careers.aliyun.com). Alibaba Group now
  collects from the social-recruitment portal instead of the campus site.
- Fosun Pharma's portal moved to a JavaScript front end. The old collector
  silently found 0 jobs; it now uses the Beisen API (71 Shanghai roles on
  release day). Rows from the old portal URLs close automatically.
- Yunnan Baiyao and Simcere collect again; their HotJob host rejected the bare
  `Mozilla/5.0` User-Agent.
- A collector run that fails on a network error (connection reset, TLS
  handshake timeout) is retried once after 15 seconds. Before, it lost that
  source until the next 6-hour cycle. Google also retries individual requests
  and keeps partial results.
- Overdue scheduled runs (after a laptop sleeps, or a slow boot) run once
  instead of being skipped until the next interval.

### Company names

- Deloitte showed its practice region (中国大陆 / 中国香港) as the company.
  Yunnan Baiyao and Simcere showed business units. Each HotJob source now uses
  its fixed employer name. Rows stored by older versions are corrected
  when the api or worker starts, with no re-collection needed.

### AI scoring

- Seniority is a hard gate: roles clearly below the target level get
  `not_fit`.
- The default target profile accepts senior IC (Senior, Staff, Principal,
  Lead) and manager-and-above security roles. It also accepts customer-facing
  cloud roles (Solutions Architect, TAM, presales, Customer/Sales Engineer)
  that centre on cloud or security, at large, well-known employers.
- The rule pre-filter scores broader security titles and adjacent cloud roles,
  so roles like an Alibaba Cloud TAM now reach the LLM.
- LLM rerank commits in batches, stops at once when credits run out, and
  reports a non-ASCII (placeholder) API key once instead of failing every job.
- Azure AI Foundry / Azure OpenAI endpoints are supported through
  `LLM_BASE_URL`.

### Dashboard

- **Favorite** and **Mark Applied** toggles on every card and in the detail
  panel. **View Details** and **Apply Now** record views ("Viewed N× · last …").
- A **My Marks** filter: Favorites, Applied, Not applied, Not viewed yet.
  Favorites and Applied include closed postings.
- Location badges and filters for Jiangsu/Zhejiang, Hong Kong, Malaysia and
  Southeast Asia.
- Collected jobs show while AI scores are still pending.

### Freshness

- Closed LinkedIn postings ("No longer accepting applications") close, and
  active LinkedIn rows are re-checked hourly on the anonymous public page.
- Postings older than 60 days (90 if undated) close across all sources, and
  Liepin/51job rows close 7 days after they stop appearing.
- Rows from removed collectors close when the worker starts.

### Operations

- `docker-compose.yml` mounts `./backend` into api and worker, so `git pull`
  plus a container recreate applies backend changes without a rebuild.
- api and worker wait for Postgres to accept connections (healthcheck) before
  starting.
- `backend/scripts/refresh_all.py` re-collects every source and re-scores the
  whole backlog in one command.
- `scripts/smoke_test.sh` checks a running stack end to end (see README).
- The version is defined in code (`APP_VERSION` in
  `backend/app/core/config.py`). An `APP_VERSION` line left in `.env` is
  ignored, so `/healthz` always reports the code that is running.
- LinkedIn collection was removed from GKE. LinkedIn runs only in a local
  install.

## Upgrade

From any earlier version (schema changes apply automatically on start):

```bash
cd ~/JobsRSS
git pull
docker compose up -d --force-recreate postgres api worker
docker compose build frontend && docker compose up -d frontend
scripts/smoke_test.sh
```

The worker starts a full collection cycle when it is recreated, about 15
minutes for all sources. If a `jobsrss-refresh` container from an earlier full
refresh is still running, let it finish before recreating the worker
(`docker wait jobsrss-refresh && docker rm jobsrss-refresh`), because it runs
the code it loaded at start.

Optional: remove the `APP_VERSION=` line from `.env`; it is no longer read.

## Test Report

All runs were on 2026-11-04 against the release branch, from a US-based test VM
with live access to every career site. The LLM was an OpenAI-compatible mock
that checks the bearer header and scores by title. Each row names the commit it
ran on; later commits changed only what the "Found and fixed" list describes.

| Area | Commit | What ran | Result |
|---|---|---|---|
| Unit tests | `7040543` | `pytest backend/tests` | 242 passed |
| CI | `8675549` | GitHub Actions backend-tests and frontend-build (clean `npm ci`) | passed |
| Clean image build | `9ca7ea9` | `docker compose build --no-cache` (api, worker, frontend) | passed |
| Fresh install | `9ca7ea9` | Empty volume, `.env` copied from `.env.example`, `docker compose up -d`, smoke test | 42 passed, 0 failed, 1 warning (LLM is off by default) |
| Startup order | `9b8c162` | Fresh volume: api and worker start once Postgres is healthy | restart count 0, `/healthz` 2.2.0 |
| Upgrade from the 2026-11-03 install | `5a0a0d1` to `9b8c162` | Old stack stored 89 Deloitte rows as 中国大陆; then `git pull` and recreate, keeping the old `.env` with `APP_VERSION=2.1.0` | `/healthz` 2.2.0, 89 rows repaired, data kept, smoke 42 passed / 0 failed, `--write` round-trip passed |
| Upgrade from `v2.0.0-beta` | `v2.0.0-beta` to `8675549` | Old 19-column schema with data, then `init_db` twice | 32 columns, idempotent, company repaired |
| Full collection cycle | `9b8c162` | Worker ran all 23 official sources; LLM rerank against the mock | 21 sources collected normally (1,895 active jobs); Xiaomi failed on a TLS handshake timeout and Fosun returned 0 (both fixed below); 600 LLM calls, 0 failures |
| Full refresh | `443d77a` | `refresh_all.py --reset-scores --linkedin-verify-max 5` in the worker container | All 23 sources collected (Fosun 71, Xiaomi 125). Alibaba hit an SSL EOF and recovered on the automatic retry. 800 scores reset, 919 re-scored in 6 passes, 0 failed, exit 0. The 468 unscored jobs are all below `LLM_MIN_RULE_SCORE` |
| Smoke after refresh | `443d77a` | Worker recreated, `scripts/smoke_test.sh --write` | 46 passed, 0 failed, 0 warnings |
| Dashboard | `7040543` | Browser run: source, location (Hong Kong, Jiangsu/Zhejiang, Southeast Asia) and AI filters, search, detail panel, favorite/applied, My Marks, RSS | all steps passed; Deloitte cards show Deloitte / 德勤; Fosun cards show Fosun Pharma / 复星医药; detail shows the `Seniority:` reason |
| Scripts | `9b8c162` | `bash -n` on all 11 shell scripts | passed |

Found and fixed during testing:

- A single TLS handshake timeout made a whole source (Xiaomi) skip its cycle.
  Collector runs now retry once after network errors (`8df4276`).
- Fosun's portal had moved to a JavaScript front end and returned 0 jobs
  without an error. It now uses the Beisen API (`443d77a`).
- The dashboard sent every API call to a same-origin path that does not exist
  locally (404) before using the proxy. It now reuses the address that
  answered, so the console shows no 404s after the first page load
  (`7040543`).
- `/healthz` could report a stale `APP_VERSION` from `.env` (`f16d46b`).
- api could start before Postgres accepted connections on a first install
  (`fa1597d`).

## Known Issues

- Google's careers site sometimes resets TLS handshakes from mainland China
  networks. Requests are retried and partial results are kept, but a run can
  still come back with fewer locations.
- From non-China networks, `talent.alibaba.com` detail pages redirect to the
  group homepage; the links work from China.
- Sources marked `assessment_pending` in the registry (for example McKinsey,
  Bain, PwC, EY) are listed but not collected yet.
