import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol

import httpx
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.job import Job


class LLMClient(Protocol):
    model: str

    def evaluate_job(self, job: Job, target_profile: str) -> "LLMMatchResult":
        ...


@dataclass
class LLMMatchResult:
    fit_score: float
    verdict: str
    role_family: str
    match_reasons: list[str]
    reject_reasons: list[str]
    missing_skills: list[str]


@dataclass
class LLMRerankStats:
    scanned: int = 0
    updated: int = 0
    failed: int = 0


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        verify_tls: bool,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls

    def evaluate_job(self, job: Job, target_profile: str) -> LLMMatchResult:
        messages = _build_messages(job, target_profile)
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(
            timeout=self.timeout_seconds,
            verify=self.verify_tls,
            follow_redirects=True,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()
        return _parse_match_result(response.json())


def resolve_base_url(provider: str, configured_base_url: Optional[str]) -> str:
    if configured_base_url:
        return configured_base_url
    normalized = provider.lower().strip()
    if normalized in {"openai", "chatgpt", "codex"}:
        return "https://api.openai.com/v1"
    if normalized == "qwen":
        return "https://dashscope.aliyuncs.com/compatible-mode/v1"
    raise ValueError(f"Unsupported llm provider: {provider}")


def create_llm_client(settings: Optional[Settings] = None) -> Optional[LLMClient]:
    settings = settings or get_settings()
    if not settings.llm_rerank_enabled:
        return None
    if not settings.llm_api_key:
        return None
    base_url = resolve_base_url(settings.llm_provider, settings.llm_base_url)
    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=base_url,
        timeout_seconds=settings.llm_timeout_seconds,
        verify_tls=settings.llm_verify_tls,
    )


def run_llm_rerank(
    db: Session,
    *,
    settings: Optional[Settings] = None,
    client: Optional[LLMClient] = None,
) -> LLMRerankStats:
    settings = settings or get_settings()
    stats = LLMRerankStats()
    client = client or create_llm_client(settings)
    if client is None:
        return stats

    query = (
        db.query(Job)
        .filter(
            Job.status == "active",
            Job.match_score >= settings.llm_min_rule_score,
        )
        .order_by(desc(Job.posted_at), desc(Job.id))
    )
    if settings.llm_only_unscored:
        query = query.filter(Job.llm_fit_score.is_(None))
    jobs = query.limit(settings.llm_max_jobs_per_run).all()

    for job in jobs:
        stats.scanned += 1
        try:
            result = client.evaluate_job(job, settings.llm_target_profile)
            _apply_match(job, result, client.model)
            stats.updated += 1
        except Exception:
            stats.failed += 1
    db.commit()
    return stats


def _apply_match(job: Job, result: LLMMatchResult, model: str) -> None:
    job.llm_fit_score = max(0.0, min(100.0, float(result.fit_score)))
    job.llm_verdict = result.verdict[:32]
    job.llm_role_family = result.role_family[:128]
    job.llm_match_reasons = _join_lines(result.match_reasons)
    job.llm_reject_reasons = _join_lines(result.reject_reasons)
    job.llm_missing_skills = _join_lines(result.missing_skills)
    job.llm_model = model[:128]
    job.llm_last_evaluated_at = datetime.now(timezone.utc)


def _join_lines(items: Iterable[str]) -> str:
    cleaned = [item.strip() for item in items if item and item.strip()]
    return "\n".join(cleaned)


def _build_messages(job: Job, target_profile: str) -> list[Dict[str, str]]:
    prompt = {
        "target_profile": target_profile,
        "job": {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description[:6000],
        },
        "task": (
            "Evaluate cybersecurity fit. Output JSON with keys: "
            "fit_score (0-100 number), verdict (strong_fit|possible_fit|not_fit), "
            "role_family (string), match_reasons (array of strings), "
            "reject_reasons (array of strings), missing_skills (array of strings)."
        ),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are a strict technical recruiter for cybersecurity roles. "
                "Do not infer unrelated fit from generic cloud or AI keywords."
            ),
        },
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]


def _parse_match_result(payload: Dict[str, Any]) -> LLMMatchResult:
    choices = payload.get("choices") or []
    message = ((choices[0] if choices else {}).get("message") or {}).get("content", "")
    data = _safe_json_loads(str(message))
    return LLMMatchResult(
        fit_score=float(data.get("fit_score", 0)),
        verdict=_normalize_verdict(str(data.get("verdict", "not_fit"))),
        role_family=str(data.get("role_family", "unknown")),
        match_reasons=_as_string_list(data.get("match_reasons")),
        reject_reasons=_as_string_list(data.get("reject_reasons")),
        missing_skills=_as_string_list(data.get("missing_skills")),
    )


def _safe_json_loads(value: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_verdict(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"strong_fit", "possible_fit", "not_fit"}:
        return normalized
    return "not_fit"
