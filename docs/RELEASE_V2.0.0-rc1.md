# JobsRSS v2.0.0-rc1

## Release Goal

Harden collection and publication logic to reduce false-positive search results,
especially LinkedIn location mismatches and login-state drift.

## What Changed

### 1) LinkedIn state-gated publication (strict mode default)

- Added `LINKEDIN_REQUIRE_STORAGE_STATE=true` (default).
- When the state file is missing:
  - collector does not crash,
  - collector run is safely skipped,
  - existing `linkedin_auth` active rows are closed to avoid stale cache publication.

### 2) LinkedIn location quality hardening

- Added explicit detail-location source classification:
  - `jsonld`, `selector`, `ambiguous`.
- When selector text contains timeline/applicant metadata and JSON-LD is missing,
  the location is treated as `ambiguous` and rejected by strict filtering.
- If card location equals search fallback location, it is treated as `fallback`
  and rejected in strict mode.
- Strict mode now rejects location sources: `fallback`, `ambiguous`, `unknown`.

### 3) LinkedIn title quality hardening

- Added invalid title marker filter (for CTA/promo text such as
  "Join LinkedIn"/"加入领英"/"Sign in").
- Added publishability gate to suppress non-job URL leakage and low-quality
  list-card artifacts.

### 4) Cookie export reliability

- Enhanced `backend/scripts/export_storage_state.py`:
  - `--mode cdp` (existing path),
  - `--mode interactive` (new fallback, does not depend on CDP context support).
- CDP compatibility errors now provide actionable hint:
  `Retry with --mode interactive`.

### 5) Stale data lifecycle control

- Added `LINKEDIN_AUTH_STALE_AFTER_DAYS` (default `14`).
- LinkedIn rows not seen beyond this threshold are auto-closed.

### 6) Build reliability under strict TLS/proxy networks

- Hardened backend image dependency bootstrap:
  - pip/self-upgrade step now uses retry + timeout + trusted hosts,
  - avoids early failure in environments where certificate chains are partial
    or proxied.

### 7) System-level early-career guard (LLM-independent)

- Added shared detector module used by both pipeline ingest and reranker.
- Early-career/campus roles are immediately marked:
  - `llm_fit_score = 0`,
  - `llm_verdict = not_fit`,
  - `llm_model = heuristic-early-career-guard`.
- Guard enforcement now runs before network LLM calls, so timeout events do not
  leave campus jobs in AI-positive states.

### 8) LLM provider outage resilience

- Added retry + exponential backoff for transient LLM request failures:
  - status codes `408/425/429/500/502/503/504`,
  - network-level `httpx.RequestError`.
- Added rerank circuit-breaker:
  - stop current rerank run after configured consecutive failures
    (`LLM_ABORT_AFTER_CONSECUTIVE_FAILURES`, default `8`),
  - reduce noisy logs and avoid long-running no-progress cycles during
    upstream incidents.

## Configuration (recommended)

```env
APP_VERSION=2.0.0-rc1
LINKEDIN_AUTH_ENABLED=true
LINKEDIN_AUTH_STORAGE_STATE_PATH=/secrets/linkedin_state.json
LINKEDIN_REQUIRE_STORAGE_STATE=true
LINKEDIN_STRICT_LOCATION_FILTER=true
LINKEDIN_ALLOWED_LOCATIONS=Singapore,Hong Kong,Shanghai,Jiangsu,Zhejiang
LINKEDIN_AUTH_STALE_AFTER_DAYS=14
```

## Verification

- `PYTHONPATH=backend python3 -m pytest backend/tests/collectors/test_linkedin_auth.py backend/tests/test_pipeline_updates.py backend/tests/test_config_defaults.py backend/tests/scripts/test_export_storage_state.py`
- Result: all tests pass.

## Upgrade

```bash
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build api worker frontend
docker compose up -d --force-recreate api worker frontend
```
