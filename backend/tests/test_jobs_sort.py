from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.jobs import list_jobs
from app.api.routes.rss import rss_all
from app.db.session import Base
from app.models.job import Job
from app.schemas.job import JobOut

NOW = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)


def _row(source_job_id, *, posted_days=None, seen_days=0, llm=None, rule=50.0):
    return Job(
        source="official_test", source_job_id=source_job_id, company="Acme", title="Security Lead",
        location="上海", description="d", apply_url=f"https://e.x/{source_job_id}",
        source_url=f"https://e.x/{source_job_id}", content_hash=source_job_id,
        posted_at=None if posted_days is None else NOW - timedelta(days=posted_days),
        first_seen_at=NOW - timedelta(days=seen_days), last_seen_at=NOW,
        match_score=rule, llm_fit_score=llm, llm_verdict=None if llm is None else "possible_fit",
    )


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            _row("old-strong", posted_days=40, seen_days=40, llm=92),
            _row("new-weak", posted_days=1, seen_days=1, llm=61),
            _row("mid-good", posted_days=10, seen_days=10, llm=80),
            _row("tie-newer", posted_days=2, seen_days=2, llm=80),
            _row("undated-recent", posted_days=None, seen_days=3, rule=70),
            _row("unscored-new", posted_days=0, seen_days=0, rule=40),
        ])
        session.commit()
        yield session


def _order(db, **filters):
    params = dict(limit=100, min_score=0, source=None, q=None, offset=0, location_category=None,
                  min_llm_score=None, llm_verdict=None, status="active", mark=None)
    params.update(filters)
    return [job.source_job_id for job in list_jobs(db=db, **params)]


def test_newest_first_uses_first_seen_for_undated_jobs(db):
    # Before, an undated row sorted as NULL, which Postgres places first.
    assert _order(db) == [
        "unscored-new", "new-weak", "tie-newer", "undated-recent", "mid-good", "old-strong",
    ]
    assert _order(db, sort="newest") == _order(db)


def test_ai_score_sort_puts_best_fit_first_and_unscored_last(db):
    assert _order(db, sort="ai_score") == [
        "old-strong", "tie-newer", "mid-good", "new-weak", "undated-recent", "unscored-new",
    ]


def test_ai_score_sort_keeps_the_filters(db):
    assert _order(db, sort="ai_score", min_llm_score=70) == ["old-strong", "tie-newer", "mid-good"]
    assert _order(db, sort="ai_score", limit=2, offset=1) == ["tie-newer", "mid-good"]


def test_unknown_sort_is_rejected(db):
    with pytest.raises(HTTPException) as error:
        _order(db, sort="random")
    assert error.value.status_code == 422


def test_job_output_includes_first_seen_for_undated_jobs(db):
    row = db.query(Job).filter(Job.source_job_id == "undated-recent").one()
    out = JobOut.model_validate(row)
    assert out.posted_at is None
    assert out.first_seen_at is not None


def test_rss_lists_newest_first_with_undated_jobs_by_first_seen(db):
    # feedgen prepends entries by default, which reversed the query order.
    xml = rss_all(db=db).body.decode()
    titles = [line for line in xml.splitlines() if "<link>https://e.x/" in line]
    assert [line.strip()[len("<link>https://e.x/"):-len("</link>")] for line in titles] == [
        "unscored-new", "new-weak", "tie-newer", "undated-recent", "mid-good", "old-strong",
    ]
