from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector, CollectorMeta
from app.db.session import Base
from app.models.job import Job
from app.pipeline import close_rows_from_removed_sources, ingest_collector
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


def test_llm_rescoring_does_not_reset_the_stale_clock():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    old_time = datetime.now(timezone.utc) - timedelta(days=30)
    current_time = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(
            Job(
                source="linkedin_auth",
                source_job_id="rescored-li",
                company="Old Co",
                title="Security Architect",
                location="Hong Kong",
                country="Hong Kong",
                description="Old role",
                apply_url="https://www.linkedin.com/jobs/view/333/",
                source_url="https://www.linkedin.com/jobs/view/333/",
                posted_at=current_time,
                updated_at=old_time,
                first_seen_at=old_time,
                last_seen_at=old_time,
                content_hash="rescored-li",
                match_score=70,
                status="active",
            )
        )
        db.commit()

        stored = db.query(Job).filter(Job.source_job_id == "rescored-li").one()
        stored.llm_fit_score = 93
        stored.llm_verdict = "strong_fit"
        db.commit()
        db.refresh(stored)
        assert stored.last_seen_at.replace(tzinfo=timezone.utc) == old_time

        current = UnifiedJob(
            source="linkedin_auth",
            source_job_id="current-li",
            company="Current Co",
            title="Current role",
            location="Hong Kong",
            country="Hong Kong",
            description="Current role",
            apply_url="https://www.linkedin.com/jobs/view/444/",
            source_url="https://www.linkedin.com/jobs/view/444/",
            posted_at=current_time,
            updated_at=current_time,
            first_seen_at=current_time,
            last_seen_at=current_time,
            content_hash="current-li",
        )
        ingest_collector(db, StubCollector(current))

        db.refresh(stored)
        assert stored.status == "closed"


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


def test_ingest_applies_early_career_guard_without_waiting_for_llm_rerank():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        early_career = UnifiedJob(
            source="official_alibaba",
            source_job_id="campus-direct",
            company="Alibaba / Alibaba Cloud",
            title="安全技术工程师",
            location="上海",
            country="China",
            description=(
                "Basic Information\n"
                "Graduation Dates: 2026-11-01 - 2027-10-31\n"
                "Hiring Program: Alibaba 2027 Graduate Recruitment"
            ),
            apply_url="https://campus-talent.alibaba.com/campus/position/199907620043",
            source_url="https://campus-talent.alibaba.com/campus/position/199907620043",
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash="campus-direct",
            match_score=15,
            status="active",
            location_category="confirmed_shanghai",
        )
        ingest_collector(db, StubOfficialCollector(early_career))
        stored = db.query(Job).filter(Job.source_job_id == "campus-direct").one()

        assert stored.llm_fit_score == 0
        assert stored.llm_verdict == "not_fit"
        assert stored.llm_role_family == "early_career_program"
        assert stored.llm_model == "heuristic-early-career-guard"


class StubAlibabaSocialCollector(StubCollector):
    meta = CollectorMeta(
        source_name="official_alibaba",
        source_type="company_site",
        collection_method="test",
        polling_interval_minutes=360,
    )
    retired_source_url_prefixes = ("https://campus-talent.alibaba.com",)


def test_rows_from_retired_portal_are_closed_on_next_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    def alibaba_job(source_job_id: str, url: str) -> Job:
        return Job(
            source="official_alibaba",
            source_job_id=source_job_id,
            company="Alibaba / Alibaba Cloud",
            title="安全工程师",
            location="上海",
            country="China",
            description="安全工程师",
            apply_url=url,
            source_url=url,
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=source_job_id,
            match_score=0,
            status="active",
            location_category="confirmed_shanghai",
        )

    social_url = "https://talent.alibaba.com/off-campus/position-detail?positionId="
    with Session(engine) as db:
        db.add(alibaba_job("campus", "https://campus-talent.alibaba.com/campus/position/1"))
        db.add(alibaba_job("social-old", f"{social_url}2"))
        db.commit()

        current = UnifiedJob(
            source="official_alibaba",
            source_job_id="social-new",
            company="Alibaba / Alibaba Cloud",
            title="应用安全专家",
            location="上海",
            country="China",
            description="应用安全专家",
            apply_url=f"{social_url}3",
            source_url=f"{social_url}3",
            content_hash="social-new",
            location_category="confirmed_shanghai",
        )
        ingest_collector(db, StubAlibabaSocialCollector(current))

        statuses = {job.source_job_id: job.status for job in db.query(Job).all()}
        assert statuses == {
            "campus": "closed",
            "social-old": "active",
            "social-new": "active",
        }


