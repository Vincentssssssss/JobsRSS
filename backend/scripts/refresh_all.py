#!/usr/bin/env python3
"""Run a full refresh: re-collect every enabled source, then re-score jobs.

The scheduler only touches `llm_max_jobs_per_run` jobs per interval and, when
`LLM_ONLY_UNSCORED=false`, keeps re-scoring the same newest page forever. This
script instead walks the whole backlog in repeated passes so a complete
re-evaluation finishes in one command.
"""
import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.matching.llm_reranker import create_llm_client, run_llm_rerank
from app.models.job import Job
from app.official.collectors.catalog import OFFICIAL_COLLECTOR_FACTORIES
from app.scheduler.runner import (
    run_job51_auth_collector,
    run_liepin_auth_collector,
    run_linkedin_auth_collector,
    run_linkedin_email_collector,
    run_registered_official_collector,
)

logger = logging.getLogger("refresh_all")

EARLY_CAREER_GUARD_MODEL = "heuristic-early-career-guard"
CLEARED_LLM_FIELDS = {
    "llm_fit_score": None,
    "llm_verdict": None,
    "llm_role_family": None,
    "llm_match_reasons": None,
    "llm_reject_reasons": None,
    "llm_missing_skills": None,
    "llm_model": None,
    "llm_last_evaluated_at": None,
}


@dataclass
class RescoreTotals:
    passes: int = 0
    scanned: int = 0
    updated: int = 0
    failed: int = 0


def collect_everything() -> None:
    settings = get_settings()
    run_linkedin_email_collector()
    run_linkedin_auth_collector()
    run_job51_auth_collector()
    run_liepin_auth_collector()
    if not settings.official_sources_enabled:
        logger.info("refresh_collect_skipped reason=official_sources_disabled")
        return
    for source_id in OFFICIAL_COLLECTOR_FACTORIES:
        run_registered_official_collector(source_id)


def reset_llm_scores(db: Session, *, active_only: bool, include_guard: bool) -> int:
    query = db.query(Job).filter(
        or_(Job.llm_fit_score.is_not(None), Job.llm_verdict.is_not(None))
    )
    if active_only:
        query = query.filter(Job.status == "active")
    if not include_guard:
        # Heuristic rejections are deterministic and cost no tokens, so keep
        # them unless the caller explicitly wants the LLM to revisit them.
        query = query.filter(
            or_(
                Job.llm_model.is_(None),
                Job.llm_model != EARLY_CAREER_GUARD_MODEL,
            )
        )
    cleared = query.update(CLEARED_LLM_FIELDS, synchronize_session=False)
    db.commit()
    return cleared


def count_unscored(db: Session, settings: Settings) -> int:
    return (
        db.query(Job)
        .filter(
            Job.status == "active",
            Job.match_score >= settings.llm_min_rule_score,
            Job.llm_fit_score.is_(None),
        )
        .count()
    )


def rescore_everything(settings: Settings, *, max_passes: int) -> RescoreTotals:
    totals = RescoreTotals()
    for _ in range(max_passes):
        db = SessionLocal()
        try:
            stats = run_llm_rerank(db, settings=settings)
            remaining = count_unscored(db, settings)
        finally:
            db.close()
        totals.passes += 1
        totals.scanned += stats.scanned
        totals.updated += stats.updated
        totals.failed += stats.failed
        logger.info(
            "refresh_rescore_pass pass=%d scanned=%d updated=%d failed=%d remaining=%d",
            totals.passes,
            stats.scanned,
            stats.updated,
            stats.failed,
            remaining,
        )
        if stats.updated == 0:
            break
    else:
        logger.warning(
            "refresh_rescore_pass_limit_reached passes=%d; rerun to continue",
            max_passes,
        )
    return totals


def build_rescore_settings(batch_size: int | None) -> Settings:
    settings = get_settings()
    overrides: dict[str, object] = {"llm_only_unscored": True}
    if batch_size is not None:
        overrides["llm_max_jobs_per_run"] = batch_size
    return settings.model_copy(update=overrides)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-collect", action="store_true", help="Do not re-run collectors.")
    parser.add_argument("--skip-rescore", action="store_true", help="Do not run the LLM rerank.")
    parser.add_argument(
        "--reset-scores",
        action="store_true",
        help="Clear existing LLM verdicts so historical jobs are evaluated again.",
    )
    parser.add_argument(
        "--reset-all-statuses",
        action="store_true",
        help="Reset closed jobs too instead of only active ones.",
    )
    parser.add_argument(
        "--reset-early-career-guard",
        action="store_true",
        help="Also clear heuristic early-career rejections (costs extra tokens).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Jobs per rerank pass; defaults to LLM_MAX_JOBS_PER_RUN.",
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=200,
        help="Safety cap on rerank passes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args(argv)

    if args.reset_scores:
        db = SessionLocal()
        try:
            cleared = reset_llm_scores(
                db,
                active_only=not args.reset_all_statuses,
                include_guard=args.reset_early_career_guard,
            )
        finally:
            db.close()
        logger.info("refresh_scores_reset cleared=%d", cleared)

    if args.skip_collect:
        logger.info("refresh_collect_skipped reason=flag")
    else:
        collect_everything()

    if args.skip_rescore:
        logger.info("refresh_rescore_skipped reason=flag")
        return 0

    settings = build_rescore_settings(args.batch_size)
    if create_llm_client(settings) is None:
        logger.error(
            "refresh_rescore_unavailable reason=no_llm_client "
            "enabled=%s has_api_key=%s",
            settings.llm_rerank_enabled,
            bool(settings.llm_api_key),
        )
        return 1

    totals = rescore_everything(settings, max_passes=args.max_passes)
    logger.info(
        "refresh_rescore_done passes=%d scanned=%d updated=%d failed=%d model=%s",
        totals.passes,
        totals.scanned,
        totals.updated,
        totals.failed,
        settings.llm_model,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
