from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UnifiedJob(BaseModel):
    source: str
    source_job_id: str
    company: str
    title: str
    location: str
    country: Optional[str] = None
    description: str
    apply_url: str
    source_url: str
    posted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    content_hash: str
    match_score: float = Field(default=0, ge=0, le=100)
    status: str = "active"


class JobOut(BaseModel):
    id: int
    source: str
    company: str
    title: str
    location: str
    apply_url: str
    source_url: str
    posted_at: Optional[datetime]
    match_score: float
    status: str

    class Config:
        from_attributes = True
