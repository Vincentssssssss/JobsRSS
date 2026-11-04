from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.normalization.location_standard import decode_cities, location_label


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_job_id", name="uq_source_source_job_id"),
        Index("ix_jobs_posted_at", "posted_at"),
        Index("ix_jobs_match_score", "match_score"),
        Index("ix_jobs_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[Optional[str]] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    apply_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    match_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="active", nullable=False)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    enrichment_source: Mapped[Optional[str]] = mapped_column(String(64))
    location_category: Mapped[str] = mapped_column(
        String(32), default="unclassified", nullable=False
    )
    llm_fit_score: Mapped[Optional[float]] = mapped_column(Float)
    llm_verdict: Mapped[Optional[str]] = mapped_column(String(32))
    llm_role_family: Mapped[Optional[str]] = mapped_column(String(128))
    llm_match_reasons: Mapped[Optional[str]] = mapped_column(Text)
    llm_reject_reasons: Mapped[Optional[str]] = mapped_column(Text)
    llm_missing_skills: Mapped[Optional[str]] = mapped_column(Text)
    llm_model: Mapped[Optional[str]] = mapped_column(String(128))
    llm_last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    favorited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    view_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    location_cities: Mapped[Optional[str]] = mapped_column(String(512))

    @property
    def cities(self) -> List[str]:
        return decode_cities(self.location_cities)

    @property
    def location_label(self) -> str:
        return location_label(self.cities, self.country)
