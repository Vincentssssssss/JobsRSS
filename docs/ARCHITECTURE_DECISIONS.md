# Architecture Decisions

## ADR-001 LinkedIn

Decision:
Use LinkedIn Job Alert email ingestion in Phase 1.

Reason:
Avoid making the system dependent on authenticated web automation.

---

## ADR-002 Scheduler

Decision:
Use APScheduler.

Reason:
Phase 1 workload is small and does not justify Celery/Redis.

---

## ADR-003 Database

Decision:
Use PostgreSQL.

Reason:
Relational job metadata, filtering, history and future pgvector support.

---

## ADR-004 Authenticated Platform Collection Mode

Decision:
Support an optional authenticated browser-collection mode for LinkedIn, 51job, and Liepin, while keeping email ingestion available as fallback.

Reason:
User workflow prefers direct account-based filtering from platform search pages. Implementation remains opt-in and disabled by default, with conservative scheduling and explicit credentials/session configuration.
