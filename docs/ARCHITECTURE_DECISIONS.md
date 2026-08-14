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
