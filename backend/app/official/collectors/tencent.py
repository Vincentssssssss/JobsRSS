import math
from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

TENCENT_SEARCH_URL = "https://careers.tencent.com/tencentcareer/api/post/Query"
TENCENT_DETAIL_URL = "https://careers.tencent.com/tencentcareer/api/post/ByPostId"


class TencentOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("tencent"),
            method="json",
            parser_name="tencent-careers-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        page_size = 50
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={"User-Agent": "JobsRSS/2.0 (+personal job monitor)"},
        ) as client:
            for page_index in range(
                1,
                min(
                    math.ceil(
                        settings.official_source_max_jobs_per_source / page_size
                    ),
                    settings.official_source_max_pages_per_source,
                )
                + 1,
            ):
                response = client.get(
                    TENCENT_SEARCH_URL,
                    params={
                        "cityId": 3,
                        "pageIndex": page_index,
                        "pageSize": page_size,
                        "language": "zh-cn",
                        "area": "cn",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                parsed = parse_tencent_jobs(payload)
                jobs.extend(parsed)
                posts = (payload.get("Data") or {}).get("Posts") or []
                if len(posts) < page_size:
                    break
        return jobs[: settings.official_source_max_jobs_per_source]


def parse_tencent_jobs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = payload.get("Data") or payload.get("data") or {}
    posts = data.get("Posts") or data.get("posts") or data.get("items") or []
    jobs: List[Dict[str, Any]] = []
    for item in posts:
        source_job_id = str(
            item.get("PostId") or item.get("postId") or item.get("id") or ""
        ).strip()
        title = str(
            item.get("RecruitPostName")
            or item.get("PostName")
            or item.get("title")
            or ""
        ).strip()
        if not source_job_id or not title:
            continue
        location = str(
            item.get("LocationName")
            or item.get("Location")
            or item.get("location")
            or "Unknown"
        )
        category = classify_official_location(location)
        if category == LocationCategory.EXCLUDED:
            continue
        description = "\n\n".join(
            str(value).strip()
            for value in (
                item.get("Responsibility") or item.get("responsibility"),
                item.get("Requirement") or item.get("requirement"),
            )
            if value
        )
        source_url = (
            f"https://careers.tencent.com/jobdesc.html?postId={source_job_id}"
        )
        company = "Tencent / Tencent Cloud"
        jobs.append(
            {
                "source_job_id": source_job_id,
                "company": company,
                "title": title,
                "location": location,
                "country": "China",
                "description": description,
                "apply_url": source_url,
                "source_url": source_url,
                "posted_at": item.get("LastUpdateTime")
                or item.get("lastUpdateTime"),
                "content_hash": OfficialCollectorBase.build_hash(
                    source_job_id,
                    title,
                    company,
                    location,
                    description,
                    source_url,
                ),
                "location_category": category.value,
            }
        )
    return jobs
