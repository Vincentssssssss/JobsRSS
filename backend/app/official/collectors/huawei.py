from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

HUAWEI_API_ROOT = "https://apigw-dgg-b0.huawei.com/api/apig/channelhw"
HUAWEI_APP_ID = "app_000000035886"


class HuaweiOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("huawei"),
            method="json",
            parser_name="huawei-careers-gateway-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        response = httpx.post(
            f"{HUAWEI_API_ROOT}/recruitmentPosition/pub/getJobPage",
            params={"X-HW-ID": HUAWEI_APP_ID},
            headers={
                "X-HW-ID": HUAWEI_APP_ID,
                "x-jalor-tenantAlias": "hcm",
                "x-language": "zh_CN",
                "Origin": "https://career.huawei.com",
                "Referer": "https://career.huawei.com/",
                "User-Agent": "JobsRSS/2.0 (+personal job monitor)",
            },
            json={
                "curPage": 1,
                "pageSize": min(
                    settings.official_source_max_jobs_per_source, 100
                ),
                "jobType": "SR",
                "jobAddress": "China\\Shanghai-Shanghai",
            },
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
        )
        response.raise_for_status()
        return parse_huawei_jobs(response.json())


def parse_huawei_jobs(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = _find_items(payload)
    jobs: List[Dict[str, Any]] = []
    for item in items:
        source_job_id = str(
            item.get("advertisementId")
            or item.get("jobId")
            or item.get("id")
            or ""
        ).strip()
        title = str(
            item.get("jobName")
            or item.get("positionName")
            or item.get("title")
            or ""
        ).strip()
        if not source_job_id or not title:
            continue
        location = str(
            item.get("jobAddress")
            or item.get("address")
            or item.get("city")
            or "Unknown"
        )
        category = classify_official_location(location)
        if category == LocationCategory.EXCLUDED:
            continue
        description = "\n\n".join(
            str(value).strip()
            for value in (
                item.get("jobResponsibility")
                or item.get("responsibility")
                or item.get("jobDescription"),
                item.get("jobRequirement")
                or item.get("requirement")
                or item.get("qualification"),
            )
            if value
        )
        source_url = (
            "https://career.huawei.com/cn/job-details"
            f"?advertisementId={source_job_id}"
        )
        company = "Huawei / Huawei Cloud"
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
                "posted_at": item.get("lastUpdateDate")
                or item.get("updateDate"),
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


def _find_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Any] = [
        payload.get("data"),
        payload.get("result"),
    ]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend(
            [result.get("data"), result.get("list"), result.get("content")]
        )
        nested = result.get("data")
        if isinstance(nested, dict):
            candidates.extend(
                [nested.get("list"), nested.get("content"), nested.get("records")]
            )
    for candidate in candidates:
        if isinstance(candidate, list) and all(
            isinstance(item, dict) for item in candidate
        ):
            return candidate
    return []
