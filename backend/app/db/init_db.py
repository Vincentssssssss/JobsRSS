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
