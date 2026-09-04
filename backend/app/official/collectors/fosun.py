import re
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

FOSUN_ROOT = "https://fosunpharma.zhiye.com"
FOSUN_SHANGHAI_LIST = (
    f"{FOSUN_ROOT}/social?k=&c=3100&p=&d=&PageIndex={{page}}"
    "&class=1&n=%E4%B8%8A%E6%B5%B7%E5%B8%82&pn=%E5%85%A8%E9%83%A8"
)


class FosunPharmaOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("fosun_pharma"),
            method="server_rendered_html",
            parser_name="fosun-zhiye-html",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        jobs: List[Dict[str, Any]] = []
        seen = set()
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            for page in range(
                1, settings.official_source_max_pages_per_source + 1
            ):
                listing = client.get(FOSUN_SHANGHAI_LIST.format(page=page))
                listing.raise_for_status()
                links = _discover_fosun_links(listing.text)
                new_links = [link for link in links if link not in seen]
                if not new_links:
                    break
                for link in new_links:
                    seen.add(link)
                    detail = client.get(link)
                    detail.raise_for_status()
                    job = parse_fosun_detail(detail.text, link)
                    if job is not None:
                        jobs.append(job)
                    if len(jobs) >= settings.official_source_max_jobs_per_source:
                        return jobs
        return jobs


def parse_fosun_detail(
    html: str, source_url: str
) -> Dict[str, Any] | None:
    job_id = (parse_qs(urlparse(source_url).query).get("jobId") or [""])[0]
    soup = BeautifulSoup(html, "html.parser")
    title_node = soup.select_one(".xqbox h2") or soup.select_one("h2")
    title = title_node.get_text(" ", strip=True) if title_node else ""
    if not job_id or not title:
        return None
    metadata = (
        soup.select_one(".xqt").get_text(" ", strip=True)
        if soup.select_one(".xqt")
        else ""
    )
    company = _metadata_value(metadata, "成员公司") or "Fosun Pharma / 复星医药"
    location = _metadata_value(metadata, "工作地点") or "Unknown"
    category = classify_official_location(location)
    if category == LocationCategory.EXCLUDED:
        return None
    posted_at = _metadata_value(metadata, "发布时间")
    description_node = soup.select_one(".zwxqm")
    description = (
        description_node.get_text("\n", strip=True)
        if description_node
        else ""
    )
    return {
        "source_job_id": job_id,
        "company": company,
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": posted_at,
        "content_hash": OfficialCollectorBase.build_hash(
            job_id,
            title,
            company,
            location,
            description,
            source_url,
        ),
        "location_category": category.value,
    }


def _discover_fosun_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.select("a[href*='socialxq'][href*='jobId=']"):
        candidate = urljoin(FOSUN_ROOT, str(anchor.get("href")))
        parsed = urlparse(candidate)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "fosunpharma.zhiye.com"
        ):
            links.append(candidate)
    return list(dict.fromkeys(links))


def _metadata_value(metadata: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}[：:]\s*(.+?)(?=\s+(?:成员公司|职位分类|招聘人数|发布时间|工作地点)[：:]|$)",
        metadata,
    )
    return match.group(1).strip() if match else ""
