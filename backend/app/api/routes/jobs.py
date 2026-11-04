from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, false, func, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.normalization.location_standard import (
    canonical_city,
    canonical_country,
    cities_in_country,
    city_country,
    city_label,
    country_label,
    decode_cities,
    parse_search,
)
from app.presentation.description_sections import split_description_sections
from app.schemas.job import JobDetail, JobMarksUpdate, JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])
ALLOWED_LLM_VERDICTS = {"strong_fit", "possible_fit", "not_fit"}
MARK_FILTERS = {
    "favorited": Job.favorited_at.is_not(None),
    "applied": Job.applied_at.is_not(None),
    "not_applied": Job.applied_at.is_(None),
    "viewed": Job.last_viewed_at.is_not(None),
    "not_viewed": Job.last_viewed_at.is_(None),
}
CityParam = Annotated[Optional[str], Query(description="Standard city name(s) or alias(es), comma-separated")]
CountryParam = Annotated[Optional[str], Query(description="Country name(s) or alias(es), comma-separated")]


def _parse_llm_verdicts(value: Optional[str]) -> list[str]:
    if not value:
        return []
    verdicts = []
    for item in value.split(","):
        normalized = item.strip().lower()
        if normalized and normalized in ALLOWED_LLM_VERDICTS and normalized not in verdicts:
            verdicts.append(normalized)
    return verdicts


def _split_values(value: Optional[str]) -> list[str]:
    return [item.strip() for item in (value or "").replace("，", ",").split(",") if item.strip()]


def _city_clause(name: str):
    return Job.location_cities.like(f"%|{name}|%")


def _country_clause(name: str):
    """A multi-city role counts for every country it lists, not only its primary one."""
    return or_(Job.country == name, *(_city_clause(city) for city in cities_in_country(name)))


def _text_clause(text: str):
    like = f"%{text}%"
    return Job.title.ilike(like) | Job.company.ilike(like) | Job.location.ilike(like)


def _apply_location_filters(query, *, city: Optional[str], country: Optional[str]):
    cities = _split_values(city)
    if cities:
        clauses = []
        for value in cities:
            name = canonical_city(value)
            clauses.append(_city_clause(name) if name else Job.location.ilike(f"%{value}%"))
        query = query.filter(or_(*clauses))
    countries = _split_values(country)
    if countries:
        clauses = []
        for value in countries:
            name = canonical_country(value)
            clauses.append(_country_clause(name) if name else Job.country == value)
        query = query.filter(or_(*clauses))
    return query


def _apply_jobs_filters(
    query,
    *,
    min_score: float,
    source: Optional[str],
    q: Optional[str],
    location_category: Optional[str],
    min_llm_score: Optional[float],
    llm_verdicts: list[str],
    llm_verdict_raw: Optional[str],
    status: Optional[str],
    mark: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
):
    query = query.filter(Job.match_score >= min_score)
    if mark:
        if mark not in MARK_FILTERS:
            raise HTTPException(status_code=422, detail=f"Unknown mark filter: {mark}")
        query = query.filter(MARK_FILTERS[mark])
    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if q:
        # Every term must match. A place name also matches the standardized
        # location, so "上海", "Shanghai" and "浦东" listings are found either way.
        for term in parse_search(q):
            if term.city:
                place = _city_clause(term.city)
            elif term.country:
                place = _country_clause(term.country)
            else:
                place = None
            if place is None:
                clause = _text_clause(term.text)
            elif term.place_only:
                clause = place
            else:
                clause = _text_clause(term.text) | place
            query = query.filter(clause)
    if location_category:
        query = query.filter(Job.location_category == location_category)
    query = _apply_location_filters(query, city=city, country=country)
    if min_llm_score is not None:
        query = query.filter(Job.llm_fit_score.is_not(None), Job.llm_fit_score >= min_llm_score)
    if llm_verdict_raw:
        if llm_verdicts:
            query = query.filter(Job.llm_verdict.in_(llm_verdicts))
        else:
            query = query.filter(false())
    return query


@router.get("", response_model=List[JobOut])
def list_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    location_category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None, ge=0, le=100),
    llm_verdict: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    mark: Optional[str] = Query(default=None),
    city: CityParam = None,
    country: CountryParam = None,
):
    llm_verdicts = _parse_llm_verdicts(llm_verdict)
    query = _apply_jobs_filters(
        db.query(Job),
        min_score=min_score,
        source=source,
        q=q,
        location_category=location_category,
        min_llm_score=min_llm_score,
        llm_verdicts=llm_verdicts,
        llm_verdict_raw=llm_verdict,
        status=status,
        mark=mark,
        city=city,
        country=country,
    )
    return query.order_by(desc(Job.posted_at), desc(Job.id)).offset(offset).limit(limit).all()


