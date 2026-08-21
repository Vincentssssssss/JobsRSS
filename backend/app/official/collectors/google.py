import re
from html import unescape
from typing import Any, Dict, List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.enrichment.external_job import ExternalJobEnricher
from app.official.collectors.base import OfficialCollectorBase
from app.official.location import LocationCategory, classify_official_location
from app.official.registry import get_official_source

GOOGLE_SEARCH_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "?location=Shanghai%2C%20China&sort_by=date"
)
GOOGLE_ROOT = "https://www.google.com"
GOOGLE_JOB_PATH = re.compile(
    r"/about/careers/applications/jobs/results/(\d+)-[^?#]+"
)


class GoogleOfficialCollector(OfficialCollectorBase):
    def __init__(self) -> None:
        super().__init__(
            get_official_source("google"),
            method="server_rendered_html",
            parser_name="google-careers-ssr-html",
        )

    def fetch_raw(self) -> List[Dict[str, Any]]:
        settings = get_settings()
        with httpx.Client(
            timeout=settings.official_source_timeout_seconds,
            verify=settings.official_source_verify_tls,
            headers={"User-Agent": "JobsRSS/2.0 (+personal job monitor)"},
            follow_redirects=True,
        ) as client:
            listing_response = client.get(GOOGLE_SEARCH_URL)
            listing_response.raise_for_status()
            links = discover_google_job_links(listing_response.text)
            jobs = []
            for link in links[: settings.official_source_max_jobs_per_source]:
                response = client.get(link)
                response.raise_for_status()
                job = parse_google_job_detail(response.text, str(response.url))
                if job is not None:
                    jobs.append(job)
            return jobs


def discover_google_job_links(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "")
        full_url = urljoin(GOOGLE_ROOT, href)
        if GOOGLE_JOB_PATH.search(full_url):
            links.append(full_url.split("?", 1)[0].split("#", 1)[0])
    decoded = unescape(html).replace("\\/", "/")
    for match in re.finditer(
        r"(?:/about/careers/applications/)?jobs/results/(\d+)-([a-z0-9-]+)",
        decoded,
        flags=re.IGNORECASE,
    ):
        links.append(
            f"{GOOGLE_ROOT}/about/careers/applications/jobs/results/"
            f"{match.group(1)}-{match.group(2)}"
        )
    return list(dict.fromkeys(links))


def parse_google_job_detail(html: str, source_url: str) -> Dict[str, Any] | None:
    match = GOOGLE_JOB_PATH.search(source_url)
    if not match:
        return None
    source_job_id = match.group(1)
    structured = ExternalJobEnricher.parse_html(
        html,
        final_url=source_url,
        provider="company_site",
    )
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one("meta[property='og:title']")
    meta_title = str(meta.get("content") or "") if meta else ""
    structured_title = (
        "" if structured.title.lower() == "job details" else structured.title
    )
    title = structured_title or meta_title
    if not title:
        title = _first_text(soup, ["[itemprop='title']", "h1"])
    title = re.sub(r"\s+[—|-]\s+Google Careers.*$", "", title).strip()
    if title.lower() == "job details":
        return None
    if not title:
        return None
    location = structured.location or _first_text(
        soup,
        [
            ".job-location",
            "[itemprop='jobLocation']",
            "[data-location]",
            "[aria-label*='location' i]",
        ],
    )
    location = location or "Shanghai, China"
    location_category = classify_official_location(location)
    if location_category == LocationCategory.EXCLUDED:
        return None
    description = structured.description or _first_text(
        soup,
        [
            ".job-description",
            "[itemprop='description']",
            "main",
        ],
    )
    semantic_sections = _google_detail_sections(soup)
    if semantic_sections:
        description = semantic_sections
    content_hash = OfficialCollectorBase.build_hash(
        source_job_id, title, "Google", location, description, source_url
    )
    return {
        "source_job_id": source_job_id,
        "company": "Google",
        "title": title,
        "location": location,
        "country": "China",
        "description": description,
        "apply_url": source_url,
        "source_url": source_url,
        "posted_at": structured.posted_at,
        "content_hash": content_hash,
        "location_category": location_category.value,
    }


def _first_text(soup: BeautifulSoup, selectors: List[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return " ".join(node.get_text(" ", strip=True).split())
    return ""


def _google_detail_sections(soup: BeautifulSoup) -> str:
    section_names = {
        "minimum qualifications",
        "preferred qualifications",
        "about the job",
        "responsibilities",
    }
    sections: List[str] = []
    for heading in soup.select("h2, h3"):
        normalized = heading.get_text(" ", strip=True).lower().rstrip(":")
        if normalized not in section_names:
            continue
        container = heading.parent
        text = " ".join(container.get_text(" ", strip=True).split())
        if text:
            sections.append(text)
    return "\n\n".join(dict.fromkeys(sections))
