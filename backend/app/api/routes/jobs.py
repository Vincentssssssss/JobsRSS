from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.schemas.job import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    min_score: float = Query(default=0, ge=0, le=100),
):
    return (
        db.query(Job)
        .filter(Job.match_score >= min_score)
        .order_by(desc(Job.posted_at), desc(Job.id))
        .limit(limit)
        .all()
    )
