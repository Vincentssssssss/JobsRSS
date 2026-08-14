from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.dedup.service import is_probable_duplicate
from app.matching.scorer import score_job
from app.models.job import Job
from app.normalization.normalizer import normalize_job


@dataclass
class IngestStats:
    found: int = 0
    new: int = 0
    duplicates: int = 0
    errors: int = 0


def ingest_collector(db: Session, collector: BaseCollector) -> IngestStats:
    stats = IngestStats()
    jobs = collector.collect()
    stats.found = len(jobs)

    for incoming in jobs:
        try:
            incoming = normalize_job(incoming)
            incoming.match_score = score_job(incoming.title, incoming.description, incoming.location)

            existing = (
                db.query(Job)
                .filter(Job.source == incoming.source, Job.source_job_id == incoming.source_job_id)
                .first()
            )
            if existing:
                if existing.content_hash != incoming.content_hash:
                    existing.title = incoming.title
                    existing.location = incoming.location
                    existing.description = incoming.description
                    existing.apply_url = incoming.apply_url
                    existing.source_url = incoming.source_url
                    existing.updated_at = incoming.updated_at
                    existing.content_hash = incoming.content_hash
                    existing.match_score = incoming.match_score
                stats.duplicates += 1
                continue

            probable = db.query(Job).filter(Job.company == incoming.company, Job.location == incoming.location).all()
            if any(is_probable_duplicate(item, incoming) for item in probable):
                stats.duplicates += 1
                continue

            db.add(
                Job(
                    source=incoming.source,
                    source_job_id=incoming.source_job_id,
                    company=incoming.company,
                    title=incoming.title,
                    location=incoming.location,
                    country=incoming.country,
                    description=incoming.description,
                    apply_url=incoming.apply_url,
                    source_url=incoming.source_url,
                    posted_at=incoming.posted_at,
                    updated_at=incoming.updated_at,
                    first_seen_at=incoming.first_seen_at,
                    last_seen_at=incoming.last_seen_at,
                    content_hash=incoming.content_hash,
                    match_score=incoming.match_score,
                    status=incoming.status,
                )
            )
            stats.new += 1
        except Exception:
            stats.errors += 1

    db.commit()
    return stats
