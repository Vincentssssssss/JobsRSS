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
        assert len(interval_jobs) == 7 + len(OFFICIAL_COLLECTOR_FACTORIES)
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


class _FlakyCollector:
    def __init__(self, failures):
        self.meta = type("Meta", (), {"source_name": "official_flaky"})()
        self.failures = list(failures)
        self.calls = 0


def _patch_ingest(monkeypatch, collector):
    def fake_ingest(db, target):
        target.calls += 1
        if target.failures:
            raise target.failures.pop(0)
        return type("Stats", (), {"found": 3, "new": 3, "duplicates": 0, "errors": 0})()

    monkeypatch.setattr(runner, "ingest_collector", fake_ingest)
    monkeypatch.setattr(runner, "SessionLocal", lambda: type("DB", (), {"close": lambda self: None, "rollback": lambda self: None})())
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)


def test_collector_run_is_retried_once_after_a_network_failure(monkeypatch, caplog):
    import httpx

    collector = _FlakyCollector([httpx.ConnectTimeout("_ssl.c:994: The handshake operation timed out")])
    _patch_ingest(monkeypatch, collector)

    with caplog.at_level("INFO"):
        runner._run_collector(collector)

    assert collector.calls == 2
    assert "collector_run_retry source=official_flaky" in caplog.text
    assert "collector_run source=official_flaky" in caplog.text
    assert "collector_run_failed" not in caplog.text


def test_wrapped_network_failure_is_retried_and_reported_when_it_persists(monkeypatch, caplog):
    import httpx

    def wrapped():
        try:
            raise httpx.ConnectError("Connection reset by peer")
        except httpx.ConnectError as exc:
            try:
                raise RuntimeError("listing request failed") from exc
            except RuntimeError as wrapped_exc:
                return wrapped_exc

    collector = _FlakyCollector([wrapped(), wrapped()])
    _patch_ingest(monkeypatch, collector)

    with caplog.at_level("INFO"):
        runner._run_collector(collector)

    assert collector.calls == 2
    assert "collector_run_failed source=official_flaky" in caplog.text


def test_non_network_collector_errors_are_not_retried(monkeypatch, caplog):
    collector = _FlakyCollector([ValueError("unexpected payload")])
    _patch_ingest(monkeypatch, collector)

    with caplog.at_level("INFO"):
        runner._run_collector(collector)

    assert collector.calls == 1
    assert "collector_run_failed source=official_flaky" in caplog.text


def test_current_source_names_cover_every_collector():
    names = current_source_names()

    assert {"linkedin_auth", "linkedin_email", "liepin_auth", "job51_auth"} <= names
    assert "official_microsoft" in names
    assert "official_alibaba" in names
    assert "microsoft" not in names
