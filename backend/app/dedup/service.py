from app.models.job import Job
from app.schemas.job import UnifiedJob


def normalized_title(value: str) -> str:
    return " ".join(value.lower().split())


def is_probable_duplicate(existing: Job, incoming: UnifiedJob) -> bool:
    return (
        existing.company.lower() == incoming.company.lower()
        and normalized_title(existing.title) == normalized_title(incoming.title)
        and existing.location.lower() == incoming.location.lower()
    )
