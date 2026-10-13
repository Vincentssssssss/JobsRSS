import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Set, Type

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app.collectors.base import BaseCollector
from app.collectors.job51_auth import Job51AuthCollector
from app.collectors.liepin_auth import LiepinAuthCollector
from app.collectors.linkedin_auth import LinkedInAuthCollector
from app.collectors.linkedin_email import LinkedInEmailCollector
from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.matching.llm_reranker import run_llm_rerank
from app.notifications.daily_digest import send_daily_digest
from app.official.collectors.catalog import (
    OFFICIAL_COLLECTOR_FACTORIES,
    create_official_collector,
)
from app.pipeline import close_rows_from_removed_sources, ingest_collector

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


def run_registered_official_collector(source_id: str) -> None:
    settings = get_settings()
    collector = create_official_collector(source_id)
    if not settings.official_sources_enabled:
        logger.info(
            "collector_skipped source=%s reason=official_sources_disabled",
            collector.meta.source_name,
        )
        return
    _run_collector(collector)


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


def run_llm_rerank_job() -> None:
    settings = get_settings()
    if not settings.llm_rerank_enabled:
        logger.info("llm_rerank_skipped reason=disabled")
        return
    db = SessionLocal()
    try:
        stats = run_llm_rerank(db, settings=settings)
        logger.info(
            "llm_rerank_run scanned=%d updated=%d failed=%d provider=%s model=%s",
            stats.scanned,
            stats.updated,
            stats.failed,
            settings.llm_provider,
            settings.llm_model,
        )
    except Exception:
        logger.exception("llm_rerank_failed")
    finally:
        db.close()


def current_source_names() -> Set[str]:
    platform_sources = {
        collector.meta.source_name
        for collector in (
            LinkedInEmailCollector,
            LinkedInAuthCollector,
            Job51AuthCollector,
            LiepinAuthCollector,
        )
    }
    return platform_sources | {
        f"official_{source_id}" for source_id in OFFICIAL_COLLECTOR_FACTORIES
    }


def close_rows_from_removed_sources_job() -> None:
    db = SessionLocal()
    try:
        closed = close_rows_from_removed_sources(db, current_source_names())
        logger.info("removed_source_rows_closed count=%d", closed)
    except Exception:
        logger.exception("removed_source_rows_close_failed")
    finally:
        db.close()


# A slow boot or a laptop waking from sleep starts jobs after their scheduled
# time. APScheduler's default 1-second grace would skip those runs and wait a
# full interval (6 hours for official sources); coalesce runs them once instead.
SCHEDULER_JOB_DEFAULTS = {"misfire_grace_time": None, "coalesce": True, "max_instances": 1}


def build_scheduler(scheduler_class: Type[BaseScheduler] = BlockingScheduler) -> BaseScheduler:
    settings = get_settings()
    scheduler = scheduler_class(timezone="UTC", job_defaults=SCHEDULER_JOB_DEFAULTS)
    now = datetime.now(timezone.utc)
    for job, minutes in (
        (run_linkedin_email_collector, settings.scheduler_linkedin_email_interval_minutes),
        (run_linkedin_auth_collector, settings.linkedin_polling_interval_minutes),
        (run_job51_auth_collector, settings.job51_polling_interval_minutes),
        (run_liepin_auth_collector, settings.liepin_polling_interval_minutes),
        (run_llm_rerank_job, settings.llm_rerank_interval_minutes),
    ):
        scheduler.add_job(job, trigger="interval", minutes=minutes, next_run_time=now)
    scheduler.add_job(
        run_daily_digest_job,
        trigger="cron",
        hour=settings.scheduler_digest_hour_utc,
        minute=settings.scheduler_digest_minute_utc,
    )
    for index, source_id in enumerate(OFFICIAL_COLLECTOR_FACTORIES):
        scheduler.add_job(
            run_registered_official_collector,
            trigger="interval",
            args=[source_id],
            id=f"official_{source_id}",
            minutes=settings.official_source_interval_minutes,
            next_run_time=now + timedelta(seconds=index * 30),
        )
    return scheduler


def init_db_with_retry(attempts: int = 10, delay_seconds: float = 3.0) -> None:
    for attempt in range(1, attempts + 1):
        try:
            init_db()
            return
        except Exception:
            if attempt >= attempts:
                raise
            logger.warning("init_db_retry attempt=%d/%d", attempt, attempts, exc_info=True)
            time.sleep(delay_seconds)


def start_scheduler() -> None:
    # The worker is usually recreated without the api, and every job selects
    # columns that only init_db adds, so it must apply schema changes itself.
    init_db_with_retry()
    close_rows_from_removed_sources_job()
    build_scheduler().start()
