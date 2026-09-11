from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.jobs import jobs_source_counts
from app.db.session import Base
from app.models.job import Job


def _make_job(
    *,
    source: str,
    source_job_id: str,
    title: str,
    match_score: float,
    llm_fit_score: float | None,
    llm_verdict: str | None,
    status: str = "active",
    location_category: str = "confirmed_shanghai",
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source=source,
        source_job_id=source_job_id,
        company="Acme",
        title=title,
        location="上海",
        country="China",
        description="Security role for cloud and application protection.",
        apply_url=f"https://example.com/{source_job_id}",
        source_url=f"https://example.com/{source_job_id}",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=f"hash-{source_job_id}",
        match_score=match_score,
        llm_fit_score=llm_fit_score,
        llm_verdict=llm_verdict,
        status=status,
        location_category=location_category,
    )


def test_jobs_source_counts_respects_ai_filters_and_groups_by_source():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all(
            [
                _make_job(
                    source="official_alibaba",
                    source_job_id="a1",
                    title="Senior Security Architect",
                    match_score=90,
                    llm_fit_score=82,
                    llm_verdict="strong_fit",
                ),
                _make_job(
                    source="official_tencent",
                    source_job_id="t1",
                    title="Cloud Security Engineer",
                    match_score=88,
                    llm_fit_score=65,
                    llm_verdict="possible_fit",
                ),
                _make_job(
                    source="liepin_auth",
                    source_job_id="l1",
                    title="Security Operations",
                    match_score=75,
                    llm_fit_score=30,
                    llm_verdict="not_fit",
                ),
                _make_job(
                    source="official_tencent",
                    source_job_id="t-closed",
                    title="Cloud Security Lead",
                    match_score=92,
                    llm_fit_score=91,
                    llm_verdict="strong_fit",
                    status="closed",
                ),
            ]
        )
        db.commit()

        result = jobs_source_counts(
            db=db,
            min_score=0,
            source=None,
            q="security",
            location_category=None,
            min_llm_score=60,
            llm_verdict="strong_fit,possible_fit",
            status="active",
        )

        assert result == {
            "counts": [
                {"source": "official_alibaba", "count": 1},
                {"source": "official_tencent", "count": 1},
            ]
        }


def test_jobs_source_counts_returns_empty_when_llm_verdict_filter_is_invalid():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            _make_job(
                source="official_alibaba",
                source_job_id="a2",
                title="Security Architect",
                match_score=90,
                llm_fit_score=82,
                llm_verdict="strong_fit",
            )
        )
        db.commit()

        result = jobs_source_counts(
            db=db,
            min_score=0,
            source=None,
            q=None,
            location_category=None,
            min_llm_score=None,
            llm_verdict="foo,bar",
            status="active",
        )

        assert result == {"counts": []}
