import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from app.collectors.microsoft import MicrosoftCollector
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.pipeline import ingest_collector

logger = logging.getLogger(__name__)


def run_microsoft_collector() -> None:
    start = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        stats = ingest_collector(db, MicrosoftCollector())
        end = datetime.now(timezone.utc)
        logger.info(
            "collector_run source=%s start=%s end=%s found=%d new=%d duplicates=%d errors=%d",
            "microsoft",
            start.isoformat(),
            end.isoformat(),
            stats.found,
            stats.new,
            stats.duplicates,
            stats.errors,
        )
    except Exception:
        logger.exception("collector_run_failed source=microsoft")
    finally:
        db.close()


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
    run_microsoft_collector()
    scheduler.start()
