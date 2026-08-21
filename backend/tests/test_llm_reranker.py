from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.matching.llm_reranker import (
    LLMMatchResult,
    resolve_base_url,
    run_llm_rerank,
)
from app.models.job import Job


class FakeLLMClient:
    model = "qwen-plus"

    def evaluate_job(self, job: Job, target_profile: str) -> LLMMatchResult:
        assert "cybersecurity" in target_profile.lower()
        return LLMMatchResult(
            fit_score=84,
            verdict="strong_fit",
            role_family="cloud_security",
            match_reasons=["Strong security ownership scope"],
            reject_reasons=[],
            missing_skills=["CNAPP"],
        )


def _make_job(*, source_job_id: str, match_score: float, llm_fit_score=None) -> Job:
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
        match_score=match_score,
        llm_fit_score=llm_fit_score,
        status="active",
        location_category="confirmed_shanghai",
    )


def test_resolve_base_url_for_supported_providers():
    assert resolve_base_url("openai", None) == "https://api.openai.com/v1"
    assert resolve_base_url("chatgpt", None) == "https://api.openai.com/v1"
    assert resolve_base_url("codex", None) == "https://api.openai.com/v1"
    assert (
        resolve_base_url("qwen", None)
        == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert resolve_base_url("openai", "https://proxy.example/v1") == "https://proxy.example/v1"


def test_run_llm_rerank_updates_job_fields():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=20,
        llm_only_unscored=True,
        llm_max_jobs_per_run=10,
        llm_target_profile="Cybersecurity architect and cloud security roles",
    )

    with Session(engine) as db:
        db.add(_make_job(source_job_id="1", match_score=70))
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=FakeLLMClient())
        stored = db.query(Job).filter(Job.source_job_id == "1").one()

        assert stats.scanned == 1
        assert stats.updated == 1
        assert stats.failed == 0
        assert stored.llm_fit_score == 84
        assert stored.llm_verdict == "strong_fit"
        assert stored.llm_role_family == "cloud_security"
        assert stored.llm_model == "qwen-plus"
        assert stored.llm_match_reasons == "Strong security ownership scope"
        assert stored.llm_missing_skills == "CNAPP"
        assert stored.llm_last_evaluated_at is not None


def test_run_llm_rerank_respects_score_and_unscored_filters():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=50,
        llm_only_unscored=True,
        llm_max_jobs_per_run=10,
        llm_target_profile="Cybersecurity architect and cloud security roles",
    )

    with Session(engine) as db:
        db.add(_make_job(source_job_id="low-rule-score", match_score=10))
        db.add(_make_job(source_job_id="already-scored", match_score=90, llm_fit_score=60))
        db.add(_make_job(source_job_id="eligible", match_score=90))
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=FakeLLMClient())
        eligible = db.query(Job).filter(Job.source_job_id == "eligible").one()
        already = db.query(Job).filter(Job.source_job_id == "already-scored").one()
        low = db.query(Job).filter(Job.source_job_id == "low-rule-score").one()

        assert stats.scanned == 1
        assert stats.updated == 1
        assert eligible.llm_fit_score == 84
        assert already.llm_fit_score == 60
        assert low.llm_fit_score is None
