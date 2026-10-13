from datetime import datetime, timezone

from app.normalization.normalizer import normalize_job
from app.schemas.job import UnifiedJob


def _make_job(location: str) -> UnifiedJob:
    now = datetime.now(timezone.utc)
    return UnifiedJob(
        source="official_amazon_aws",
        source_job_id="job-1",
        company="Amazon",
        title="Security Engineer",
        location=location,
        description="Security role in cloud platform.",
        apply_url="https://example.com/apply",
        source_url="https://example.com/jobs/1",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-1",
    )


def test_shanghai_name_is_normalized_to_chinese():
    normalized = normalize_job(_make_job("Shanghai, China"))
    assert normalized.location == "上海"


def test_shanghai_district_alias_is_normalized_to_chinese():
    normalized = normalize_job(_make_job("Pudong New Area"))
    assert normalized.location == "上海"


def test_non_shanghai_city_keeps_original_location():
    normalized = normalize_job(_make_job("Shenzhen, China"))
    assert normalized.location == "Shenzhen, China"


def test_non_target_city_with_same_district_name_is_not_misclassified():
    normalized = normalize_job(_make_job("Putuo District, Zhoushan, Zhejiang, China"))
    assert normalized.location == "Putuo District, Zhoushan, Zhejiang, China"
