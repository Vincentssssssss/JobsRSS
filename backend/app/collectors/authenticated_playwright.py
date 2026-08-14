import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector
from app.core.config import get_settings
from app.schemas.job import UnifiedJob


class AuthenticatedPlaywrightCollector(BaseCollector):
    """Shared collector for account-based browser collection.

    This class favors an existing storage-state session file for reliability.
    Username/password login is optional and implemented only for collectors
    where selectors are known and stable.
    """

    base_domain: str = ""

    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_raw(self) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []
        search_urls = self.get_search_urls()
        if not search_urls:
            return []

        from playwright.sync_api import sync_playwright

        results: List[Dict[str, Any]] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
            context_args: Dict[str, Any] = {}
            state_path = self.get_storage_state_path()
            if state_path:
                context_args["storage_state"] = state_path
            context = browser.new_context(ignore_https_errors=True, **context_args)
            page = context.new_page()

            if not state_path:
                self.perform_login(page)

            for search_url in search_urls:
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    html = page.content()
                    results.extend(self.extract_jobs_from_html(html, search_url))
                except Exception:
                    continue

            context.close()
            browser.close()
        return results

    def normalize(self, raw: Dict[str, Any]) -> UnifiedJob:
        now = self.now()
        posted_at = raw.get("posted_at")
        if isinstance(posted_at, str):
            try:
                posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            except ValueError:
                posted_at = None
        if posted_at is None:
            posted_at = now
        return UnifiedJob(
            source=self.meta.source_name,
            source_job_id=raw["source_job_id"],
            company=raw.get("company", "Unknown Company"),
            title=raw["title"],
            location=raw.get("location", "Unknown"),
            country=raw.get("country"),
            description=raw.get("description", ""),
            apply_url=raw["apply_url"],
            source_url=raw["source_url"],
            posted_at=posted_at,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=raw["content_hash"],
            status="active",
        )

    def is_enabled(self) -> bool:
        raise NotImplementedError

    def get_search_urls(self) -> List[str]:
        raise NotImplementedError

    def get_storage_state_path(self) -> Optional[str]:
        return None

    def perform_login(self, page: Any) -> None:
        # Optional override per source.
        return None

    def extract_jobs_from_html(self, html: str, source_url: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        cards: List[Dict[str, Any]] = []
        anchors = soup.select("a[href]")

        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(source_url, href)
            if not self.is_job_url(full_url):
                continue

            title = self.clean_text(anchor.get_text(" ", strip=True))
            if len(title) < 4:
                continue

            block_text = self.clean_text(anchor.parent.get_text(" ", strip=True)) if anchor.parent else title
            company = self.extract_company(block_text)
            location = self.extract_location(block_text)
            posted_at = self.extract_posted_at(block_text)
            source_job_id = self.extract_source_job_id(full_url, title, company, location)

            cards.append(
                {
                    "source_job_id": source_job_id,
                    "title": title[:255],
                    "company": company[:255],
                    "location": location[:255],
                    "country": self.derive_country(location),
                    "description": block_text[:2000],
                    "apply_url": full_url,
                    "source_url": full_url,
                    "posted_at": posted_at,
                    "content_hash": self.build_hash(source_job_id, title, company, location, block_text),
                }
            )

        # Keep deterministic top N after dedupe by source job id.
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in cards:
            deduped[item["source_job_id"]] = item
        return list(deduped.values())[:120]

    def is_job_url(self, url: str) -> bool:
        lowered = url.lower()
        return "job" in lowered or "career" in lowered or "position" in lowered

    def extract_source_job_id(self, url: str, title: str, company: str, location: str) -> str:
        match = re.search(r"(\d{5,})", url)
        if match:
            return match.group(1)
        raw = f"{self.meta.source_name}|{url}|{title}|{company}|{location}"
        return sha256(raw.encode("utf-8")).hexdigest()[:32]

    def extract_company(self, text: str) -> str:
        separators = ["·", "|", "-", "/", " at "]
        for sep in separators:
            parts = [part.strip() for part in text.split(sep) if part.strip()]
            if len(parts) >= 2:
                # Often title first, company second.
                candidate = parts[1]
                if 2 <= len(candidate) <= 80:
                    return candidate
        return "Unknown Company"

    def extract_location(self, text: str) -> str:
        common = [
            "Hong Kong",
            "Singapore",
            "Shanghai",
            "Beijing",
            "Shenzhen",
            "Guangzhou",
            "香港",
            "新加坡",
            "上海",
            "北京",
            "深圳",
            "广州",
            "Remote",
            "APAC",
        ]
        lowered = text.lower()
        for item in common:
            if item.lower() in lowered:
                return item
        return "Unknown"

    def derive_country(self, location: str) -> str:
        lowered = location.lower()
        if "hong kong" in lowered or "香港" in lowered:
            return "Hong Kong"
        if "singapore" in lowered or "新加坡" in lowered:
            return "Singapore"
        if any(s in lowered for s in ["shanghai", "beijing", "shenzhen", "guangzhou", "china", "上海", "北京", "深圳", "广州", "中国"]):
            return "China"
        if "apac" in lowered:
            return "APAC"
        return "Unknown"

    def clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def extract_posted_at(self, text: str) -> Optional[str]:
        lowered = text.lower()
        now = datetime.now(timezone.utc)
        patterns = [
            (r"(\d+)\s*(minutes?|mins?|分钟)\s*ago", "minutes"),
            (r"(\d+)\s*(hours?|hrs?|小时)\s*ago", "hours"),
            (r"(\d+)\s*(days?|天)\s*ago", "days"),
            (r"(\d+)\s*(weeks?|周)\s*ago", "weeks"),
            (r"(\d+)\s*(个月)\s*前", "months"),
            (r"(\d+)\s*(天)\s*前", "days"),
            (r"(\d+)\s*(小时)\s*前", "hours"),
            (r"(\d+)\s*(分钟)\s*前", "minutes"),
        ]
        if "just now" in lowered or "刚刚" in text:
            return now.isoformat()
        if "today" in lowered or "今天" in text:
            return now.isoformat()

        for pattern, unit in patterns:
            match = re.search(pattern, lowered if "ago" in pattern else text)
            if not match:
                continue
            value = int(match.group(1))
            if unit == "minutes":
                ts = now - timedelta(minutes=value)
            elif unit == "hours":
                ts = now - timedelta(hours=value)
            elif unit == "days":
                ts = now - timedelta(days=value)
            elif unit == "weeks":
                ts = now - timedelta(weeks=value)
            elif unit == "months":
                ts = now - timedelta(days=value * 30)
            else:
                continue
            return ts.isoformat()
        return None
