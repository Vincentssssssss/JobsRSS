from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectorMeta
from app.db.session import Base
from app.models.job import Job
from app.pipeline import ingest_collector
from app.schemas.job import UnifiedJob


class StubCollector(BaseCollector):
    meta = CollectorMeta(
        source_name="linkedin_auth",
        source_type="job_platform",
        collection_method="test",
        polling_interval_minutes=20,
    )

    def __init__(self, job: UnifiedJob) -> None:
        self.job = job

    def fetch_raw(self):
        return []

    def normalize(self, raw):
        return self.job

    def collect(self):
        return [self.job]


class StubOfficialCollector(StubCollector):
    meta = CollectorMeta(
        source_name="official_test_company",
        source_type="company_site",
        collection_method="test",
        polling_interval_minutes=360,
    )


class StubLinkedInMissingStateCollector(BaseCollector):
    meta = CollectorMeta(
        source_name="linkedin_auth",
        source_type="job_platform",
        collection_method="test",
        polling_interval_minutes=20,
    )
    skip_publish_due_to_missing_state = True

    def fetch_raw(self):
        return []

    def normalize(self, raw):
        raise NotImplementedError

    def collect(self):
        return []


def test_existing_job_receives_enriched_company_country_and_posted_time():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    posted_at = datetime(2026, 8, 20, tzinfo=timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="123",
                company="Unknown Company",
                title="Cloud Security Architect",
                location="Unknown",
                country="Unknown",
                description="Short fallback",
                apply_url="https://www.linkedin.com/jobs/view/123/",
                source_url="https://www.linkedin.com/jobs/view/123/",
                posted_at=None,
                updated_at=None,
                first_seen_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                content_hash="old",
                match_score=0,
                status="active",
            )
        )
        db.commit()

        enriched = UnifiedJob(
            source="linkedin_auth",
            source_job_id="123",
            company="Acme Cloud",
            title="Principal Cloud Security Architect",
            location="Shanghai",
            country="China",
            description="Own multi-cloud security architecture and IAM.",
            apply_url="https://jobs.acme.com/123",
            source_url="https://www.linkedin.com/jobs/view/123/",
            posted_at=posted_at,
            updated_at=posted_at,
            first_seen_at=posted_at,
            last_seen_at=posted_at,
            content_hash="new",
            enrichment_source="workday",
        )

        ingest_collector(db, StubCollector(enriched))
        stored = db.query(Job).filter(Job.source_job_id == "123").one()

        assert stored.company == "Acme Cloud"
        assert stored.country == "China"
        assert stored.posted_at.replace(tzinfo=timezone.utc) == posted_at
        assert stored.apply_url == "https://jobs.acme.com/123"


def test_fallback_refresh_does_not_replace_existing_authoritative_fields():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    official_description = "Own cloud security architecture, IAM, DevSecOps, and multi-cloud controls." * 3

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="456",
                company="Acme Cloud",
                title="Cloud Security Architect",
                location="Shanghai",
                country="China",
                description=official_description,
                apply_url="https://jobs.acme.com/456",
                source_url="https://www.linkedin.com/jobs/view/456/",
                posted_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                updated_at=None,
                first_seen_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc),
                content_hash="official",
                match_score=90,
                status="active",
                enrichment_source="workday",
            )
        )
        db.commit()

        fallback = UnifiedJob(
            source="linkedin_auth",
            source_job_id="456",
            company="LinkedIn Parsed Company",
            title="Updated LinkedIn Title",
            location="Singapore",
            country="Singapore",
            description=(
                "This is a longer LinkedIn fallback description that would otherwise replace "
                "the existing official company career page content."
            ),
            apply_url="https://www.linkedin.com/jobs/view/456/",
            source_url="https://www.linkedin.com/jobs/view/456/",
            posted_at=None,
            updated_at=datetime.now(timezone.utc),
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            content_hash="fallback",
        )

        ingest_collector(db, StubCollector(fallback))
        stored = db.query(Job).filter(Job.source_job_id == "456").one()

        assert stored.company == "Acme Cloud"
        assert stored.title == "Cloud Security Architect"
        assert stored.location == "Shanghai"
        assert stored.description == official_description
        assert stored.apply_url == "https://jobs.acme.com/456"
        assert stored.posted_at is not None


def test_stale_official_job_is_closed_after_successful_source_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    old_time = datetime.now(timezone.utc) - timedelta(days=45)

    with Session(engine) as db:
        db.add(
            Job(
                source="official_test_company",
                source_job_id="old",
                company="Acme",
                title="Old role",
                location="Shanghai",
                country="China",
                description="Old role",
                apply_url="https://jobs.acme.example/old",
                source_url="https://jobs.acme.example/old",
                posted_at=old_time,
                updated_at=old_time,
                first_seen_at=old_time,
                last_seen_at=old_time,
                content_hash="old",
                match_score=0,
                status="active",
                location_category="confirmed_shanghai",
            )
        )
        db.commit()

        current = UnifiedJob(
            source="official_test_company",
            source_job_id="current",
            company="Acme",
            title="Current role",
            location="Shanghai",
            country="China",
            description="Current role",
            apply_url="https://jobs.acme.example/current",
            source_url="https://jobs.acme.example/current",
            content_hash="current",
            location_category="confirmed_shanghai",
        )
        ingest_collector(db, StubOfficialCollector(current))

        stale = db.query(Job).filter(Job.source_job_id == "old").one()
        assert stale.status == "closed"


