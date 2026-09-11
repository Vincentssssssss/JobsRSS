from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.matching.llm_reranker import (
    LLMMatchResult,
    _build_auth_headers,
    _is_retryable_status,
    _normalize_verdict,
    _parse_match_result,
    _retry_delay_seconds,
    _summarize_http_status_error,
    create_llm_client,
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


class FailIfCalledClient:
    model = "never-call"

    def evaluate_job(self, job: Job, target_profile: str) -> LLMMatchResult:
        raise AssertionError("LLM client should not be called for early-career jobs")


class AlwaysFailClient:
    model = "always-fail"

    def evaluate_job(self, job: Job, target_profile: str) -> LLMMatchResult:
        raise TimeoutError("simulated timeout")


def _make_job(
    *,
    source_job_id: str,
    match_score: float,
    llm_fit_score=None,
    description: str = "Responsible for cloud security architecture and threat detection.",
    title: str = "Cloud Security Engineer",
    source: str = "official_alibaba",
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source=source,
        source_job_id=source_job_id,
        company="Alibaba",
        title=title,
        location="上海",
        country="China",
        description=description,
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


def test_auth_header_uses_api_key_for_azure_base_url():
    headers = _build_auth_headers(
        "secret",
        "https://foundry0805.openai.azure.com/openai/v1",
    )
    assert headers["api-key"] == "secret"
    assert "Authorization" not in headers


def test_auth_header_uses_api_key_for_foundry_services_base_url():
    headers = _build_auth_headers(
        "secret",
        "https://foundry0805.services.ai.azure.com/openai/v1",
    )
    assert headers["api-key"] == "secret"
    assert "Authorization" not in headers


def test_auth_header_uses_bearer_for_openai_base_url():
    headers = _build_auth_headers("secret", "https://api.openai.com/v1")
    assert headers["Authorization"] == "Bearer secret"
    assert "api-key" not in headers


def test_retryable_status_and_backoff_helpers():
    assert _is_retryable_status(500)
    assert _is_retryable_status(429)
    assert not _is_retryable_status(400)
    assert _retry_delay_seconds(1.5, 0) == 1.5
    assert _retry_delay_seconds(1.5, 1) == 3.0
    assert _retry_delay_seconds(1.5, 2) == 6.0


def test_summarize_http_status_error_includes_request_id_and_error_fields():
    import httpx

    request = httpx.Request("POST", "https://example.com/chat/completions")
    response = httpx.Response(
        status_code=500,
        request=request,
        headers={"x-request-id": "req-123"},
        json={
            "error": {
                "message": "The server had an error while processing your request.",
                "type": "server_error",
                "code": None,
            }
        },
    )
    exc = httpx.HTTPStatusError("boom", request=request, response=response)

    text = _summarize_http_status_error(exc)

    assert "http_status=500" in text
    assert "request_id=req-123" in text
    assert "error_type=server_error" in text


def test_parse_match_result_tolerates_json_fence_and_space_verdict():
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "```json\n"
                        '{"fit_score": 78, "verdict": "possible fit", '
                        '"role_family": "cloud security", '
                        '"match_reasons": ["IAM"], "reject_reasons": [], '
                        '"missing_skills": ["CNAPP"]}\n'
                        "```"
                    )
                }
            }
        ]
    }

    parsed = _parse_match_result(payload)

    assert parsed.fit_score == 78
    assert parsed.verdict == "possible_fit"
    assert parsed.role_family == "cloud security"


def test_normalize_verdict_falls_back_to_score_when_label_unexpected():
    assert _normalize_verdict("totally-custom-label", 84) == "strong_fit"
    assert _normalize_verdict("totally-custom-label", 50) == "possible_fit"
    assert _normalize_verdict("totally-custom-label", 10) == "not_fit"


def test_create_llm_client_allows_default_credential_without_api_key(monkeypatch):
    monkeypatch.setattr(
        "app.matching.llm_reranker._build_azure_default_credential",
        lambda enabled: object() if enabled else None,
    )
    settings = SimpleNamespace(
        llm_rerank_enabled=True,
        llm_api_key=None,
        llm_provider="openai",
        llm_base_url="https://foundry0805.services.ai.azure.com/openai/v1",
        llm_model="gpt-5.6-luna",
        llm_api_version=None,
        llm_temperature=None,
        llm_timeout_seconds=30,
        llm_verify_tls=True,
        llm_azure_use_default_credential=True,
        llm_azure_scope="https://ai.azure.com/.default",
    )

    client = create_llm_client(settings)

    assert client is not None


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


