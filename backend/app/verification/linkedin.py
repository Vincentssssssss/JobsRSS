import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Optional

import httpx
from sqlalchemy import and_, case, or_
from sqlalchemy.orm import Session

from app.collectors.linkedin_status import (
    PostingState,
    classify_guest_job_response,
    linkedin_job_id,
)
from app.core.config import Settings, get_settings
from app.models.job import Job

logger = logging.getLogger(__name__)

LINKEDIN_SOURCES = ("linkedin_auth", "linkedin_email")
GUEST_JOB_POSTING_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
DASHBOARD_VERDICTS = ("strong_fit", "possible_fit")
DASHBOARD_MIN_LLM_SCORE = 60
# A 404 for a posting the collector saw this recently is more likely an
# endpoint change than a removal, so it must not close the row.
RECENT_SIGHTING = timedelta(hours=24)
MAX_CONSECUTIVE_REQUEST_ERRORS = 3
_GUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class LinkedInVerificationStats:
    checked: int = 0
    open: int = 0
    closed: int = 0
    inconclusive: int = 0
    skipped: int = 0
    errors: int = 0
    throttled: bool = False


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def select_verification_candidates(db: Session, settings: Settings, now: datetime) -> List[Job]:
    recheck_cutoff = now - timedelta(hours=settings.linkedin_verify_recheck_hours)
    on_dashboard = and_(
        Job.llm_verdict.in_(DASHBOARD_VERDICTS),
        Job.llm_fit_score >= DASHBOARD_MIN_LLM_SCORE,
    )
    return (
        db.query(Job)
        .filter(
            Job.source.in_(LINKEDIN_SOURCES),
            Job.status == "active",
            or_(Job.last_verified_at.is_(None), Job.last_verified_at < recheck_cutoff),
        )
        .order_by(
            case((on_dashboard, 0), else_=1),
            case((Job.last_verified_at.is_(None), 0), else_=1),
            Job.last_verified_at.asc(),
            Job.last_seen_at.asc(),
            Job.id.asc(),
        )
        .limit(max(0, settings.linkedin_verify_max_per_run))
        .all()
    )


def build_guest_client(settings: Settings) -> httpx.Client:
    # Deliberately anonymous: never load the LinkedIn storage state or any
    # account cookie here, so these checks cannot be tied to the user's account.
    return httpx.Client(
        headers=_GUEST_HEADERS,
        timeout=settings.collector_default_timeout_seconds,
        follow_redirects=False,
    )


def verify_linkedin_postings(
    db: Session,
    *,
    settings: Optional[Settings] = None,
    client: Optional[httpx.Client] = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Optional[datetime] = None,
) -> LinkedInVerificationStats:
    """Re-check a bounded batch of active LinkedIn rows against the public job
    page and close the ones LinkedIn reports as closed or removed."""
    settings = settings or get_settings()
    stats = LinkedInVerificationStats()
    if not settings.linkedin_verify_enabled:
        return stats
    now = now or datetime.now(timezone.utc)
    candidates = select_verification_candidates(db, settings, now)
    if not candidates:
        return stats

    owns_client = client is None
    client = client or build_guest_client(settings)
    requests_sent = 0
    consecutive_errors = 0
    try:
        for job in candidates:
            job_id = linkedin_job_id(job.source_url, job.source_job_id, job.apply_url)
            if job_id is None:
                job.last_verified_at = now
                db.commit()
                stats.skipped += 1
                continue
            if requests_sent and settings.linkedin_verify_delay_seconds > 0:
                sleep(settings.linkedin_verify_delay_seconds * random.uniform(1.0, 1.5))
            requests_sent += 1
            try:
                response = client.get(GUEST_JOB_POSTING_URL.format(job_id=job_id))
            except httpx.HTTPError as exc:
                stats.errors += 1
                consecutive_errors += 1
                logger.warning(
                    "linkedin_verify_request_failed job_id=%s error=%s",
                    job_id,
                    type(exc).__name__,
                )
                if consecutive_errors >= MAX_CONSECUTIVE_REQUEST_ERRORS:
                    break
                continue
            consecutive_errors = 0

            last_seen = _as_utc(job.last_seen_at)
            check = classify_guest_job_response(
                response.status_code,
                response.text,
                trust_not_found=last_seen is None or now - last_seen >= RECENT_SIGHTING,
            )
            if check.state is PostingState.THROTTLED:
                stats.throttled = True
                logger.warning(
                    "linkedin_verify_throttled job_id=%s reason=%s", job_id, check.reason
                )
                break

            stats.checked += 1
            job.last_verified_at = now
            if check.state is PostingState.CLOSED:
                job.status = "closed"
                stats.closed += 1
                logger.info(
                    "linkedin_verify_closed id=%s source=%s job_id=%s reason=%s",
                    job.id,
                    job.source,
                    job_id,
                    check.reason,
                )
            elif check.state is PostingState.OPEN:
                stats.open += 1
            else:
                stats.inconclusive += 1
                logger.info(
                    "linkedin_verify_inconclusive id=%s job_id=%s reason=%s",
                    job.id,
                    job_id,
                    check.reason,
                )
            db.commit()
    finally:
        if owns_client:
            client.close()
    return stats
