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