from typing import Any, Dict, List

import httpx

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

MIDEA_ROOT = "https://recruit.midea.com"
MIDEA_LIST_URL = f"{MIDEA_ROOT}/backend/rec/home/out/official/position/list"
MIDEA_DETAIL_URL_PREFIX = (
    f"{MIDEA_ROOT}/backend/rec/home/out/official/position/info"
)
MIDEA_DETAIL_PAGE = f"{MIDEA_ROOT}/recruit-out/#/position?positionId={{id}}"


class MideaOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("midea"),
            method="json",
            parser_name="midea-recruit-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        page_size = min(settings.official_source_max_jobs_per_source, 50)
        max_pages = settings.official_source_max_pages_per_source
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": f"{MIDEA_ROOT}/recruit-out/",
            },
        ) as client:
            for page_index in range(1, max_pages + 1):
                response = client.post(
                    MIDEA_LIST_URL,
                    data={
                        "pageIndex": str(page_index),
                        "pageSize": str(page_size),
                    },
                )
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("data") or []
                if not rows:
                    break
                for row in rows:
                    source_job_id = str(row.get("positionId") or "").strip()
                    if not source_job_id:
                        continue
                    list_location = str(
                        row.get("workingPlace") or row.get("workPlace") or "Unknown"
                    )
                    if classify_official_location(
                        list_location
                    ) == LocationCategory.EXCLUDED:
                        continue
                    detail = client.get(
                        f"{MIDEA_DETAIL_URL_PREFIX}/{source_job_id}"
                    )
                    detail.raise_for_status()
                    job = parse_midea_position(row, detail.json())
                    if job is not None:
                        jobs.append(job)
                    if len(jobs) >= settings.official_source_max_jobs_per_source:
                        return jobs
                info = payload.get("info") or {}
                total_page = int(info.get("totalPage") or page_index)
                if page_index >= total_page:
                    break
        return jobs


def parse_midea_position(
    list_item: Dict[str, Any], detail_item: Dict[str, Any]
) -> Dict[str, Any] | None:
    source_job_id = str(
        detail_item.get("positionId") or list_item.get("positionId") or ""
    ).strip()
    title = str(
        detail_item.get("publicationName")
        or detail_item.get("demandPositionName")
        or list_item.get("publicationName")
        or list_item.get("demandPositionName")
        or ""
    ).strip()
    if not source_job_id or not title:
        return None
    location = str(
        detail_item.get("workingPlace")
        or detail_item.get("workPlace")
        or detail_item.get("detailWorkingPlace")
        or list_item.get("workingPlace")
        or list_item.get("workPlace")
        or "Unknown"
    )
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    description = "\n\n".join(
        str(value).strip()
        for value in (
            detail_item.get("postDuties") or list_item.get("postDuties"),
            detail_item.get("qualification") or list_item.get("qualification"),
        )
        if value
    )
    source_url = MIDEA_DETAIL_PAGE.format(id=source_job_id)
    company = "Midea / 美的集团"
    posted_at = (
        detail_item.get("publicDate")
        or detail_item.get("releaseStartDate")
        or detail_item.get("releaseUpdateDate")
        or list_item.get("releaseStartDate")
        or list_item.get("releaseUpdateDate")
    )
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": posted_at,
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
