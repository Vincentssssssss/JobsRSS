from datetime import datetime, timezone

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
