from typing import Any, Dict, List

import httpx

PHENOM_PAGE_SIZE = 50


def fetch_phenom_listing(
    client: httpx.Client,
    widgets_url: str,
    base_payload: Dict[str, Any],
    selected_fields: Dict[str, List[str]],
    *,
    limit: int,
    max_pages: int,
) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    for page in range(max_pages):
        if len(jobs) >= limit:
            break
        response = client.post(
            widgets_url,
            json={
                **base_payload,
                "size": PHENOM_PAGE_SIZE,
                "from": page * PHENOM_PAGE_SIZE,
                "jobs": True,
                "counts": True,
                "selected_fields": selected_fields,
                "sort": {"field": "postedDate", "order": "desc"},
                "ddoKey": "refineSearch",
            },
        )
        response.raise_for_status()
        refine = response.json().get("refineSearch", {})
        batch = refine.get("data", {}).get("jobs", []) or []
        jobs.extend(batch)
        total = refine.get("totalHits")
        if len(batch) < PHENOM_PAGE_SIZE or (isinstance(total, int) and len(jobs) >= total):
            break
    return jobs[:limit]


def phenom_job_key(listing: Dict[str, Any]) -> str:
    return str(listing.get("jobSeqNo") or listing.get("jobId") or "")


def phenom_multi_location(listing: Dict[str, Any]) -> str:
    """Every location of a multi-site posting; the primary ``location`` alone can
    name a non-target city even when the search matched Shanghai or Kuala Lumpur."""
    values = listing.get("multi_location")
    if not isinstance(values, list):
        return ""
    labels = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    return " / ".join(dict.fromkeys(labels))
