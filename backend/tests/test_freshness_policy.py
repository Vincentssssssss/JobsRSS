from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectorMeta
from app.core.config import Settings
from app.db.session import Base
from app.models.job import Job
from app.pipeline import (
    close_outdated_rows,
    close_stale_rows_from_disabled_sources,
    ingest_collector,
)
from app.schemas.job import UnifiedJob

NOW = datetime.now(timezone.utc)


class StubOfficialCollector(BaseCollector):
    meta = CollectorMeta(
        source_name="official_acme",
        source_type="company_site",
        collection_method="test",
        polling_interval_minutes=360,
    )

    def __init__(self, *jobs: UnifiedJob) -> None:
        self.jobs = list(jobs)

    def fetch_raw(self):
        return []

    def normalize(self, raw):
        raise NotImplementedError

    def collect(self):
        return self.jobs


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def _row(source_job_id: str, *, source="official_acme", posted_days=None, first_seen_days=5,
         last_seen_days=0, status="active") -> Job:
    return Job(
        source=source,
        source_job_id=source_job_id,
        company=f"Company {source_job_id}",
        title=f"Security Architect {source_job_id}",
        location="上海",
        country="China",
        description="Own cloud security architecture.",
        apply_url=f"https://jobs.acme.example/{source_job_id}",
        source_url=f"https://jobs.acme.example/{source_job_id}",
        posted_at=None if posted_days is None else NOW - timedelta(days=posted_days),
        updated_at=NOW,
        first_seen_at=NOW - timedelta(days=first_seen_days),
        last_seen_at=NOW - timedelta(days=last_seen_days),
        content_hash=source_job_id,
        match_score=70,
        status=status,
        location_category="confirmed_shanghai",
    )


def _incoming(source_job_id: str, posted_days) -> UnifiedJob:
    return UnifiedJob(
        source="official_acme",
        source_job_id=source_job_id,
        company=f"Company {source_job_id}",
        title=f"Security Architect {source_job_id}",
        location="上海",
        country="China",
        description="Own cloud security architecture.",
        apply_url=f"https://jobs.acme.example/{source_job_id}",
        source_url=f"https://jobs.acme.example/{source_job_id}",
        posted_at=None if posted_days is None else NOW - timedelta(days=posted_days),
        updated_at=NOW,
        first_seen_at=NOW,
        last_seen_at=NOW,
        content_hash=source_job_id,
        location_category="confirmed_shanghai",
    )


def _statuses(db: Session) -> dict:
    db.expire_all()
    return {job.source_job_id: job.status for job in db.query(Job).all()}


def test_sweep_closes_rows_past_max_age_even_when_recently_seen(db):
    db.add_all(
        [
            _row("old-dated", posted_days=75, first_seen_days=75, last_seen_days=0),
            _row("fresh-dated", posted_days=20, first_seen_days=100, last_seen_days=0),
            _row("old-undated", posted_days=None, first_seen_days=95, last_seen_days=0),
            _row("young-undated", posted_days=None, first_seen_days=70, last_seen_days=0),
            _row("already-closed", posted_days=300, status="closed"),
        ]
    )
    db.commit()

    closed = close_outdated_rows(db, _settings(), now=NOW)

    assert closed == 2
    assert _statuses(db) == {
        "old-dated": "closed",
        "fresh-dated": "active",
        "old-undated": "closed",
        "young-undated": "active",
        "already-closed": "closed",
    }


def test_zero_disables_each_max_age_rule(db):
    db.add_all(
        [
            _row("old-dated", posted_days=400),
            _row("old-undated", posted_days=None, first_seen_days=400),
        ]
    )
    db.commit()

    closed = close_outdated_rows(
        db, _settings(job_max_age_days=0, job_max_age_undated_days=0), now=NOW
    )

    assert closed == 0
    assert set(_statuses(db).values()) == {"active"}


def test_ingest_does_not_reopen_or_insert_outdated_postings(db):
    existing = _row("old-dated", posted_days=75, first_seen_days=75, last_seen_days=1)
    existing.status = "closed"
    db.add(existing)
    db.commit()

    ingest_collector(
        db,
        StubOfficialCollector(
            _incoming("old-dated", posted_days=75),
            _incoming("new-but-old", posted_days=120),
            _incoming("new-and-fresh", posted_days=3),
        ),
    )

    assert _statuses(db) == {
        "old-dated": "closed",
        "new-but-old": "closed",
        "new-and-fresh": "active",
    }


def test_reposted_job_with_a_fresh_date_comes_back(db):
    existing = _row("reposted", posted_days=75, first_seen_days=75, last_seen_days=1)
    existing.status = "closed"
    db.add(existing)
    db.commit()

    ingest_collector(db, StubOfficialCollector(_incoming("reposted", posted_days=2)))

    assert _statuses(db) == {"reposted": "active"}


def test_undated_row_keeps_its_first_seen_age_across_sightings(db):
    db.add(_row("evergreen", posted_days=None, first_seen_days=95, last_seen_days=0))
    db.commit()

    ingest_collector(db, StubOfficialCollector(_incoming("evergreen", posted_days=None)))

    assert _statuses(db) == {"evergreen": "closed"}


def test_disabled_collectors_get_their_stale_rule_applied_by_the_sweep(db):
    db.add_all(
        [
            _row("liepin-stale", source="liepin_auth", posted_days=None, last_seen_days=10),
            _row("liepin-recent", source="liepin_auth", posted_days=None, last_seen_days=2),
            _row("job51-stale", source="job51_auth", posted_days=None, last_seen_days=8),
            _row("linkedin-enabled", source="linkedin_auth", posted_days=None, last_seen_days=20),
            _row("official-enabled", posted_days=None, last_seen_days=40),
        ]
    )
    db.commit()

    closed = close_stale_rows_from_disabled_sources(
        db,
        _settings(
            liepin_auth_enabled=False,
            job51_auth_enabled=False,
            linkedin_auth_enabled=True,
            official_sources_enabled=True,
        ),
        now=NOW,
    )

    assert closed == 2
    assert _statuses(db) == {
        "liepin-stale": "closed",
        "liepin-recent": "active",
        "job51-stale": "closed",
        "linkedin-enabled": "active",
        "official-enabled": "active",
    }


def test_disabled_official_sources_use_the_official_stale_window(db):
    db.add_all(
        [
            _row("official-stale", posted_days=None, last_seen_days=40),
            _row("official-recent", posted_days=None, last_seen_days=10),
        ]
    )
    db.commit()

    close_stale_rows_from_disabled_sources(
        db, _settings(official_sources_enabled=False), now=NOW
    )

    assert _statuses(db) == {"official-stale": "closed", "official-recent": "active"}
