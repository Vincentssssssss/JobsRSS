import json
from datetime import datetime, timezone

from app.official.collectors.base import parse_source_datetime
from app.official.collectors.google import google_posted_at, parse_google_job_detail
from app.official.collectors.tencent import TencentOfficialCollector, parse_tencent_jobs

GOOGLE_URL = (
    "https://www.google.com/about/careers/applications/jobs/results/"
    "107942634529399494-partner-delivery-manager"
)


def _google_detail(job_id: str, create: int, update: int, publish: int) -> str:
    record = [job_id, "Partner Delivery Manager", "https://signin", [None, "<ul></ul>"],
              [None, ""], "projects/x", None, "Google", "en-US",
              [["Shanghai, China", ["Shanghai, China"], "Shanghai", None, "Shanghai", "CN"]],
              [None, "<p>About</p>"], [2, 3], [create, 608000000], [update, 608000000],
              [publish, 669000000], [None, ""], None, None, [None, ""], [None, ""], 3]
    return f"""
    <html>
      <head><meta property="og:title" content="Partner Delivery Manager — Google Careers"></head>
      <body>
        <h1>Partner Delivery Manager</h1>
        <div class="job-location">Shanghai, China</div>
        <div class="job-description">Deliver ads solutions.</div>
        <script>AF_initDataCallback({{key: 'ds:0', hash: '1', data:{json.dumps([record])}, sideChannel: {{}}}});</script>
      </body>
    </html>
    """


def test_chinese_portal_dates_are_parsed():
    expected = datetime(2026, 11, 5, tzinfo=timezone.utc)
    assert parse_source_datetime("2026年11月05日") == expected
    assert parse_source_datetime("2026/11/5") == expected
    assert parse_source_datetime("2026.11.05") == expected
    assert parse_source_datetime("2026-11-05") == expected
    assert parse_source_datetime("2026年13月05日") is None


def test_tencent_jobs_keep_their_update_date():
    payload = {"Data": {"Posts": [{
        "PostId": "2038814816268873728",
        "RecruitPostName": "云安全架构师",
        "LocationName": "上海",
        "Responsibility": "负责云安全架构。",
        "LastUpdateTime": "2026年11月05日",
    }]}}
    raw = parse_tencent_jobs(payload)[0]
    job = TencentOfficialCollector().normalize(raw)
    assert job.posted_at == datetime(2026, 11, 5, tzinfo=timezone.utc)


def test_google_posting_date_comes_from_the_embedded_job_record():
    # 2026-10-19 created, 2026-10-29 published again: the results page sorts by the latter.
    html = _google_detail("107942634529399494", 1792424400, 1793268540, 1793268540)
    job = parse_google_job_detail(html, GOOGLE_URL)
    assert job["posted_at"] == datetime.fromtimestamp(1793268540, tz=timezone.utc)


def test_google_record_of_another_job_is_ignored():
    html = _google_detail("999", 1792424400, 1793268540, 1793268540)
    assert google_posted_at(html, "107942634529399494") is None
    assert parse_google_job_detail(html, GOOGLE_URL)["posted_at"] is None


def test_google_page_without_a_job_record_has_no_date():
    assert google_posted_at("<html><script>var x = 1;</script></html>", "1") is None
    assert google_posted_at("AF_initDataCallback({key: 'ds:0', data:not json, sideChannel", "1") is None