def test_rows_from_removed_sources_are_closed():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    def job(source: str, source_job_id: str) -> Job:
        return Job(
            source=source,
            source_job_id=source_job_id,
            company="Microsoft",
            title="Cloud Security Architect",
            location="Hong Kong",
            country="Hong Kong",
            description="Lead cloud security architecture.",
            apply_url="https://careers.microsoft.com/",
            source_url="https://careers.microsoft.com/",
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=source_job_id,
            match_score=90,
            status="active",
        )

    with Session(engine) as db:
        db.add(job("microsoft", "msft-demo-001"))
        db.add(job("official_microsoft", "1970393557020991"))
        db.add(job("linkedin_auth", "4451337319"))
        db.commit()

        closed = close_rows_from_removed_sources(
            db, {"official_microsoft", "linkedin_auth"}
        )

        statuses = {row.source: row.status for row in db.query(Job).all()}
        assert closed == 1
        assert statuses == {
            "microsoft": "closed",
            "official_microsoft": "active",
            "linkedin_auth": "active",
        }


class StubLiepinCollector(StubCollector):
    meta = CollectorMeta(
        source_name="liepin_auth",
        source_type="job_platform",
        collection_method="test",
        polling_interval_minutes=20,
    )


class EmptyLiepinCollector(StubLiepinCollector):
    def __init__(self) -> None:
        pass

    def collect(self):
        return []


def _stale_liepin_job(days_ago: int) -> Job:
    seen = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return Job(
        source="liepin_auth",
        source_job_id="old-lp",
        company="Old Co",
        title="安全经理",
        location="上海",
        country="China",
        description="安全经理",
        apply_url="https://www.liepin.com/job/111.shtml",
        source_url="https://www.liepin.com/job/111.shtml",
        posted_at=seen,
        updated_at=seen,
        first_seen_at=seen,
        last_seen_at=seen,
        content_hash="old-lp",
        match_score=0,
        status="active",
    )


def test_stale_liepin_job_is_closed_after_run_that_found_jobs():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as db:
        db.add(_stale_liepin_job(days_ago=10))
        db.commit()

        current = UnifiedJob(
            source="liepin_auth",
            source_job_id="current-lp",
            company="Current Co",
            title="云安全经理",
            location="上海",
            country="China",
            description="云安全经理",
            apply_url="https://www.liepin.com/job/222.shtml",
            source_url="https://www.liepin.com/job/222.shtml",
            posted_at=now,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash="current-lp",
        )
        ingest_collector(db, StubLiepinCollector(current))

        assert db.query(Job).filter(Job.source_job_id == "old-lp").one().status == "closed"
        assert db.query(Job).filter(Job.source_job_id == "current-lp").one().status == "active"


def test_liepin_jobs_stay_active_when_run_finds_nothing():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(_stale_liepin_job(days_ago=10))
        db.commit()

        ingest_collector(db, EmptyLiepinCollector())

        assert db.query(Job).filter(Job.source_job_id == "old-lp").one().status == "active"


