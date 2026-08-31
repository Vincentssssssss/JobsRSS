import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import and_, desc, or_
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.matching.early_career_guard import detect_early_career_markers
from app.models.job import Job

logger = logging.getLogger(__name__)
_VERDICT_ALIAS_MAP = {
    "strong fit": "strong_fit",
    "strong-fit": "strong_fit",
    "strongfit": "strong_fit",
    "high fit": "strong_fit",
    "high-fit": "strong_fit",
    "possible fit": "possible_fit",
    "possible-fit": "possible_fit",
    "possiblefit": "possible_fit",
    "potential fit": "possible_fit",
    "maybe fit": "possible_fit",
    "not fit": "not_fit",
    "not-fit": "not_fit",
    "notfit": "not_fit",
    "unfit": "not_fit",
    "不匹配": "not_fit",
    "不适合": "not_fit",
    "可能匹配": "possible_fit",
    "较匹配": "possible_fit",
    "强匹配": "strong_fit",
}


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
        api_version: Optional[str],
        temperature: Optional[float],
        timeout_seconds: int,
        verify_tls: bool,
        azure_use_default_credential: bool = False,
        azure_scope: str = "https://ai.azure.com/.default",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.verify_tls = verify_tls
        self.azure_use_default_credential = azure_use_default_credential
        self.azure_scope = azure_scope
        self._azure_credential = _build_azure_default_credential(
            azure_use_default_credential
        )

    def evaluate_job(self, job: Job, target_profile: str) -> LLMMatchResult:
        messages = _build_messages(job, target_profile)
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        with httpx.Client(
            timeout=self.timeout_seconds,
            verify=self.verify_tls,
            follow_redirects=True,
            headers=self._build_request_headers(),
        ) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                params=(
                    {"api-version": self.api_version}
                    if self.api_version
                    else None
                ),
            )
            response.raise_for_status()
        return _parse_match_result(response.json())

    def _build_request_headers(self) -> Dict[str, str]:
        if self.azure_use_default_credential:
            token = _get_azure_bearer_token(self._azure_credential, self.azure_scope)
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        return _build_auth_headers(self.api_key, self.base_url)


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
    if not settings.llm_api_key and not settings.llm_azure_use_default_credential:
        return None
    base_url = resolve_base_url(settings.llm_provider, settings.llm_base_url)
    return OpenAICompatibleClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=base_url,
        api_version=settings.llm_api_version,
        temperature=settings.llm_temperature,
        timeout_seconds=settings.llm_timeout_seconds,
        verify_tls=settings.llm_verify_tls,
        azure_use_default_credential=settings.llm_azure_use_default_credential,
        azure_scope=settings.llm_azure_scope,
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

    stats.updated += _enforce_early_career_guard(db, settings)

    query = (
        db.query(Job)
        .filter(
            Job.status == "active",
            Job.match_score >= settings.llm_min_rule_score,
        )
        .order_by(desc(Job.posted_at), desc(Job.id))
    )
    if settings.llm_only_unscored:
        query = query.filter(
            or_(
                Job.llm_fit_score.is_(None),
                _early_career_candidates_filter(settings),
            )
        )
    jobs = query.limit(settings.llm_max_jobs_per_run).all()

    for job in jobs:
        stats.scanned += 1
        early_career_markers = (
            _early_career_markers(job)
            if getattr(settings, "llm_reject_early_career", True)
            else []
        )
        if early_career_markers:
            if (
                str(job.llm_verdict or "") == "not_fit"
                and str(job.llm_model or "") == "heuristic-early-career-guard"
            ):
                continue
            _apply_match(
                job,
                _build_early_career_reject_result(early_career_markers),
                "heuristic-early-career-guard",
            )
            stats.updated += 1
            continue
        try:
            result = client.evaluate_job(job, settings.llm_target_profile)
            _apply_match(job, result, client.model)
            stats.updated += 1
        except Exception as exc:
            stats.failed += 1
            logger.warning(
                "llm_rerank_item_failed job_id=%s source=%s error=%s",
                job.id,
                job.source,
                str(exc),
            )
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
    content = _extract_message_text(message)
    data = _safe_json_loads(content)
    fit_score = _coerce_fit_score(data.get("fit_score"))
    return LLMMatchResult(
        fit_score=fit_score,
        verdict=_normalize_verdict(str(data.get("verdict", "")), fit_score),
        role_family=str(data.get("role_family", "unknown")),
        match_reasons=_as_string_list(data.get("match_reasons")),
        reject_reasons=_as_string_list(data.get("reject_reasons")),
        missing_skills=_as_string_list(data.get("missing_skills")),
    )


def _extract_message_text(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, list):
        parts = []
        for item in message:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts)
    if isinstance(message, dict):
        text = message.get("text") or message.get("content")
        if isinstance(text, str):
            return text
    return str(message or "")


