import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import Base, engine
from app.models import Job  # noqa: F401
from app.official.collectors.catalog import official_fixed_companies
from app.pipeline import repair_fixed_company_names

logger = logging.getLogger(__name__)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS enrichment_source VARCHAR(64)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS location_category VARCHAR(32) "
                    "NOT NULL DEFAULT 'unclassified'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_fit_score DOUBLE PRECISION"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_verdict VARCHAR(32)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_role_family VARCHAR(128)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_match_reasons TEXT"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_reject_reasons TEXT"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_missing_skills TEXT"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_model VARCHAR(128)"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS llm_last_evaluated_at TIMESTAMPTZ"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ"
                )
            )
            for column in ("favorited_at", "applied_at", "last_viewed_at"):
                connection.execute(
                    text(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {column} TIMESTAMPTZ")
                )
            connection.execute(
                text(
                    "ALTER TABLE jobs "
                    "ADD COLUMN IF NOT EXISTS view_count INTEGER NOT NULL DEFAULT 0"
                )
            )
    _repair_company_names()


def _repair_company_names() -> None:
    with Session(engine) as db:
        repaired = repair_fixed_company_names(db, official_fixed_companies())
    if repaired:
        logger.info("company_names_repaired count=%d", repaired)
