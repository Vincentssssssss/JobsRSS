from datetime import timezone

from fastapi import APIRouter, Depends, Response
from feedgen.feed import FeedGenerator
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.job import Job

router = APIRouter(prefix="/rss", tags=["rss"])


def _build_feed(title: str, jobs: list[Job]) -> str:
    settings = get_settings()
    fg = FeedGenerator()
    fg.id(f"{settings.rss_base_url}/rss/{title}")
    fg.title(f"JobsRSS - {title}")
    fg.link(href=settings.rss_base_url)
    fg.description(f"JobsRSS feed: {title}")

    for job in jobs:
        fe = fg.add_entry()
        fe.id(f"{job.source}:{job.source_job_id}")
        fe.title(f"{job.company} - {job.title} ({job.location})")
        fe.link(href=job.apply_url)
        fe.description(job.description[:500])
        if job.posted_at:
            fe.pubDate(job.posted_at.astimezone(timezone.utc))

    return fg.rss_str(pretty=True).decode("utf-8")


@router.get("/all.xml")
def rss_all(db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .filter(Job.status == "active")
        .order_by(desc(Job.posted_at), desc(Job.id))
        .limit(200)
        .all()
    )
    xml = _build_feed("all", jobs)
    return Response(content=xml, media_type="application/rss+xml")


@router.get("/high-match.xml")
def rss_high_match(db: Session = Depends(get_db)):
    settings = get_settings()
    jobs = (
        db.query(Job)
        .filter(
            Job.match_score >= settings.high_match_threshold,
            Job.status == "active",
        )
        .order_by(desc(Job.posted_at), desc(Job.id))
        .limit(200)
        .all()
    )
    xml = _build_feed("high-match", jobs)
    return Response(content=xml, media_type="application/rss+xml")


@router.get("/company/{company}.xml")
def rss_by_company(company: str, db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .filter(
            Job.company.ilike(f"%{company}%"),
            Job.status == "active",
        )
        .order_by(desc(Job.posted_at), desc(Job.id))
        .limit(200)
        .all()
    )
    xml = _build_feed(f"company/{company}", jobs)
    return Response(content=xml, media_type="application/rss+xml")
