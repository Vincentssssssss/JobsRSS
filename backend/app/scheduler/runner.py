import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.collectors.base import BaseCollector
from app.collectors.job51_auth import Job51AuthCollector
from app.collectors.liepin_auth import LiepinAuthCollector
from app.collectors.linkedin_auth import LinkedInAuthCollector
from app.collectors.linkedin_email import LinkedInEmailCollector
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.notifications.daily_digest import send_daily_digest
from app.official.collectors import (
    AmazonOfficialCollector,
    GoogleOfficialCollector,
    MicrosoftOfficialCollector,
)
from app.pipeline import ingest_collector

logger = logging.getLogger(__name__)


def _run_collector(collector: BaseCollector) -> None:
    start = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        stats = ingest_collector(db, collector)
        end = datetime.now(timezone.utc)
        logger.info(
            "collector_run source=%s start=%s end=%s found=%d new=%d duplicates=%d errors=%d",
            collector.meta.source_name,
            start.isoformat(),
            end.isoformat(),
            stats.found,
            stats.new,
            stats.duplicates,
            stats.errors,
        )
    except Exception:
        logger.exception("collector_run_failed source=%s", collector.meta.source_name)
    finally:
        db.close()


def run_linkedin_email_collector() -> None:
    settings = get_settings()
    if not settings.linkedin_email_enabled:
        logger.info("collector_skipped source=linkedin_email reason=disabled")
        return
    _run_collector(LinkedInEmailCollector())


def run_linkedin_auth_collector() -> None:
    settings = get_settings()
    if not settings.linkedin_auth_enabled:
        logger.info("collector_skipped source=linkedin_auth reason=disabled")
        return
    _run_collector(LinkedInAuthCollector())


def run_job51_auth_collector() -> None:
    settings = get_settings()
    if not settings.job51_auth_enabled:
        logger.info("collector_skipped source=job51_auth reason=disabled")
        return
    _run_collector(Job51AuthCollector())


def run_liepin_auth_collector() -> None:
    settings = get_settings()
    if not settings.liepin_auth_enabled:
        logger.info("collector_skipped source=liepin_auth reason=disabled")
        return
    _run_collector(LiepinAuthCollector())


def _run_official_collector(collector: BaseCollector) -> None:
    settings = get_settings()
    if not settings.official_sources_enabled:
        logger.info(
            "collector_skipped source=%s reason=official_sources_disabled",
            collector.meta.source_name,
        )
        return
    _run_collector(collector)


def run_amazon_official_collector() -> None:
    _run_official_collector(AmazonOfficialCollector())


def run_google_official_collector() -> None:
    _run_official_collector(GoogleOfficialCollector())


def run_microsoft_official_collector() -> None:
    _run_official_collector(MicrosoftOfficialCollector())


def run_daily_digest_job() -> None:
    settings = get_settings()
    if not settings.digest_email_enabled:
        logger.info("digest_skipped reason=disabled")
        return
    db = SessionLocal()
    try:
        sent = send_daily_digest(db)
        logger.info("digest_run sent=%s", sent)
    except Exception:
        logger.exception("digest_run_failed")
    finally:
        db.close()


def start_scheduler() -> None:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_linkedin_email_collector,
        trigger="interval",
        minutes=settings.scheduler_linkedin_email_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_linkedin_auth_collector,
        trigger="interval",
        minutes=settings.linkedin_polling_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_job51_auth_collector,
        trigger="interval",
        minutes=settings.job51_polling_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_liepin_auth_collector,
        trigger="interval",
        minutes=settings.liepin_polling_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_daily_digest_job,
        trigger="cron",
        hour=settings.scheduler_digest_hour_utc,
        minute=settings.scheduler_digest_minute_utc,
        max_instances=1,
        coalesce=True,
    )
    for job_function in (
        run_amazon_official_collector,
        run_google_official_collector,
        run_microsoft_official_collector,
    ):
        scheduler.add_job(
            job_function,
            trigger="interval",
            minutes=settings.official_source_interval_minutes,
            max_instances=1,
            coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )
    run_linkedin_email_collector()
    run_linkedin_auth_collector()
    run_job51_auth_collector()
    run_liepin_auth_collector()
    scheduler.start()
