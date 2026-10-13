from types import SimpleNamespace

from app.notifications.daily_digest import DigestSummary, render_digest_html


def test_digest_escapes_job_and_source_values():
    job = SimpleNamespace(
        company="<script>alert(1)</script>",
        title="Cloud & Security",
        location='"Shanghai"',
        match_score=80,
        apply_url="https://jobs.example.com/?q='bad'",
    )
    summary = DigestSummary(
        total_new=1,
        high_match=1,
        by_source={"<linkedin>": 1},
        jobs=[job],
    )

    rendered = render_digest_html(summary)

    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;linkedin&gt;" in rendered
    assert "Cloud &amp; Security" in rendered
    assert "&#x27;bad&#x27;" in rendered
