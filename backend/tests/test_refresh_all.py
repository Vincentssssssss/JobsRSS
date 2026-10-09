from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.job import Job
from scripts.refresh_all import (
    EARLY_CAREER_GUARD_MODEL,
    count_unscored,
    reset_llm_scores,
)


def _make_job(
    *,
    source_job_id: str,
    llm_fit_score=None,
    llm_verdict=None,
    llm_model=None,
    status: str = "active",
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source="official_alibaba",
        source_job_id=source_job_id,
        company="Alibaba",
        title="Cloud Security Engineer",
        location="上海",
        country="China",
        description="Responsible for cloud security architecture and threat detection.",
        apply_url=f"https://example.com/{source_job_id}",
        source_url=f"https://example.com/{source_job_id}",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=f"hash-{source_job_id}",
        match_score=60,
        llm_fit_score=llm_fit_score,
        llm_verdict=llm_verdict,
        llm_model=llm_model,
        llm_last_evaluated_at=now if llm_fit_score is not None else None,
        status=status,
        location_category="confirmed_shanghai",
    )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_reset_llm_scores_clears_active_llm_verdicts_but_keeps_guard_rows():
    db = _session()
    db.add_all(
        [
            _make_job(source_job_id="a", llm_fit_score=88, llm_verdict="strong_fit", llm_model="gpt"),
            _make_job(
                source_job_id="b",
                llm_fit_score=0,
                llm_verdict="not_fit",
                llm_model=EARLY_CAREER_GUARD_MODEL,
            ),
            _make_job(source_job_id="c"),
        ]
    )
    db.commit()

    cleared = reset_llm_scores(db, active_only=True, include_guard=False)

    assert cleared == 1
    scored = db.query(Job).filter(Job.source_job_id == "a").one()
    assert scored.llm_fit_score is None
    assert scored.llm_verdict is None
    assert scored.llm_last_evaluated_at is None
    guarded = db.query(Job).filter(Job.source_job_id == "b").one()
    assert guarded.llm_model == EARLY_CAREER_GUARD_MODEL
    db.close()


def test_reset_llm_scores_can_include_guard_rows_and_closed_jobs():
    db = _session()
    db.add_all(
        [
            _make_job(
                source_job_id="a",
                llm_fit_score=0,
                llm_verdict="not_fit",
                llm_model=EARLY_CAREER_GUARD_MODEL,
            ),
            _make_job(
                source_job_id="b",
                llm_fit_score=71,
                llm_verdict="possible_fit",
                llm_model="gpt",
                status="closed",
            ),
        ]
    )
    db.commit()

    cleared = reset_llm_scores(db, active_only=False, include_guard=True)

    assert cleared == 2
    assert db.query(Job).filter(Job.llm_verdict.is_not(None)).count() == 0
    db.close()


def test_count_unscored_respects_rule_score_floor_and_status():
    db = _session()
    low_score = _make_job(source_job_id="low")
    low_score.match_score = 5
    closed = _make_job(source_job_id="closed", status="closed")
    scored = _make_job(source_job_id="scored", llm_fit_score=70, llm_verdict="possible_fit")
    orphaned = _make_job(source_job_id="orphaned", llm_fit_score=24)
    db.add_all([_make_job(source_job_id="open"), low_score, closed, scored, orphaned])
    db.commit()

    class _Settings:
        llm_min_rule_score = 20

    assert count_unscored(db, _Settings()) == 2
    db.close()