def test_run_llm_rerank_hard_rejects_early_career_jobs_without_llm_call():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=0,
        llm_only_unscored=True,
        llm_max_jobs_per_run=10,
        llm_target_profile="Experienced cybersecurity architect roles only",
        llm_reject_early_career=True,
    )

    with Session(engine) as db:
        db.add(
            _make_job(
                source_job_id="campus-1",
                match_score=80,
                title="安全技术工程师",
                description=(
                    "Basic Information\n"
                    "Graduation Dates: 2026-11-01 - 2027-10-31\n"
                    "Hiring Program: Alibaba 2027 Graduate Recruitment"
                ),
                source="official_alibaba",
            )
        )
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=FailIfCalledClient())
        stored = db.query(Job).filter(Job.source_job_id == "campus-1").one()

        assert stats.scanned == 0
        assert stats.updated == 1
        assert stats.failed == 0
        assert stored.llm_fit_score == 0
        assert stored.llm_verdict == "not_fit"
        assert stored.llm_role_family == "early_career_program"


def test_run_llm_rerank_rechecks_scored_early_career_jobs_when_only_unscored_true():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=0,
        llm_only_unscored=True,
        llm_max_jobs_per_run=10,
        llm_target_profile="Experienced cybersecurity architect roles only",
        llm_reject_early_career=True,
    )

    with Session(engine) as db:
        db.add(
            _make_job(
                source_job_id="campus-2",
                match_score=80,
                llm_fit_score=82,
                title="安全技术工程师",
                description=(
                    "Basic Information\n"
                    "Graduation Dates: 2026-11-01 - 2027-10-31\n"
                    "Hiring Program: Alibaba 2027 Graduate Recruitment"
                ),
                source="official_alibaba",
            )
        )
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=FailIfCalledClient())
        stored = db.query(Job).filter(Job.source_job_id == "campus-2").one()

        assert stats.scanned == 0
        assert stats.updated == 1
        assert stats.failed == 0
        assert stored.llm_fit_score == 0
        assert stored.llm_verdict == "not_fit"


def test_run_llm_rerank_enforces_early_career_guard_before_network_failures():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=0,
        llm_only_unscored=False,
        llm_max_jobs_per_run=10,
        llm_target_profile="Experienced cybersecurity architect roles only",
        llm_reject_early_career=True,
    )

    with Session(engine) as db:
        db.add(
            _make_job(
                source_job_id="campus-3",
                match_score=80,
                llm_fit_score=82,
                description=(
                    "Basic Information\n"
                    "Graduation Dates: 2026-11-01 - 2027-10-31\n"
                    "Hiring Program: Alibaba 2027 Graduate Recruitment"
                ),
                source="official_alibaba",
            )
        )
        db.add(
            _make_job(
                source_job_id="normal-1",
                match_score=80,
                llm_fit_score=None,
                title="Senior Cloud Security Architect",
                description="Experienced role focused on cloud security and IAM.",
                source="linkedin_auth",
            )
        )
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=AlwaysFailClient())
        campus = db.query(Job).filter(Job.source_job_id == "campus-3").one()
        normal = db.query(Job).filter(Job.source_job_id == "normal-1").one()

        assert stats.updated == 1
        assert stats.failed == 1
        assert campus.llm_fit_score == 0
        assert campus.llm_verdict == "not_fit"
        assert campus.llm_model == "heuristic-early-career-guard"
        assert normal.llm_fit_score is None


def test_run_llm_rerank_aborts_after_consecutive_failures_threshold():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = SimpleNamespace(
        llm_min_rule_score=0,
        llm_only_unscored=False,
        llm_max_jobs_per_run=10,
        llm_target_profile="Experienced cybersecurity architect roles only",
        llm_reject_early_career=False,
        llm_abort_after_consecutive_failures=2,
    )

    with Session(engine) as db:
        db.add(_make_job(source_job_id="n1", match_score=80, source="linkedin_auth"))
        db.add(_make_job(source_job_id="n2", match_score=80, source="linkedin_auth"))
        db.add(_make_job(source_job_id="n3", match_score=80, source="linkedin_auth"))
        db.commit()

        stats = run_llm_rerank(db, settings=settings, client=AlwaysFailClient())

        assert stats.failed == 2
        assert stats.scanned == 2
