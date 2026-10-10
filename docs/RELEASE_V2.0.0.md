# JobsRSS v2.0.0

## Release Focus

Stabilize production behavior for multi-source job collection and targeted
ranking with stronger data-quality and failure-control guarantees.

## Included in v2.0.0

- Official-source connector registry and Shanghai-focused location policy.
- LinkedIn quality hardening:
  - strict location-source gating (`detail_jsonld` vs fallback/ambiguous),
  - invalid title suppression (e.g. CTA/promo text),
  - stale active-row cleanup and storage-state safety handling.
- State-gated authenticated collection:
  - `LINKEDIN_REQUIRE_STORAGE_STATE=true` default,
  - safe skip + cache suppression when state is missing.
- Deterministic early-career guard (LLM-independent):
  - applied in ingest pipeline and reranker,
  - campus/new-grad/intern roles forced to `not_fit`.
- LLM runtime resilience:
  - retry + backoff for transient HTTP/network failures,
  - consecutive-failure circuit breaker for rerank runs,
  - structured HTTP error diagnostics with request identifiers.
- Frontend/API stability improvements:
  - proxy fallback behavior,
  - production build/runtime defaults,
  - robust filtering behavior for AI precision mode.

## Version Metadata

- Backend default `APP_VERSION=2.0.0`
- Frontend package version `2.0.0`

## Upgrade

```bash
git pull origin cursor/jobs-intelligence-bootstrap-0a74
docker compose build --no-cache api worker frontend
docker compose up -d --force-recreate api worker frontend
```

## Post-upgrade sanity

```bash
curl -s http://localhost:8000/healthz
curl -s http://localhost:3000/api/backend/healthz
```
