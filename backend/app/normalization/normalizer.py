import re

from app.schemas.job import UnifiedJob


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_job(job: UnifiedJob) -> UnifiedJob:
    job.title = normalize_text(job.title)
    job.company = normalize_text(job.company)
    job.location = normalize_text(job.location)
    job.description = normalize_text(job.description)
    return job