@router.get("/count")
def jobs_count(
    db: Session = Depends(get_db),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    location_category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None, ge=0, le=100),
    llm_verdict: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    mark: Optional[str] = Query(default=None),
    city: CityParam = None,
    country: CountryParam = None,
):
    llm_verdicts = _parse_llm_verdicts(llm_verdict)
    query = _apply_jobs_filters(
        db.query(func.count(Job.id)),
        min_score=min_score,
        source=source,
        q=q,
        location_category=location_category,
        min_llm_score=min_llm_score,
        llm_verdicts=llm_verdicts,
        llm_verdict_raw=llm_verdict,
        status=status,
        mark=mark,
        city=city,
        country=country,
    )
    total = query.scalar() or 0
    return {"total": total}


@router.get("/source-counts")
def jobs_source_counts(
    db: Session = Depends(get_db),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    location_category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None, ge=0, le=100),
    llm_verdict: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    mark: Optional[str] = Query(default=None),
    city: CityParam = None,
    country: CountryParam = None,
):
    llm_verdicts = _parse_llm_verdicts(llm_verdict)
    query = _apply_jobs_filters(
        db.query(Job.source, func.count(Job.id)),
        min_score=min_score,
        source=source,
        q=q,
        location_category=location_category,
        min_llm_score=min_llm_score,
        llm_verdicts=llm_verdicts,
        llm_verdict_raw=llm_verdict,
        status=status,
        mark=mark,
        city=city,
        country=country,
    )
    rows = (
        query
        .group_by(Job.source)
        .order_by(desc(func.count(Job.id)), asc(Job.source))
        .all()
    )
    counts = [{"source": row[0], "count": row[1]} for row in rows]
    return {"counts": counts}


@router.get("/locations")
def jobs_locations(
    db: Session = Depends(get_db),
    min_score: float = Query(default=0, ge=0, le=100),
    source: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    location_category: Optional[str] = Query(default=None),
    min_llm_score: Optional[float] = Query(default=None, ge=0, le=100),
    llm_verdict: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="active"),
    mark: Optional[str] = Query(default=None),
):
    """Standard countries and cities with job counts under the other filters, for
    the dashboard's location picker. A multi-city role counts once for each city."""
    llm_verdicts = _parse_llm_verdicts(llm_verdict)
    query = _apply_jobs_filters(
        db.query(Job.country, Job.location_cities, func.count(Job.id)),
        min_score=min_score,
        source=source,
        q=q,
        location_category=location_category,
        min_llm_score=min_llm_score,
        llm_verdicts=llm_verdicts,
        llm_verdict_raw=llm_verdict,
        status=status,
        mark=mark,
    )
    country_counts: Counter = Counter()
    city_counts: Counter = Counter()
    unknown = 0
    total = 0
    for country, stored_cities, count in query.group_by(Job.country, Job.location_cities).all():
        total += count
        cities = decode_cities(stored_cities)
        countries = {city_country(name) for name in cities} | ({country} if country else set())
        countries.discard(None)
        if not countries:
            unknown += count
        for name in countries:
            country_counts[name] += count
        for name in cities:
            city_counts[name] += count

    def by_count(item):
        return (-item[1], item[0])

    return {
        "total": total,
        "unknown": unknown,
        "countries": [
            {
                "country": name,
                "label": country_label(name),
                "count": count,
                "cities": [
                    {"city": city, "label": city_label(city), "count": city_count}
                    for city, city_count in sorted(city_counts.items(), key=by_count)
                    if city_country(city) == name
                ],
            }
            for name, count in sorted(country_counts.items(), key=by_count)
        ],
    }


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
    detail = JobDetail.model_validate(job)
    detail.description_sections = [
        {"title": section.title, "lines": section.lines}
        for section in split_description_sections(job.description)
    ]
    return detail


def _get_job_or_404(db: Session, job_id: int) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/{job_id}/marks", response_model=JobOut)
def update_job_marks(job_id: int, marks: JobMarksUpdate, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    now = datetime.now(timezone.utc)
    if marks.favorited is not None:
        job.favorited_at = (job.favorited_at or now) if marks.favorited else None
    if marks.applied is not None:
        job.applied_at = (job.applied_at or now) if marks.applied else None
    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/view", response_model=JobOut)
def record_job_view(job_id: int, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    job.view_count = (job.view_count or 0) + 1
    job.last_viewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return job