def test_card_with_closed_marker_is_ingested_as_closed():
    from app.collectors.liepin_auth import LiepinAuthCollector

    collector = LiepinAuthCollector()
    job = collector.normalize(
        {
            "source_job_id": "lp-closed",
            "title": "云安全经理",
            "company": "Acme",
            "location": "上海",
            "description": "云安全经理 Acme 上海 该职位已停止招聘",
            "apply_url": "https://www.liepin.com/job/333.shtml",
            "source_url": "https://www.liepin.com/job/333.shtml",
            "content_hash": "lp-closed",
        }
    )

    assert job.status == "closed"


class StubLinkedInEmailCollector(StubCollector):
    meta = CollectorMeta(
        source_name="linkedin_email",
        source_type="email",
        collection_method="test",
        polling_interval_minutes=15,
    )


class EmptyLinkedInEmailCollector(StubLinkedInEmailCollector):
    def __init__(self) -> None:
        pass

    def collect(self):
        return []


def _linkedin_email_job(source_job_id: str, days_since_seen: int) -> Job:
    seen = datetime.now(timezone.utc) - timedelta(days=days_since_seen)
    return Job(
        source="linkedin_email",
        source_job_id=source_job_id,
        company="Acme",
        title="Security Manager",
        location="Singapore",
        country="Singapore",
        description="Security Manager",
        apply_url=f"https://www.linkedin.com/comm/jobs/view/{source_job_id}/",
        source_url=f"https://www.linkedin.com/comm/jobs/view/{source_job_id}/",
        posted_at=seen,
        updated_at=seen,
        first_seen_at=seen,
        last_seen_at=seen,
        content_hash=source_job_id,
        match_score=70,
        status="active",
    )


def _linkedin_email_incoming(source_job_id: str) -> UnifiedJob:
    now = datetime.now(timezone.utc)
    return UnifiedJob(
        source="linkedin_email",
        source_job_id=source_job_id,
        company="Acme",
        title="Security Manager",
        location="Singapore",
        country="Singapore",
        description="Security Manager",
        apply_url=f"https://www.linkedin.com/comm/jobs/view/{source_job_id}/",
        source_url=f"https://www.linkedin.com/comm/jobs/view/{source_job_id}/",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=source_job_id,
    )


def test_stale_linkedin_email_job_is_closed_after_run_that_found_jobs():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(_linkedin_email_job("4500000001", days_since_seen=20))
        db.add(_linkedin_email_job("4500000002", days_since_seen=3))
        db.commit()

        incoming = _linkedin_email_incoming("4500000003")
        incoming.company = "Beta Bank"
        incoming.title = "Head of Cloud Security"
        ingest_collector(db, StubLinkedInEmailCollector(incoming))

        statuses = {job.source_job_id: job.status for job in db.query(Job).all()}
        assert statuses == {
            "4500000001": "closed",
            "4500000002": "active",
            "4500000003": "active",
        }


def test_linkedin_email_jobs_stay_active_when_run_finds_nothing():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(_linkedin_email_job("4500000001", days_since_seen=20))
        db.commit()

        ingest_collector(db, EmptyLinkedInEmailCollector())

        assert db.query(Job).one().status == "active"


def test_reopened_row_is_queued_for_immediate_reverification():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        closed = _linkedin_email_job("4500000001", days_since_seen=1)
        closed.status = "closed"
        closed.last_verified_at = datetime.now(timezone.utc)
        verified_open = _linkedin_email_job("4500000002", days_since_seen=1)
        verified_open.last_verified_at = datetime.now(timezone.utc)
        db.add_all([closed, verified_open])
        db.commit()

        ingest_collector(db, StubLinkedInEmailCollector(_linkedin_email_incoming("4500000001")))
        ingest_collector(db, StubLinkedInEmailCollector(_linkedin_email_incoming("4500000002")))

        reopened = db.query(Job).filter(Job.source_job_id == "4500000001").one()
        still_open = db.query(Job).filter(Job.source_job_id == "4500000002").one()
        assert reopened.status == "active"
        assert reopened.last_verified_at is None
        assert still_open.last_verified_at is not None
