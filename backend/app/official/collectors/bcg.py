import re
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

BCG_WIDGETS_URL = "https://careers.bcg.com/widgets"
BCG_CAREER_ROOT = "https://careers.bcg.com/global/en"


class BcgOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("bcg"),
            method="json",
            parser_name="bcg-phenom-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        base_payload = {
            "lang": "en_global",
            "country": "global",
            "pageName": "search-results",
            "siteType": "external",
        }
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                )
            },
        ) as client:
            response = client.post(
                BCG_WIDGETS_URL,
                json={
                    **base_payload,
                    "size": min(
                        settings.official_source_max_jobs_per_source, 50
                    ),
                    "from": 0,
                    "jobs": True,
                    "selected_fields": {"city": ["Shanghai"]},
                    "sort": {"field": "postedDate", "order": "desc"},
                    "ddoKey": "refineSearch",
                },
            )
            response.raise_for_status()
            listing_jobs = (
                response.json()
                .get("refineSearch", {})
                .get("data", {})
                .get("jobs", [])
            )
            jobs: List[Dict[str, Any]] = []
            for item in listing_jobs:
                if len(jobs) >= settings.official_source_max_jobs_per_source:
                    break
                detail_response = client.post(
                    BCG_WIDGETS_URL,
                    json={
                        **base_payload,
                        "pageName": "job-details",
                        "ddoKey": "jobDetail",
                        "jobId": item.get("jobId"),
                        "jobSeqNo": item.get("jobSeqNo"),
                    },
                )
                detail_response.raise_for_status()
                job = parse_bcg_job(item, detail_response.json())
                if job is not None:
                    jobs.append(job)
            return jobs


def parse_bcg_job(
    listing: Dict[str, Any], detail_payload: Dict[str, Any]
) -> Dict[str, Any] | None:
    detail = (
        detail_payload.get("jobDetail", {}).get("data", {}).get("job") or {}
    )
    source_job_id = str(
        listing.get("jobSeqNo")
        or detail.get("jobSeqNo")
        or listing.get("jobId")
        or detail.get("jobId")
        or ""
    ).strip()
    title = str(
        detail.get("title") or listing.get("title") or ""
    ).strip()
    if not source_job_id or not title:
        return None
    location = str(
        detail.get("location")
        or listing.get("location")
        or " / ".join(
            str(value)
            for value in (
                detail.get("city") or listing.get("city"),
                detail.get("country") or listing.get("country"),
            )
            if value
        )
        or "Unknown"
    )
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    description = BeautifulSoup(
        str(
            detail.get("description")
            or listing.get("descriptionTeaser")
            or ""
        ),
        "html.parser",
    ).get_text("\n", strip=True)
    company = str(
        detail.get("companyName")
        or listing.get("companyName")
        or "Boston Consulting Group / BCG"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    source_url = f"{BCG_CAREER_ROOT}/job/{source_job_id}/{slug}"
    apply_url = str(detail.get("applyUrl") or listing.get("applyUrl") or source_url)
    posted_at = detail.get("postedDate") or listing.get("postedDate")
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": apply_url,
        "source_url": source_url,
        "posted_at": posted_at,
        "content_hash": OfficialCollectorBase.build_hash(
            source_job_id,
            title,
            company,
            location,
            description,
            apply_url,
        ),
        "location_category": category.value,
    }
