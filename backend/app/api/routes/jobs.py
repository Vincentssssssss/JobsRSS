from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import JobDetail, JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    location_category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
):
    query = db.query(Job).filter(Job.match_score >= min_score)
    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter((Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.location.ilike(like)))
    if location_category:
        query = query.filter(Job.location_category == location_category)
    return query.order_by(desc(Job.posted_at), desc(Job.id)).offset(offset).limit(limit).all()


@router.get("/count")
def jobs_count(
    db: Session = Depends(get_db),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    location_category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
):
    query = db.query(func.count(Job.id)).filter(Job.match_score >= min_score)
    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if q:
        like = f"%{q}%"
        query = query.filter((Job.title.ilike(like)) | (Job.company.ilike(like)) | (Job.location.ilike(like)))
    if location_category:
        query = query.filter(Job.location_category == location_category)
    total = query.scalar() or 0
    return {"total": total}


@router.get("/summary/last-24h")
def summary_last_24h(db: Session = Depends(get_db)):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    total = (
        db.query(func.count(Job.id))
        .filter(Job.first_seen_at >= cutoff, Job.status == "active")
        .scalar()
        or 0
    )
    high_match = (
        db.query(func.count(Job.id))
        .filter(
            Job.first_seen_at >= cutoff,
            Job.match_score >= 80,
            Job.status == "active",
        )
        .scalar()
        or 0
    )
    source_rows = (
        db.query(Job.source, func.count(Job.id))
        .filter(Job.first_seen_at >= cutoff, Job.status == "active")
        .group_by(Job.source)
        .order_by(desc(func.count(Job.id)))
        .all()
    )
    top_jobs = (
        db.query(Job)
        .filter(Job.first_seen_at >= cutoff, Job.status == "active")
        .order_by(desc(Job.match_score), desc(Job.posted_at), desc(Job.id))
        .limit(20)
        .all()
    )
    return {
        "window_hours": 24,
        "total_new_jobs": total,
        "high_match_jobs": high_match,
        "by_source": [{"source": row[0], "count": row[1]} for row in source_rows],
        "top_jobs": [
            {
                "id": job.id,
                "source": job.source,
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "match_score": job.match_score,
                "apply_url": job.apply_url,
            }
            for job in top_jobs
        ],
    }


@router.get("/{job_id}", response_model=JobDetail)
def get_job_detail(job_id: int, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
