from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.core.config import get_settings
from app.dedup.service import is_probable_duplicate
from app.matching.scorer import score_job
from app.models.job import Job
from app.normalization.normalizer import normalize_job


@dataclass
class IngestStats:
    found: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0


def ingest_collector(db: Session, collector: BaseCollector) -> IngestStats:
    stats = IngestStats()
    jobs = collector.collect()
    stats.found = len(jobs)

    for incoming in jobs:
        try:
            incoming = normalize_job(incoming)
            incoming.match_score = score_job(incoming.title, incoming.description, incoming.location)

            existing = (
                db.query(Job)
                .filter(Job.source == incoming.source, Job.source_job_id == incoming.source_job_id)
                .first()
            )
            if existing:
                previous_hash = existing.content_hash
                existing.last_seen_at = incoming.last_seen_at
                existing_is_authoritative = bool(existing.enrichment_source)
                incoming_is_authoritative = bool(incoming.enrichment_source)
                allow_text_replacement = not existing_is_authoritative or incoming_is_authoritative
                if incoming.title and allow_text_replacement:
                    existing.title = incoming.title
                if allow_text_replacement and _should_replace_company(existing.company, incoming.company):
                    existing.company = incoming.company
                if allow_text_replacement and _should_replace_location(existing.location, incoming.location):
                    existing.location = incoming.location
                if allow_text_replacement and incoming.country and incoming.country != "Unknown":
                    existing.country = incoming.country
                if (
                    allow_text_replacement
                    and _description_quality(incoming.description) >= _description_quality(existing.description)
                ):
                    existing.description = incoming.description
                if (
                    (not existing_is_authoritative or incoming_is_authoritative)
                    and _should_replace_apply_url(existing.apply_url, incoming.apply_url)
                ):
                    existing.apply_url = incoming.apply_url
                if incoming.source_url:
                    existing.source_url = incoming.source_url
                if incoming.posted_at is not None:
                    existing.posted_at = incoming.posted_at
                existing.updated_at = incoming.updated_at
                existing.status = incoming.status
                existing.location_category = incoming.location_category
                if incoming.enrichment_source:
                    existing.enrichment_source = incoming.enrichment_source
                existing.match_score = score_job(existing.title, existing.description, existing.location)
                existing.content_hash = _job_hash(existing)
                if existing.content_hash != previous_hash:
                    existing.llm_fit_score = None
                    existing.llm_verdict = None
                    existing.llm_role_family = None
                    existing.llm_match_reasons = None
                    existing.llm_reject_reasons = None
                    existing.llm_missing_skills = None
                    existing.llm_model = None
                    existing.llm_last_evaluated_at = None
                stats.duplicates += 1
                continue

            probable = (
                db.query(Job)
                .filter(
                    Job.company == incoming.company,
                    Job.location == incoming.location,
                    Job.status == "active",
                )
                .all()
            )
            if any(is_probable_duplicate(item, incoming) for item in probable):
                stats.duplicates += 1
                continue

            db.add(
                Job(
                    source=incoming.source,
                    source_job_id=incoming.source_job_id,
                    company=incoming.company,
                    title=incoming.title,
                    location=incoming.location,
                    country=incoming.country,
                    description=incoming.description,
                    apply_url=incoming.apply_url,
                    source_url=incoming.source_url,
                    posted_at=incoming.posted_at,
                    updated_at=incoming.updated_at,
                    first_seen_at=incoming.first_seen_at,
                    last_seen_at=incoming.last_seen_at,
                    content_hash=incoming.content_hash,
                    match_score=incoming.match_score,
                    status=incoming.status,
                    enrichment_source=incoming.enrichment_source,
                    location_category=incoming.location_category,
                )
            )
            stats.new += 1
        except Exception:
            stats.errors += 1

    if collector.meta.source_name.startswith("official_"):
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=get_settings().official_source_stale_after_days
        )
        (
            db.query(Job)
            .filter(
                Job.source == collector.meta.source_name,
                Job.status == "active",
                Job.last_seen_at < cutoff,
            )
            .update({"status": "closed"}, synchronize_session=False)
        )
    if collector.meta.source_name == "linkedin_auth":
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=get_settings().linkedin_auth_stale_after_days
        )
        (
            db.query(Job)
            .filter(
                Job.source == "linkedin_auth",
                Job.status == "active",
                Job.last_seen_at < cutoff,
            )
            .update({"status": "closed"}, synchronize_session=False)
        )
    db.commit()
    return stats


def _is_placeholder(value: str, placeholders: set[str]) -> bool:
    return not value or value.strip().lower() in placeholders


def _should_replace_company(existing: str, incoming: str) -> bool:
    if _is_placeholder(incoming, {"unknown company", "unknown"}):
        return False
    return bool(incoming) or _is_placeholder(existing, {"unknown company", "unknown"})


def _should_replace_location(existing: str, incoming: str) -> bool:
    if _is_placeholder(incoming, {"unknown"}):
        return False
    return bool(incoming) or _is_placeholder(existing, {"unknown"})


def _description_quality(value: str) -> int:
    if not value:
        return 0
    lowered = value.lower()
    quality = min(len(value), 2000)
    if " at unknown company in " in lowered or len(value) < 80:
        quality -= 500
    return quality


def _should_replace_apply_url(existing: str, incoming: str) -> bool:
    if not incoming:
        return False
    existing_host = (urlparse(existing).hostname or "").lower()
    incoming_host = (urlparse(incoming).hostname or "").lower()
    existing_is_linkedin = existing_host == "linkedin.com" or existing_host.endswith(".linkedin.com")
    incoming_is_linkedin = incoming_host == "linkedin.com" or incoming_host.endswith(".linkedin.com")
    if existing and not existing_is_linkedin and incoming_is_linkedin:
        return False
    return True


def _job_hash(job: Job) -> str:
    posted_at = job.posted_at.isoformat() if job.posted_at else ""
    values = [
        job.source_job_id,
        job.title,
        job.company,
        job.location,
        job.description,
        job.apply_url,
        posted_at,
    ]
    return sha256("||".join(values).encode("utf-8")).hexdigest()
