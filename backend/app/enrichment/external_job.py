import html as html_lib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass
class EnrichedJobData:
    official_url: str
    provider: str
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    posted_at: Optional[datetime] = None
    structured: bool = False

    @property
    def has_authoritative_content(self) -> bool:
        known_ats = self.provider in {
            "workday",
            "greenhouse",
            "lever",
            "smartrecruiters",
            "successfactors",
        }
        return bool(
            self.title
            and self.company
            and len(self.description) >= 80
            and (self.structured or known_ats)
        )


def detect_ats_provider(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if _host_matches(host, "myworkdayjobs.com") or _host_matches(host, "workday.com"):
        return "workday"
    if _host_matches(host, "greenhouse.io"):
        return "greenhouse"
    if _host_matches(host, "lever.co"):
        return "lever"
    if _host_matches(host, "smartrecruiters.com"):
        return "smartrecruiters"
    if _host_matches(host, "successfactors.com") or _host_matches(host, "successfactors.eu"):
        return "successfactors"
    return "company_site"


def merge_job_fields(linkedin: Dict[str, Any], official: Optional[EnrichedJobData]) -> Dict[str, Any]:
    source_url = linkedin.get("source_url") or linkedin.get("job_url") or linkedin.get("apply_url", "")
    if official is None or not official.has_authoritative_content:
        return {
            **linkedin,
            "apply_url": linkedin.get("apply_url") or source_url,
            "source_url": source_url,
        }

    return {
        **linkedin,
        "title": official.title or linkedin.get("title", ""),
        "company": official.company or linkedin.get("company", ""),
        "location": official.location or linkedin.get("location", ""),
        "description": official.description or linkedin.get("description", ""),
        "posted_at": official.posted_at or linkedin.get("posted_at"),
        "apply_url": official.official_url,
        "source_url": source_url,
        "ats_provider": official.provider,
    }


class ExternalJobEnricher:
    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def enrich(self, url: str) -> Optional[EnrichedJobData]:
        if not self.is_supported_ats_url(url, resolve_dns=True):
            return None
        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=self.timeout_seconds,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
                    )
                },
            ) as client:
                current_url = url
                response = None
                for _ in range(6):
                    if not self.is_supported_ats_url(current_url, resolve_dns=True):
                        return None
                    response = client.get(current_url)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    break
                if response is None or response.is_redirect:
                    return None
        except (httpx.HTTPError, ValueError):
            return None

        final_url = str(response.url)
        if not self.is_supported_ats_url(final_url, resolve_dns=True):
            return None
        return self.parse_html(
            response.text,
            final_url=final_url,
            provider=detect_ats_provider(final_url),
        )

    @staticmethod
    def is_safe_public_url(url: str, resolve_dns: bool = False) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        hostname = parsed.hostname.lower().rstrip(".")
        if (
            hostname in {"localhost", "localhost.localdomain"}
            or hostname.endswith(".local")
            or hostname.endswith(".localhost")
            or "." not in hostname
        ):
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            if not resolve_dns:
                return True
            try:
                addresses = {
                    item[4][0]
                    for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
                }
            except socket.gaierror:
                return False
            return bool(addresses) and all(_is_public_ip(value) for value in addresses)
        return _is_public_ip(str(address))

    @staticmethod
    def is_supported_ats_url(url: str, resolve_dns: bool = False) -> bool:
        if not ExternalJobEnricher.is_safe_public_url(url, resolve_dns=resolve_dns):
            return False
        provider = detect_ats_provider(url)
        return provider != "company_site"

    @staticmethod
    def parse_html(html: str, final_url: str, provider: str) -> EnrichedJobData:
        soup = BeautifulSoup(html, "html.parser")
        posting = _find_job_posting(soup)
        if posting:
            title = _clean_text(str(posting.get("title", "")))
            company = _organization_name(posting.get("hiringOrganization"))
            location = _job_location(posting.get("jobLocation"))
            description = _clean_description(str(posting.get("description", "")))
            posted_at = _parse_datetime(posting.get("datePosted"))
            return EnrichedJobData(
                official_url=final_url,
                provider=provider,
                title=title[:255],
                company=company[:255],
                location=location[:255],
                description=description[:12000],
                posted_at=posted_at,
                structured=True,
            )

        title = _first_text(soup, ["h1", "[data-automation-id='jobPostingHeader']"])
        company = _meta_content(soup, "og:site_name")
        location = _first_text(
            soup,
            [
                "[itemprop='jobLocation']",
                "[data-automation-id='locations']",
                ".posting-categories .location",
                ".location",
            ],
        )
        description_node = _first_node(
            soup,
            [
                "[itemprop='description']",
                "[data-automation-id='jobPostingDescription']",
                ".show-more-less-html__markup",
                ".job-post",
                ".posting-page .content",
                "#content",
            ],
        )
        description = _clean_description(str(description_node) if description_node else "")
        if not description:
            description = _clean_description(_meta_content(soup, "og:description"))
        return EnrichedJobData(
            official_url=final_url,
            provider=provider,
            title=title[:255],
            company=company[:255],
            location=location[:255],
            description=description[:12000],
        )


def _find_job_posting(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json_objects(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "jobposting" for value in types):
                return item
    return None


def _walk_json_objects(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json_objects(child)


def _organization_name(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_text(str(value.get("name", "")))
    return _clean_text(str(value or ""))


def _job_location(value: Any) -> str:
    locations = value if isinstance(value, list) else [value]
    rendered = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address", location)
        if not isinstance(address, dict):
            continue
        country_value = address.get("addressCountry", "")
        if isinstance(country_value, dict):
            country_value = country_value.get("name", "")
        parts = [
            address.get("addressLocality", ""),
            address.get("addressRegion", ""),
            country_value,
        ]
        text = ", ".join(_clean_text(str(part)) for part in parts if _clean_text(str(part)))
        if text:
            rendered.append(text)
    return " / ".join(dict.fromkeys(rendered))


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _first_node(soup: BeautifulSoup, selectors: list[str]) -> Any:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return node
    return None


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    node = _first_node(soup, selectors)
    return _clean_text(node.get_text(" ", strip=True)) if node else ""


def _meta_content(soup: BeautifulSoup, property_name: str) -> str:
    node = soup.select_one(f"meta[property='{property_name}']")
    return _clean_text(str(node.get("content", ""))) if node else ""


def _clean_description(value: str) -> str:
    decoded = html_lib.unescape(value)
    text = BeautifulSoup(decoded, "html.parser").get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value)).strip()


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith(f".{suffix}")
