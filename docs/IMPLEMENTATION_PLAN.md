# JobsRSS Phase 1 Implementation Plan

> For this phase, keep solutions simple and avoid optional infrastructure unless required by current scope.

## Goal

Deliver an MVP that continuously ingests jobs from initial sources, normalizes and deduplicates records, computes deterministic relevance scoring, and publishes RSS feeds with direct apply links.

## Scope

In scope:

- Microsoft + 51job + LinkedIn email ingestion end-to-end first
- Extend to Alibaba, Huawei, and Liepin after MVP pipeline validation
- Dockerized deployment with PostgreSQL, API, and worker services

Out of scope:

- Automatic application submission
- CAPTCHA bypassing or anti-bot evasion
- LLM/embedding ranking
- Celery/Redis

## Architecture Summary

Pipeline:

1. Collector fetches raw source data.
2. Normalizer maps raw records into unified schema.
3. Deduplication identifies duplicates and updates last-seen metadata.
4. Matcher computes 0-100 relevance score from configurable rules.
5. Repository persists job records in PostgreSQL.
6. RSS endpoints render filtered views from stored records.

## Task Breakdown

### Task 1: Project Skeleton and Configuration

- Create module structure for `app/api`, `app/collectors`, `app/normalization`, `app/dedup`, `app/matching`, `app/scheduler`, and `app/db`.
- Add `.env.example` and externalized config loading.
- Add base logging configuration.

Acceptance:

- Service starts with `docker compose up -d`.
- Health endpoint responds successfully.

### Task 2: Database Schema and Persistence

- Implement SQLAlchemy models for unified Job schema.
- Add indexes and uniqueness constraints:
  - `(source, source_job_id)` unique
  - `posted_at`, `match_score`, `last_seen_at` indexes
- Add migration baseline and repository methods.

Acceptance:

- Insert/update/query paths work with tests.
- Data persists across container restarts.

### Task 3: Collector Interface and Shared Runtime

- Implement `BaseCollector` interface with:
  - `fetch_raw()`
  - `normalize(raw)`
  - `collect()`
- Add per-collector timeout, conservative retry, and rate limiting.

Acceptance:

- Collectors can be instantiated and tested independently.

### Task 4: First End-to-End Sources

- Implement `microsoft` collector using highest-priority structured source available.
- Implement `job51` collector using best available source without unsafe automation.
- Implement `linkedin_email` ingestion collector.

Acceptance:

- All three sources ingest into unified pipeline.
- Records include valid `apply_url` fallback selection.

### Task 5: Normalization, Deduplication, and Matching

- Implement normalization for title/company/location/date/description.
- Implement dedup:
  - Primary key: `source + source_job_id`
  - Secondary heuristic: `company + normalized_title + location`
- Implement deterministic scoring engine from config (0-100).

Acceptance:

- Duplicate jobs do not create duplicate active records.
- Scores are produced for all stored jobs.

### Task 6: RSS Endpoints and Query APIs

- Add endpoints:
  - `/rss/all.xml`
  - `/rss/high-match.xml`
  - `/rss/cloud-security.xml`
  - `/rss/company/{company}.xml`
- Ensure entries include company, title, location, summary, published date, and apply URL.

Acceptance:

- Feeds are valid XML and readable by common RSS readers.

### Task 7: Scheduler and Failure Isolation

- Add APScheduler jobs per source with isolated error handling.
- Configure default intervals:
  - Company sites: 10-30 min
  - 51job/Liepin: 15-30 min
  - LinkedIn email: periodic polling

Acceptance:

- One collector failure does not stop others.
- Execution metrics are logged per run.

### Task 8: Docker Deployment

- Finalize `docker-compose.yml` for `postgres`, `api`, `worker`.
- Add volumes and restart policies.

Acceptance:

- All services start and remain healthy under normal conditions.

## Testing Plan

Required tests:

- Normalization unit tests
- Deduplication unit tests
- Matching/scoring unit tests
- Collector contract tests
- RSS endpoint integration tests
- Scheduler failure isolation test

## Operational Guardrails

- Respect source terms and access restrictions.
- Never commit secrets.
- Use conservative request frequency.
- Document each collector's limitations and data provenance.
