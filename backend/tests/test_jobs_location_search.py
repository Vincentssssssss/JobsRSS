from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes.jobs import jobs_count, jobs_locations, list_jobs
from app.db.session import Base
from app.models.job import Job
from app.normalization.normalizer import normalize_job
from app.pipeline import ingest_collector, standardize_stored_locations
from app.schemas.job import JobOut, UnifiedJob
from tests.test_pipeline_updates import StubOfficialCollector


def _unified(source_job_id: str, location: str, *, title: str = "Security Architect",
             company: str = "Acme", country=None) -> UnifiedJob:
    now = datetime.now(timezone.utc)
    return UnifiedJob(
        source="official_test_company",
        source_job_id=source_job_id,
        company=company,
        title=title,
        location=location,
        country=country,
        description="Cloud security role.",
        apply_url=f"https://example.com/{source_job_id}",
        source_url=f"https://example.com/{source_job_id}",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash=f"hash-{source_job_id}",
    )


def _store(db: Session, job: UnifiedJob) -> Job:
    job = normalize_job(job)
    row = Job(**job.model_dump(exclude={"match_score"}), match_score=50)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _store(session, _unified("amazon-sh", "Shanghai, CHN"))
        _store(session, _unified("kpmg-sh", "闵行区, 上海, 上海市, 中国", title="网络安全经理"))
        _store(session, _unified("ali-hz", "北京 / 杭州", title="Security Engineer"))
        _store(session, _unified("ms-sz", "Beijing, Beijing, CN / Suzhou, Jiangsu, CN"))
        _store(session, _unified("aws-hk", "Hong Kong, Hong Kong SAR, HKG"))
        _store(session, _unified("ms-kl", "Kuala Lumpur, Federal Territory of Kuala Lumpur, MY"))
        _store(session, _unified("bcg-sea", "Singapore, Singapore / Kuala Lumpur, Malaysia"))
        _store(session, _unified("bank", "Beijing", company="Bank of Shanghai"))
        yield session


def _ids(jobs) -> set:
    return {job.source_job_id for job in jobs}


def _list(db, **filters):
    params = dict(limit=100, min_score=0, source=None, q=None, offset=0, location_category=None,
                  min_llm_score=None, llm_verdict=None, status="active", mark=None)
    params.update(filters)
    return list_jobs(db=db, **params)


def test_place_names_in_any_language_find_the_same_jobs(db):
    shanghai = {"amazon-sh", "kpmg-sh"}
    assert _ids(_list(db, q="上海")) == shanghai
    assert _ids(_list(db, q="SH")) == shanghai
    # A place term still matches as text, so the company name is found too.
    assert _ids(_list(db, q="Shanghai")) == shanghai | {"bank"}


def test_place_and_keyword_terms_must_all_match(db):
    assert _ids(_list(db, q="security 杭州")) == {"ali-hz"}
    assert _ids(_list(db, q="Hangzhou security")) == {"ali-hz"}
    assert _ids(_list(db, q="上海安全")) == {"kpmg-sh"}
    assert _ids(_list(db, q="architect hong kong")) == {"aws-hk"}


def test_country_search_includes_every_city_of_a_multi_location_role(db):
    assert _ids(_list(db, q="马来西亚")) == {"ms-kl", "bcg-sea"}
    assert _ids(_list(db, q="新加坡")) == {"bcg-sea"}


def test_city_and_country_filters_accept_aliases(db):
    assert _ids(_list(db, city="Shanghai")) == {"amazon-sh", "kpmg-sh"}
    assert _ids(_list(db, city="苏州")) == {"ms-sz"}
    assert _ids(_list(db, city="Beijing")) == {"ali-hz", "ms-sz", "bank"}
    assert _ids(_list(db, city="Hangzhou,Suzhou")) == {"ali-hz", "ms-sz"}
    assert _ids(_list(db, country="Malaysia")) == {"ms-kl", "bcg-sea"}
    assert _ids(_list(db, country="HKG")) == {"aws-hk"}
    assert jobs_count(
        db=db, min_score=0, source=None, q=None, location_category=None, min_llm_score=None,
        llm_verdict=None, status="active", mark=None, country="China",
    ) == {"total": 5}


