import email
import imaplib
import re
from email.message import Message
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, CollectorMeta
from app.core.config import get_settings
from app.schemas.job import UnifiedJob


class LinkedInEmailCollector(BaseCollector):
    meta = CollectorMeta(
        source_name="linkedin_email",
        source_type="email",
        collection_method="imap",
        polling_interval_minutes=15,
    )

    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_raw(self) -> List[Dict[str, Any]]:
        if not self.settings.linkedin_email_enabled:
            return []
        if not self.settings.linkedin_email_imap_host or not self.settings.linkedin_email_username:
            return []
        if not self.settings.linkedin_email_password:
            return []

        conn = imaplib.IMAP4_SSL(
            self.settings.linkedin_email_imap_host,
            self.settings.linkedin_email_imap_port,
        )
        try:
            conn.login(self.settings.linkedin_email_username, self.settings.linkedin_email_password)
            conn.select(self.settings.linkedin_email_folder)

            sender = self.settings.linkedin_email_sender_filter.replace('"', "").strip()
            status, data = conn.search(None, f'(FROM "{sender}")')
            if status != "OK" or not data or not data[0]:
                return []

            message_ids = data[0].split()
            # Process the newest messages first with a bounded window.
            selected_ids = message_ids[-self.settings.scheduler_linkedin_email_max_messages :]

            items: List[Dict[str, Any]] = []
            for msg_id in reversed(selected_ids):
                fetch_status, parts = conn.fetch(msg_id, "(RFC822)")
                if fetch_status != "OK" or not parts:
                    continue
                raw_email = parts[0][1]
                if not isinstance(raw_email, (bytes, bytearray)):
                    continue
                parsed = email.message_from_bytes(raw_email)
                item = self._extract_from_message(parsed)
                if item is not None:
                    items.append(item)
            return items
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn.logout()

    def normalize(self, raw: Dict[str, Any]) -> UnifiedJob:
        now = self.now()
        posted_at = raw.get("posted_at") or now
        job_id = raw["source_job_id"]
        content_hash = self.build_hash(job_id, raw["title"], raw["location"], raw["description"])

        return UnifiedJob(
            source=self.meta.source_name,
            source_job_id=job_id,
            company=raw["company"],
            title=raw["title"],
            location=raw["location"],
            country=raw.get("country"),
            description=raw["description"],
            apply_url=raw["apply_url"],
            source_url=raw["source_url"],
            posted_at=posted_at,
            updated_at=now,
            first_seen_at=now,
            last_seen_at=now,
            content_hash=content_hash,
            status="active",
        )

    def _extract_from_message(self, message: Message) -> Optional[Dict[str, Any]]:
        body = self._extract_body(message)
        if not body:
            return None

        links = self._extract_links(body)
        primary_link = self._choose_primary_link(links)
        if not primary_link:
            return None

        title = self._extract_title(message, body)
        company = self._extract_company(body)
        location = self._extract_location(body)
        description = self._extract_description(body, message.get("Subject", "LinkedIn Job Alert"))

        source_job_id = self._build_source_job_id(primary_link, title, company, location)
        posted_at = None
        date_header = message.get("Date")
        if date_header:
            try:
                posted_at = parsedate_to_datetime(date_header)
            except (TypeError, ValueError):
                posted_at = None

        return {
            "source_job_id": source_job_id,
            "company": company,
            "title": title,
            "location": location,
            "country": self._derive_country(location),
            "description": description,
            "apply_url": primary_link,
            "source_url": primary_link,
            "posted_at": posted_at,
        }

    def _extract_body(self, message: Message) -> str:
        if message.is_multipart():
            html_parts: List[str] = []
            text_parts: List[str] = []
            for part in message.walk():
                content_type = part.get_content_type()
                if content_type not in {"text/plain", "text/html"}:
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="ignore")
                if content_type == "text/html":
                    html_parts.append(decoded)
                else:
                    text_parts.append(decoded)
            if html_parts:
                soup = BeautifulSoup("\n".join(html_parts), "html.parser")
                return soup.get_text("\n", strip=True)
            return "\n".join(text_parts).strip()

        payload = message.get_payload(decode=True)
        if payload is None:
            return ""
        charset = message.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="ignore")
        if message.get_content_type() == "text/html":
            soup = BeautifulSoup(decoded, "html.parser")
            return soup.get_text("\n", strip=True)
        return decoded.strip()

    def _extract_links(self, body: str) -> List[str]:
        links = re.findall(r"https?://[^\s<>\"]+", body)
        cleaned = []
        for link in links:
            cleaned.append(link.rstrip(").,;"))
        # Keep order while removing duplicates.
        seen = set()
        deduped = []
        for link in cleaned:
            if link in seen:
                continue
            seen.add(link)
            deduped.append(link)
        return deduped

    def _choose_primary_link(self, links: List[str]) -> Optional[str]:
        for link in links:
            resolved = self._resolve_linkedin_redirect(link)
            parsed = urlparse(resolved)
            host = parsed.netloc.lower()
            if "linkedin.com" not in host:
                continue
            if "/jobs/view/" in parsed.path or "/jobs/collections/" in parsed.path or "/jobs/search/" in parsed.path:
                return resolved
        for link in links:
            resolved = self._resolve_linkedin_redirect(link)
            if "linkedin.com" in urlparse(resolved).netloc.lower():
                return resolved
        return None

    def _resolve_linkedin_redirect(self, link: str) -> str:
        parsed = urlparse(link)
        query = parse_qs(parsed.query)
        for key in ("url", "dest", "redirect", "redirect_url"):
            if key in query and query[key]:
                return unquote(query[key][0])
        return link

    def _extract_title(self, message: Message, body: str) -> str:
        subject = message.get("Subject", "").strip()
        patterns = [
            r"(?i)jobs for you[:,\-]?\s*(.+)$",
            r"(?i)new job alert[:,\-]?\s*(.+)$",
            r"(?i)(.+?)\s*\|\s*linkedin",
        ]
        for pattern in patterns:
            match = re.search(pattern, subject)
            if match:
                candidate = match.group(1).strip()
                if candidate:
                    return candidate[:255]
        # Fallback to first meaningful line in email body.
        for line in body.splitlines():
            line = line.strip()
            if len(line) < 8:
                continue
            if "linkedin" in line.lower():
                continue
            return line[:255]
        return "LinkedIn Job Opportunity"

    def _extract_company(self, body: str) -> str:
        patterns = [
            r"(?i)at\s+([A-Za-z0-9&\-\.,\s]{2,80})",
            r"(?i)company[:：]\s*([^\n]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                return match.group(1).strip()[:255]
        return "Unknown Company"

    def _extract_location(self, body: str) -> str:
        patterns = [
            r"(?i)location[:：]\s*([^\n]{2,80})",
            r"(?i)in\s+([A-Za-z\u4e00-\u9fff\-\s,]{2,80})",
        ]
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                value = match.group(1).strip()
                if len(value) >= 2:
                    return value[:255]
        return "Unknown"

    def _extract_description(self, body: str, subject: str) -> str:
        compact = re.sub(r"\s+", " ", body).strip()
        if compact:
            return compact[:2000]
        return subject[:500]

    def _build_source_job_id(self, apply_url: str, title: str, company: str, location: str) -> str:
        parsed = urlparse(apply_url)
        match = re.search(r"/jobs/view/(\d+)", parsed.path)
        if match:
            return match.group(1)
        fallback = f"{apply_url}|{title}|{company}|{location}"
        return sha256(fallback.encode("utf-8")).hexdigest()[:32]

    def _derive_country(self, location: str) -> str:
        lowered = location.lower()
        if any(item in lowered for item in ["hong kong", "香港"]):
            return "Hong Kong"
        if any(item in lowered for item in ["singapore", "新加坡"]):
            return "Singapore"
        if any(item in lowered for item in ["china", "中国", "shanghai", "上海"]):
            return "China"
        return "Unknown"
