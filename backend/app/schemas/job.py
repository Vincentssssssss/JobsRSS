from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    enrichment_source: Optional[str] = None
    location_category: str = "unclassified"


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    company: str
    title: str
    location: str
    apply_url: str
    source_url: str
    posted_at: Optional[datetime]
    match_score: float
    llm_fit_score: Optional[float]
    llm_verdict: Optional[str]
    llm_role_family: Optional[str]
    status: str
    location_category: str

class JobDetail(JobOut):
    country: Optional[str]
    description: str
    updated_at: Optional[datetime]
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    enrichment_source: Optional[str]
    llm_match_reasons: Optional[str]
    llm_reject_reasons: Optional[str]
    llm_missing_skills: Optional[str]
    llm_model: Optional[str]
    llm_last_evaluated_at: Optional[datetime]
