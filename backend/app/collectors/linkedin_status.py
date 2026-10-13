import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

# The first three are the exact strings LinkedIn's job page renders for a
# closed posting with en-US, zh-CN and zh-TW locales; the rest cover phrasings
# the logged-in UI or older layouts may use.
LINKEDIN_CLOSED_MARKERS = (
    "no longer accepting applications",
    "停止接受求职申请",
    "不再受理應徵",
    "job is no longer available",
    "不再接受求职申请",
    "不再接受申请",
    "停止接受申请",
    "不再受理应征",
)
_DESCRIPTION_SELECTORS = ", ".join(
    (
        ".show-more-less-html__markup",
        ".description__text",
        ".jobs-description-content__text",
        ".jobs-box__html-content",
        ".jobs-description__content",
        ".jobs-description",
        "#job-details",
    )
)
_NON_VISIBLE_TAGS = ["script", "style", "noscript", "template", "code"]
_JOB_VIEW_PATH = re.compile(r"/jobs/view/(?:[^/]*-)?(\d{6,})/?$")
_BARE_JOB_ID = re.compile(r"^\d{6,}$")
_THROTTLE_STATUSES = {429, 999}
_GONE_STATUSES = {404, 410}


class PostingState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    THROTTLED = "throttled"


@dataclass(frozen=True)
class PostingCheck:
    state: PostingState
    reason: str


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def find_linkedin_closed_marker(html: str) -> Optional[str]:
    """Return the "no longer accepting applications" style text a LinkedIn job
    page shows, ignoring the job description so a posting that merely quotes
    such a phrase is not treated as closed."""
    if not html:
        return None
    lowered = _squash(html).lower()
    if "closed-job" not in lowered and not any(
        marker in lowered for marker in LINKEDIN_CLOSED_MARKERS
    ):
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_NON_VISIBLE_TAGS):
        tag.decompose()
    for node in soup.select(_DESCRIPTION_SELECTORS):
        node.decompose()
    badge = soup.select_one(".closed-job")
    if badge is not None:
        return _squash(badge.get_text(" ", strip=True)) or "closed-job"
    text = _squash(soup.get_text(" ", strip=True)).lower()
    for marker in LINKEDIN_CLOSED_MARKERS:
        if marker in text:
            return marker
    return None


def linkedin_job_id(*candidates: Optional[str]) -> Optional[str]:
    for value in candidates:
        text = str(value or "").strip()
        if not text:
            continue
        if _BARE_JOB_ID.match(text):
            return text
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
        if host != "linkedin.com" and not host.endswith(".linkedin.com"):
            continue
        match = _JOB_VIEW_PATH.search(parsed.path)
        if match:
            return match.group(1)
        current = parse_qs(parsed.query).get("currentJobId", [])
        if current and _BARE_JOB_ID.match(current[0]):
            return current[0]
    return None


def classify_guest_job_response(
    status_code: int, body: str, *, trust_not_found: bool = True
) -> PostingCheck:
    """Interpret a response from LinkedIn's anonymous jobPosting endpoint.

    Only a closed marker or a 404/410 counts as closed. Throttling (429, and
    LinkedIn's 999), redirects to the auth wall and pages without a job top
    card are never treated as evidence either way."""
    if status_code in _THROTTLE_STATUSES:
        return PostingCheck(PostingState.THROTTLED, f"http_{status_code}")
    if status_code in _GONE_STATUSES:
        if trust_not_found:
            return PostingCheck(PostingState.CLOSED, f"http_{status_code}")
        return PostingCheck(PostingState.UNKNOWN, f"http_{status_code}_recently_seen")
    if status_code != 200:
        return PostingCheck(PostingState.UNKNOWN, f"http_{status_code}")
    marker = find_linkedin_closed_marker(body)
    if marker:
        return PostingCheck(PostingState.CLOSED, f"marker:{marker}")
    if "top-card-layout__title" in body:
        return PostingCheck(PostingState.OPEN, "top_card")
    return PostingCheck(PostingState.UNKNOWN, "unrecognized_page")
