from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import init_db as init_db_module
from app.models.job import Job


def _job(source: str, source_job_id: str, company: str) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source=source,
        source_job_id=source_job_id,
        company=company,
        title="Senior Manager - Cyber Defense & Resilience- Shanghai",
        location="上海",
        country="China",
        description="Lead cyber defense engagements.",
        apply_url=f"https://jobs.example/{source_job_id}",
        source_url=f"https://jobs.example/{source_job_id}",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash",
        status="active",
    )


def test_init_db_repairs_region_company_on_existing_deloitte_rows(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    monkeypatch.setattr(init_db_module, "engine", engine)
    init_db_module.init_db()

    with Session(engine) as db:
        db.add_all(
            [
                _job("official_deloitte", "dt-1", "中国大陆"),
                _job("official_deloitte", "dt-2", "中国香港"),
                _job("official_amazon_aws", "aws-1", "Amazon Web Services Singapore"),
            ]
        )
        db.commit()

    init_db_module.init_db()

    with Session(engine) as db:
        companies = {job.source_job_id: job.company for job in db.query(Job).all()}
    assert companies == {
        "dt-1": "Deloitte / 德勤",
        "dt-2": "Deloitte / 德勤",
        "aws-1": "Amazon Web Services Singapore",
    }