def test_location_counts_group_cities_under_their_country(db):
    result = jobs_locations(
        db=db, min_score=0, source=None, q=None, location_category=None, min_llm_score=None,
        llm_verdict=None, status="active", mark=None,
    )
    countries = {item["country"]: item for item in result["countries"]}
    assert result["total"] == 8
    assert result["unknown"] == 0
    assert countries["China"]["count"] == 5
    assert countries["China"]["label"] == "中国 China"
    china_cities = {city["city"]: city["count"] for city in countries["China"]["cities"]}
    assert china_cities == {"Beijing": 3, "Shanghai": 2, "Hangzhou": 1, "Suzhou": 1}
    assert countries["Malaysia"]["count"] == 2
    assert countries["Singapore"]["cities"] == [
        {"city": "Singapore", "label": "新加坡 Singapore", "count": 1}
    ]


def test_location_counts_follow_the_other_filters(db):
    result = jobs_locations(
        db=db, min_score=0, source=None, q="security", location_category=None,
        min_llm_score=None, llm_verdict=None, status="active", mark=None,
    )
    assert result["total"] == 7
    assert {item["country"] for item in result["countries"]} == {
        "China", "Hong Kong", "Malaysia", "Singapore",
    }


def test_job_output_carries_the_standard_location(db):
    row = db.query(Job).filter(Job.source_job_id == "ali-hz").one()
    out = JobOut.model_validate(row)
    assert out.cities == ["Hangzhou", "Beijing"]
    assert out.country == "China"
    assert out.location_label == "杭州 Hangzhou / 北京 Beijing · 中国 China"
    assert out.location == "北京 / 杭州"


def test_shanghai_listing_keeps_its_other_cities_after_normalization():
    job = normalize_job(_unified("x", "Shanghai, CHN / Beijing, CHN"))
    assert job.location == "上海"
    assert job.location_cities == "|Shanghai|Beijing|"
    assert job.country == "China"


def test_platform_rows_get_a_location_category():
    job = _unified("li-1", "上海-浦东新区")
    job.source = "liepin_auth"
    assert normalize_job(job).location_category == "confirmed_shanghai"


def test_ingest_stores_and_refreshes_standard_cities():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ingest_collector(db, StubOfficialCollector(_unified("job-1", "Hangzhou, CHN")))
        row = db.query(Job).one()
        assert (row.location_cities, row.country) == ("|Hangzhou|", "China")
        ingest_collector(db, StubOfficialCollector(_unified("job-1", "Hong Kong, Hong Kong SAR, HKG")))
        db.refresh(row)
        assert (row.location_cities, row.country) == ("|Hong Kong|", "Hong Kong")


def test_stored_rows_are_standardized_once_and_keep_collected_cities():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    def row(source, source_job_id, location, country, category="unclassified", cities=None):
        return Job(
            source=source, source_job_id=source_job_id, company="Acme", title="Security Lead",
            location=location, country=country, description="d", apply_url="https://e.x",
            source_url="https://e.x", first_seen_at=now, last_seen_at=now, content_hash="h",
            location_category=category, location_cities=cities,
        )

    with Session(engine) as db:
        db.add_all([
            row("linkedin_auth", "li", "Kuala Lumpur, Malaysia", "Unknown"),
            row("official_deloitte", "dt", "香港", "China", "confirmed_hong_kong"),
            row("official_amazon_aws", "aws", "上海", "China", "confirmed_shanghai",
                "|Shanghai|Beijing|"),
            row("official_kpmg", "kp", "武侯区, 四川, China", "China"),
            row("official_anta", "an", "九龙坡区, 重庆市, 中国", "China", "confirmed_hong_kong"),
        ])
        db.commit()

        assert standardize_stored_locations(db) == 4
        stored = {job.source_job_id: job for job in db.query(Job).all()}
        assert (stored["li"].location_cities, stored["li"].country) == ("|Kuala Lumpur|", "Malaysia")
        assert stored["li"].location_category == "confirmed_malaysia"
        assert (stored["dt"].location_cities, stored["dt"].country) == ("|Hong Kong|", "Hong Kong")
        assert stored["aws"].location_cities == "|Shanghai|Beijing|"
        assert stored["kp"].location_cities == "|Chengdu|"
        assert stored["kp"].location_category == "unclassified"
        assert stored["an"].location_cities == "|Chongqing|"
        assert stored["an"].location_category == "excluded"

        assert standardize_stored_locations(db) == 0
