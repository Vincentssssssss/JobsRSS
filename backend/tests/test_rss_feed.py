from datetime import datetime, timezone

from app.api.routes.rss import _build_feed, _rss_response
from app.models.job import Job


def _make_job() -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        source="official_ct_tianqing",
        source_job_id="J16056",
        company="正大天晴",
        title="KA经理（上海）",
        location="上海",
        country="China",
        description="岗位职责：客户拜访与药品进院。",
        apply_url="https://example.com/jobs/J16056",
        source_url="https://example.com/jobs/J16056",
        posted_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
        content_hash="hash-rss",
        match_score=0,
        status="active",
        location_category="confirmed_shanghai",
    )


def test_build_feed_contains_utf8_xml_declaration_and_chinese_text():
    xml = _build_feed("all", [_make_job()])

    assert "<?xml version='1.0' encoding='UTF-8'?>" in xml
    assert "正大天晴 - KA经理（上海） (上海)" in xml
    assert "岗位职责：客户拜访与药品进院。" in xml


def test_rss_response_sets_utf8_charset_header():
    response = _rss_response("<rss></rss>")

    assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
