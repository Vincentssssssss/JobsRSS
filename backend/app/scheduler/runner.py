import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.collectors.base import BaseCollector
from app.collectors.linkedin_email import LinkedInEmailCollector
from app.collectors.microsoft import MicrosoftCollector
from app.core.config import get_settings
from app.db.session import SessionLocal
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


def run_microsoft_collector() -> None:
    _run_collector(MicrosoftCollector())


def run_linkedin_email_collector() -> None:
    settings = get_settings()
    if not settings.linkedin_email_enabled:
        logger.info("collector_skipped source=linkedin_email reason=disabled")
        return
    _run_collector(LinkedInEmailCollector())


def start_scheduler() -> None:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_microsoft_collector,
        trigger="interval",
        minutes=settings.scheduler_company_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        run_linkedin_email_collector,
        trigger="interval",
        minutes=settings.scheduler_linkedin_email_interval_minutes,
        max_instances=1,
        coalesce=True,
    )
    run_microsoft_collector()
    run_linkedin_email_collector()
    scheduler.start()
