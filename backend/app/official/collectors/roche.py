import re
from typing import Any, Dict, List

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase, interleave_capped
from app.official.collectors.phenom import (
    fetch_phenom_listing,
    phenom_job_key,
    phenom_multi_location,
)
from app.official.location import (
    LocationCategory,
    classify_official_location,
    country_for_category,
)
from app.official.registry import get_official_source

ROCHE_WIDGETS_URL = "https://careers.roche.com/widgets"
ROCHE_LOCATION_FILTERS = (
    {"country": ["China's Mainland"], "city": ["Shanghai"]},
    {"country": ["Malaysia"]},
)


class RocheOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("roche"),
            method="json",
            parser_name="roche-phenom-json",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        base_payload = {
            "lang": "en_global",
            "country": "global",
            "pageName": "search-results",
            "pageId": "page11",
            "siteType": "external",
            "refNum": "ROCHGLOBAL",
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
            limit = settings.official_source_max_jobs_per_source
            groups = [
                fetch_phenom_listing(
                    client,
                    ROCHE_WIDGETS_URL,
                    base_payload,
                    selected_fields,
                    limit=limit,
                    max_pages=settings.official_source_max_pages_per_source,
                )
                for selected_fields in ROCHE_LOCATION_FILTERS
            ]
            jobs: List[Dict[str, Any]] = []
            for item in interleave_capped(groups, limit, key=phenom_job_key):
                detail_response = client.post(
                    ROCHE_WIDGETS_URL,
                    json={
                        **base_payload,
                        "pageName": "job-details",
                        "ddoKey": "jobDetail",
                        "jobId": item.get("jobId"),
                        "jobSeqNo": item.get("jobSeqNo"),
                    },
                )
                detail_response.raise_for_status()
                job = parse_roche_job(item, detail_response.json())
                if job is not None:
                    jobs.append(job)
            return jobs


def parse_roche_job(
    listing: Dict[str, Any], detail_payload: Dict[str, Any]
) -> Dict[str, Any] | None:
    detail = (
        detail_payload.get("jobDetail", {}).get("data", {}).get("job", {})
    )
    structured = detail.get("structureData") or {}
    source_job_id = str(
        listing.get("jobSeqNo")
        or listing.get("jobId")
        or structured.get("identifier", {}).get("value")
        or ""
    ).strip()
    title = str(
        structured.get("title")
        or detail.get("title")
        or listing.get("title")
        or ""
    ).strip()
    if not source_job_id or not title:
        return None
    address = (structured.get("jobLocation") or {}).get("address") or {}
    location = ", ".join(
        str(address.get(key))
        for key in ("addressLocality", "addressRegion", "addressCountry")
        if address.get(key)
    )
    location = location or str(listing.get("location") or "Unknown")
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED and phenom_multi_location(listing):
        location = phenom_multi_location(listing)
        category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    description = BeautifulSoup(
        str(structured.get("description") or listing.get("descriptionTeaser") or ""),
        "html.parser",
    ).get_text("\n", strip=True)
    company = str(detail.get("companyName") or "Roche")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    source_url = (
        "https://careers.roche.com/global/en/job/"
        f"{source_job_id}/{slug}"
    )
    apply_url = str(listing.get("applyUrl") or source_url)
    posted_at = structured.get("datePosted") or listing.get("postedDate")
    return {
        "source_job_id": source_job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": country_for_category(category),
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
