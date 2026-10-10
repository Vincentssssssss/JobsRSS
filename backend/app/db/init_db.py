from sqlalchemy import text

from app.db.session import Base, engine
from app.models import Job  # noqa: F401


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
