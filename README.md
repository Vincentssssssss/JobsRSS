# JobsRSS

Phase 1 monorepo for a personal Job Intelligence platform.

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