from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.jobs import jobs_count, list_jobs, record_job_view, update_job_marks
from app.db.session import Base
from app.models.job import Job
from app.schemas.job import JobMarksUpdate


def _make_job(source_job_id: str, *, status: str = "active") -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source="official_deloitte",
        source_job_id=source_job_id,
        company="Deloitte / 德勤",
        title="Senior Manager - Cyber Defense",
        location="上海",
        country="China",
        description="Cyber defense role.",
        apply_url=f"https://example.com/{source_job_id}",
        source_url=f"https://example.com/{source_job_id}",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=f"hash-{source_job_id}",
        match_score=80,
        status=status,
        location_category="confirmed_shanghai",
    )


def _list(db: Session, *, mark=None, status="active"):
    return list_jobs(
        db=db,
        limit=100,
        min_score=0,
        source=None,
        q=None,
        offset=0,
        location_category=None,
        min_llm_score=None,
        llm_verdict=None,
        status=status,
        mark=mark,
    )


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_new_jobs_start_unmarked_and_unviewed(db):
    job = _make_job("j1")
    db.add(job)
    db.commit()

    assert job.view_count == 0
    assert job.favorited_at is None
    assert job.applied_at is None
    assert job.last_viewed_at is None


def test_marks_set_keep_first_timestamp_and_clear(db):
    job = _make_job("j1")
    db.add(job)
    db.commit()

    first = update_job_marks(job.id, JobMarksUpdate(favorited=True), db=db)
    favorited_at = first.favorited_at
    assert favorited_at is not None
    assert first.applied_at is None

    again = update_job_marks(job.id, JobMarksUpdate(favorited=True, applied=True), db=db)
    assert again.favorited_at == favorited_at
    assert again.applied_at is not None

    cleared = update_job_marks(job.id, JobMarksUpdate(favorited=False), db=db)
    assert cleared.favorited_at is None
    assert cleared.applied_at is not None


def test_record_view_counts_clicks(db):
    job = _make_job("j1")
    db.add(job)
    db.commit()

    record_job_view(job.id, db=db)
    viewed = record_job_view(job.id, db=db)

    assert viewed.view_count == 2
    assert viewed.last_viewed_at is not None


def test_marks_and_view_return_404_for_unknown_job(db):
    with pytest.raises(HTTPException) as marks_error:
        update_job_marks(999, JobMarksUpdate(applied=True), db=db)
    with pytest.raises(HTTPException) as view_error:
        record_job_view(999, db=db)

    assert marks_error.value.status_code == 404
    assert view_error.value.status_code == 404


def test_mark_filter_selects_jobs_and_can_include_closed_ones(db):
    favorite = _make_job("fav")
    applied_closed = _make_job("applied-closed", status="closed")
    viewed = _make_job("viewed")
    untouched = _make_job("untouched")
    db.add_all([favorite, applied_closed, viewed, untouched])
    db.commit()
    update_job_marks(favorite.id, JobMarksUpdate(favorited=True), db=db)
    update_job_marks(applied_closed.id, JobMarksUpdate(applied=True), db=db)
    record_job_view(viewed.id, db=db)

    def ids(jobs):
        return {job.source_job_id for job in jobs}

    assert ids(_list(db, mark="favorited")) == {"fav"}
    assert ids(_list(db, mark="applied")) == set()
    assert ids(_list(db, mark="applied", status=None)) == {"applied-closed"}
    assert ids(_list(db, mark="not_applied")) == {"fav", "viewed", "untouched"}
    assert ids(_list(db, mark="viewed")) == {"viewed"}
    assert ids(_list(db, mark="not_viewed")) == {"fav", "untouched"}
    assert jobs_count(
        db=db,
        min_score=0,
        source=None,
        q=None,
        location_category=None,
        min_llm_score=None,
        llm_verdict=None,
        status=None,
        mark="applied",
    ) == {"total": 1}


def test_unknown_mark_filter_is_rejected(db):
    with pytest.raises(HTTPException) as error:
        _list(db, mark="starred")

    assert error.value.status_code == 422