def _safe_json_loads(value: str) -> Dict[str, Any]:
    for candidate in _json_candidates(value):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _json_candidates(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return [raw]
    candidates = [raw]
    stripped_fence = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    if stripped_fence != raw:
        candidates.append(stripped_fence.strip())
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1].strip())
    return candidates


def _coerce_fit_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fallback_verdict_by_score(fit_score: float) -> str:
    if fit_score >= 75:
        return "strong_fit"
    if fit_score >= 45:
        return "possible_fit"
    return "not_fit"


def _normalize_verdict(value: str, fit_score: float = 0.0) -> str:
    normalized = value.strip().lower()
    if normalized in {"strong_fit", "possible_fit", "not_fit"}:
        return normalized
    alias = _VERDICT_ALIAS_MAP.get(normalized)
    if alias:
        return alias
    compact = re.sub(r"[\s\-]+", "_", normalized)
    if compact in {"strong_fit", "possible_fit", "not_fit"}:
        return compact
    if compact in {"strongfit", "possiblefit", "notfit"}:
        return {
            "strongfit": "strong_fit",
            "possiblefit": "possible_fit",
            "notfit": "not_fit",
        }[compact]
    return _fallback_verdict_by_score(fit_score)


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _early_career_markers(job: Job) -> list[str]:
    return detect_early_career_markers(
        [
            str(job.title or ""),
            str(job.description or ""),
            str(job.company or ""),
            str(job.apply_url or ""),
            str(job.source_url or ""),
        ]
    )


def _build_early_career_reject_result(markers: Iterable[str]) -> LLMMatchResult:
    marker_text = ", ".join(markers)
    return LLMMatchResult(
        fit_score=0.0,
        verdict="not_fit",
        role_family="early_career_program",
        match_reasons=[],
        reject_reasons=[
            "Hard rejected as early-career/campus role.",
            f"Detected markers: {marker_text}",
        ],
        missing_skills=[],
    )


def _early_career_candidates_filter(settings: Settings | Any):
    if not getattr(settings, "llm_reject_early_career", True):
        return Job.id.is_(None)
    return and_(
        Job.llm_fit_score.is_not(None),
        or_(Job.llm_verdict.is_(None), Job.llm_verdict != "not_fit"),
        or_(
            Job.title.ilike("%校招%"),
            Job.title.ilike("%应届%"),
            Job.title.ilike("%实习%"),
            Job.description.ilike("%校园招聘%"),
            Job.description.ilike("%Graduation Dates%"),
            Job.description.ilike("%Graduate Recruitment%"),
            Job.apply_url.ilike("%campus-talent.alibaba.com%"),
            Job.source_url.ilike("%campus-talent.alibaba.com%"),
        ),
    )


def _enforce_early_career_guard(db: Session, settings: Settings | Any) -> int:
    if not getattr(settings, "llm_reject_early_career", True):
        return 0
    candidates = (
        db.query(Job)
        .filter(
            Job.status == "active",
            or_(Job.llm_verdict.is_(None), Job.llm_verdict != "not_fit"),
            or_(
                Job.title.ilike("%校招%"),
                Job.title.ilike("%应届%"),
                Job.title.ilike("%实习%"),
                Job.title.ilike("%管培生%"),
                Job.description.ilike("%校园招聘%"),
                Job.description.ilike("%Graduation Dates%"),
                Job.description.ilike("%Graduate Recruitment%"),
                Job.apply_url.ilike("%campus-talent.alibaba.com%"),
                Job.source_url.ilike("%campus-talent.alibaba.com%"),
            ),
        )
        .all()
    )
    updated = 0
    for job in candidates:
        markers = _early_career_markers(job)
        if not markers:
            continue
        _apply_match(
            job,
            _build_early_career_reject_result(markers),
            "heuristic-early-career-guard",
        )
        updated += 1
    return updated


def _build_auth_headers(api_key: str, base_url: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if _is_azure_openai_base_url(base_url):
        headers["api-key"] = api_key
        return headers
    headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _is_azure_openai_base_url(base_url: str) -> bool:
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return False
    return host.endswith(".openai.azure.com") or host.endswith(
        ".services.ai.azure.com"
    )


def _build_azure_default_credential(enabled: bool) -> Optional[Any]:
    if not enabled:
        return None
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise RuntimeError(
            "LLM_AZURE_USE_DEFAULT_CREDENTIAL=true requires azure-identity package."
        ) from exc
    return DefaultAzureCredential()


def _get_azure_bearer_token(credential: Optional[Any], scope: str) -> str:
    if credential is None:
        raise RuntimeError("Azure default credential is not initialized.")
    token = credential.get_token(scope)
    return token.token
