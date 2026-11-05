from sqlalchemy import desc, func

from app.models.job import Job

JOB_SORTS = ("newest", "ai_score")


def job_date():
    """When a job was posted, or first collected if its source gives no date."""
    return func.coalesce(Job.posted_at, Job.first_seen_at)


def newest_first():
    # Postgres puts NULLs first in a descending sort; a row without either date goes last.
    return (desc(job_date()).nulls_last(), desc(Job.id))


def job_order(sort: str):
    if sort == "ai_score":
        # Unscored jobs follow every scored one, best rule score first.
        return (desc(Job.llm_fit_score).nulls_last(), desc(Job.match_score), *newest_first())
    return newest_first()
