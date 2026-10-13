from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.official.collectors.catalog import OFFICIAL_COLLECTOR_FACTORIES
from app.scheduler import runner
from app.scheduler.runner import build_scheduler, current_source_names, run_daily_digest_job


def test_scheduler_runs_late_jobs_once_instead_of_skipping_them():
    scheduler = build_scheduler(BackgroundScheduler)
    scheduler.start(paused=True)
    try:
        jobs = scheduler.get_jobs()
        assert jobs
        for job in jobs:
            assert job.misfire_grace_time is None, job.name
            assert job.coalesce is True, job.name
            assert job.max_instances == 1, job.name
    finally:
        scheduler.shutdown(wait=False)


def test_every_interval_job_first_runs_at_boot():
    scheduler = build_scheduler(BackgroundScheduler)
    scheduler.start(paused=True)
    try:
        latest_first_run = datetime.now(timezone.utc) + timedelta(
            seconds=30 * len(OFFICIAL_COLLECTOR_FACTORIES)
        )
        interval_jobs = [
            job for job in scheduler.get_jobs() if job.func is not run_daily_digest_job
        ]
        assert len(interval_jobs) == 6 + len(OFFICIAL_COLLECTOR_FACTORIES)
        for job in interval_jobs:
            assert job.next_run_time <= latest_first_run, job.name
    finally:
        scheduler.shutdown(wait=False)


def test_worker_applies_schema_before_scheduling_and_retries_while_db_boots(monkeypatch):
    calls = []

    def flaky_init_db():
        calls.append("init_db")
        if calls.count("init_db") < 3:
            raise ConnectionError("database is starting up")

    class FakeScheduler:
        def start(self):
            calls.append("start")

    monkeypatch.setattr(runner, "init_db", flaky_init_db)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        runner, "close_rows_from_removed_sources_job", lambda: calls.append("close_removed")
    )
    monkeypatch.setattr(runner, "build_scheduler", lambda: FakeScheduler())

    runner.start_scheduler()

    assert calls == ["init_db", "init_db", "init_db", "close_removed", "start"]


def test_current_source_names_cover_every_collector():
    names = current_source_names()

    assert {"linkedin_auth", "linkedin_email", "liepin_auth", "job51_auth"} <= names
    assert "official_microsoft" in names
    assert "official_alibaba" in names
    assert "microsoft" not in names