def test_stale_linkedin_job_is_closed_after_successful_linkedin_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    old_time = datetime.now(timezone.utc) - timedelta(days=30)
    current_time = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="old-li",
                company="Old Co",
                title="Old role",
                location="Shanghai",
                country="China",
                description="Old role",
                apply_url="https://www.linkedin.com/jobs/view/111/",
                source_url="https://www.linkedin.com/jobs/view/111/",
                posted_at=old_time,
                updated_at=old_time,
                first_seen_at=old_time,
                last_seen_at=old_time,
                content_hash="old-li",
                match_score=0,
                status="active",
            )
        )
        db.commit()

        current = UnifiedJob(
            source="linkedin_auth",
            source_job_id="current-li",
            company="Current Co",
            title="Current role",
            location="Shanghai",
            country="China",
            description="Current role",
            apply_url="https://www.linkedin.com/jobs/view/222/",
            source_url="https://www.linkedin.com/jobs/view/222/",
            posted_at=current_time,
            updated_at=current_time,
            first_seen_at=current_time,
            last_seen_at=current_time,
            content_hash="current-li",
        )
        ingest_collector(db, StubCollector(current))

        stale = db.query(Job).filter(Job.source_job_id == "old-li").one()
        assert stale.status == "closed"


def test_linkedin_jobs_are_closed_when_state_missing_flag_is_set():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="li-active",
                company="Acme",
                title="Security Architect",
                location="Shanghai",
                country="China",
                description="Existing job",
                apply_url="https://www.linkedin.com/jobs/view/123/",
                source_url="https://www.linkedin.com/jobs/view/123/",
                posted_at=now,
                updated_at=now,
                first_seen_at=now,
                last_seen_at=now,
                content_hash="li-active",
                match_score=80,
                status="active",
            )
        )
        db.commit()

        ingest_collector(db, StubLinkedInMissingStateCollector())
        stored = db.query(Job).filter(Job.source_job_id == "li-active").one()

        assert stored.status == "closed"


def test_closed_job_does_not_suppress_new_repost_with_new_source_id():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="official_test_company",
                source_job_id="closed-id",
                company="Acme",
                title="Cloud Security Architect",
                location="Shanghai",
                country="China",
                description="Previous posting",
                apply_url="https://jobs.acme.example/closed",
                source_url="https://jobs.acme.example/closed",
                posted_at=now,
                updated_at=now,
                first_seen_at=now,
                last_seen_at=now,
                content_hash="closed",
                match_score=80,
                status="closed",
                location_category="confirmed_shanghai",
            )
        )
        db.commit()

        repost = UnifiedJob(
            source="official_test_company",
            source_job_id="repost-id",
            company="Acme",
            title="Cloud Security Architect",
            location="Shanghai",
            country="China",
            description="New posting",
            apply_url="https://jobs.acme.example/repost",
            source_url="https://jobs.acme.example/repost",
            content_hash="repost",
            location_category="confirmed_shanghai",
        )
        stats = ingest_collector(db, StubOfficialCollector(repost))

        assert stats.new == 1
        assert db.query(Job).count() == 2
        assert (
            db.query(Job)
            .filter(Job.source_job_id == "repost-id")
            .one()
            .status
            == "active"
        )


def test_content_change_resets_cached_llm_match():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="llm-reset",
                company="Acme",
                title="Cloud Security Architect",
                location="Shanghai",
                country="China",
                description="Initial description",
                apply_url="https://jobs.acme.example/llm-reset",
                source_url="https://jobs.acme.example/llm-reset",
                posted_at=now,
                updated_at=now,
                first_seen_at=now,
                last_seen_at=now,
                content_hash="old-hash",
                match_score=80,
                status="active",
                llm_fit_score=92,
                llm_verdict="strong_fit",
                llm_role_family="cloud_security",
                llm_match_reasons="Existing reason",
                llm_model="gpt-4o-mini",
            )
        )
        db.commit()

        refreshed = UnifiedJob(
            source="linkedin_auth",
            source_job_id="llm-reset",
            company="Acme",
            title="Cloud Security Architect",
            location="Shanghai",
            country="China",
            description="Updated description with new responsibilities",
            apply_url="https://jobs.acme.example/llm-reset",
            source_url="https://jobs.acme.example/llm-reset",
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash="new-hash",
        )
        ingest_collector(db, StubCollector(refreshed))
        stored = db.query(Job).filter(Job.source_job_id == "llm-reset").one()

        assert stored.llm_fit_score is None
        assert stored.llm_verdict is None
        assert stored.llm_match_reasons is None
        assert stored.llm_model is None
