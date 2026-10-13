# Job Intelligence Project

## Project Overview

Build a personal Job Intelligence platform for discovering, monitoring, ranking, and tracking job opportunities.

The system is NOT simply a web crawler.

It should be designed as:

Job Sources  
    -> Collectors  
    -> Normalization  
    -> Deduplication  
    -> Job Matching  
    -> PostgreSQL  
    -> RSS / Web Dashboard / Notifications  
    -> One-click application

The primary user is a senior cloud/security professional looking for high-quality career opportunities in China, Hong Kong, Singapore, APAC, and selected international markets.

## Primary Goals

1. Monitor major company career websites.
2. Monitor Chinese job platforms such as 51job and Liepin.
3. Ingest LinkedIn job alerts through email where appropriate.
4. Detect newly published jobs.
5. Normalize jobs from different sources into a unified schema.
6. Deduplicate identical or highly similar jobs.
7. Calculate job relevance against the user's career profile.
8. Provide RSS feeds.
9. Provide direct application links.
10. Maintain job history and job status.
11. Run continuously as a Dockerized service.

## Phase 1 Scope

MVP sources:

- Company careers: Alibaba, Microsoft, Huawei
- Chinese platforms: 51job, Liepin
- International: LinkedIn Job Alerts via email ingestion

The architecture must make it easy to add more sources later.

## Data Collection Priority

For each source, prefer:

1. Official API
2. JSON endpoint
3. RSS / Atom
4. Sitemap
5. Server-rendered HTML
6. Browser automation
7. Headless browser

Do not use browser automation if a stable API or public structured endpoint is available.

## Reliability and Safety Principles

- Do not bypass CAPTCHA, anti-bot controls, authentication, rate limits, or access restrictions.
- For authenticated platforms, only use access the user is legitimately authorized to use.
- Use conservative request rates and per-collector timeouts.
- Log failures without stopping the whole system.

## Technology Stack (Phase 1)

- Backend: Python, FastAPI, PostgreSQL, SQLAlchemy, APScheduler
- Collection: httpx, BeautifulSoup, Playwright only when necessary
- RSS: feedgen
- Frontend: Next.js (optional in Phase 1)
- Deployment: Docker, Docker Compose, Nginx (Nginx optional in Phase 1)

Optional later components (not in Phase 1 unless justified):

- Redis, Celery, pgvector, LLM/embeddings, Telegram notifications
