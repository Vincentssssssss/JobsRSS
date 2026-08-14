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

## LinkedIn Job Alerts via IMAP

Phase 1 uses email ingestion instead of authenticated web automation.

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