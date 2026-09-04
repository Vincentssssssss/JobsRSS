import httpx

from app.official.collectors.amazon import parse_amazon_jobs
from app.official.collectors.google import discover_google_job_links, parse_google_job_detail
from app.official.collectors.microsoft import (
    _get_json_with_backoff,
    parse_microsoft_position,
)
from app.official.location import LocationCategory


def test_parses_amazon_search_json_and_keeps_multilocation_shanghai_role():
    payload = {
        "jobs": [
            {
                "id_icims": "10509781",
                "title": "Senior Security Solutions Architect",
                "company_name": "Amazon Web Services",
                "city": "Beijing",
                "normalized_location": "Beijing, China",
                "locations": '["Shanghai, China", "Beijing, China"]',
                "description": "Lead AWS cloud security architecture.",
                "basic_qualifications": "Cloud security and IAM experience.",
                "preferred_qualifications": "Security architecture leadership.",
                "job_path": "/en/jobs/10509781/security-architect",
                "posted_date": "August 20, 2026",
            }
        ]
    }

    jobs = parse_amazon_jobs(payload)

    assert len(jobs) == 1
    assert jobs[0]["source_job_id"] == "10509781"
    assert "Shanghai" in jobs[0]["location"]
    assert jobs[0]["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "IAM" in jobs[0]["description"]


def test_parses_microsoft_search_and_detail_payload():
    search_item = {
        "id": "1849213",
        "name": "Cloud Security Architect",
        "locations": ["Shanghai, Shanghai, CN"],
        "posted_ts": 1787184000,
        "positionUrl": "/careers/job/1849213",
    }
    detail = {
        "position": {
            "name": "Cloud Security Architect",
            "job_description": "Own Azure cloud security architecture and DevSecOps.",
            "qualifications": "IAM and application security experience.",
            "locations": ["Shanghai, Shanghai, CN"],
            "displayJobId": "MS-12345",
        }
    }

    job = parse_microsoft_position(search_item, detail)

    assert job["source_job_id"] == "1849213"
    assert job["company"] == "Microsoft"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value
    assert "qualifications" not in job
    assert "IAM" in job["description"]


def test_discovers_and_parses_google_ssr_job_page():
    listing = """
    <a href="/about/careers/applications/jobs/results/127276011858338502-security-architect">
      Security Architect
    </a>
    <a href="/about/careers/applications/jobs/results/">Search jobs</a>
    <script>
      AF_initDataCallback({data:"jobs/results/998877665544332211-cloud-security-lead"});
    </script>
    """
    detail = """
    <html>
      <head><meta property="og:title" content="Security Architect — Google Careers"></head>
      <body>
        <h1>Security Architect</h1>
        <div class="job-location">Shanghai, China</div>
        <div class="job-description">Own cloud and product security architecture.</div>
      </body>
    </html>
    """

    links = discover_google_job_links(listing)
    job = parse_google_job_detail(detail, links[0])

    assert links == [
        "https://www.google.com/about/careers/applications/jobs/results/"
        "127276011858338502-security-architect",
        "https://www.google.com/about/careers/applications/jobs/results/"
        "998877665544332211-cloud-security-lead",
    ]
    assert job["source_job_id"] == "127276011858338502"
    assert job["title"] == "Security Architect"
    assert job["location_category"] == LocationCategory.CONFIRMED_SHANGHAI.value


def test_microsoft_json_request_retries_rate_limit(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "0"})
        return httpx.Response(200, json={"positions": []})

    monkeypatch.setattr("app.official.collectors.microsoft.time.sleep", lambda _: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        payload = _get_json_with_backoff(
            client,
            "https://apply.careers.microsoft.com/api/pcsx/search",
            params={},
            retries=1,
        )

    assert payload == {"positions": []}
    assert calls == 2


def test_google_discovery_rejects_external_job_shaped_url():
    html = (
        '<a href="http://169.254.169.254/about/careers/applications/'
        'jobs/results/123456789012-security">metadata</a>'
    )

    assert discover_google_job_links(html) == []
