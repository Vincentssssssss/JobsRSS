from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import Base
from app.models.job import Job
from app.verification.linkedin import verify_linkedin_postings

NOW = datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc)

OPEN_PAGE = (
    '<section class="top-card-layout"><h2 class="top-card-layout__title">Security Manager</h2>'
    '<button class="apply-button">Apply</button></section>'
)
CLOSED_PAGE = (
    '<section class="top-card-layout"><h2 class="top-card-layout__title">Security Manager</h2>'
    '<figure class="closed-job closed-job__flavor"><figcaption class="closed-job__flavor--closed">'
    "No longer accepting applications</figcaption></figure></section>"
)


def _settings(**overrides) -> Settings:
    values = {
        "linkedin_verify_enabled": True,
        "linkedin_verify_max_per_run": 20,
        "linkedin_verify_recheck_hours": 24,
        "linkedin_verify_delay_seconds": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _job(job_id: str, **overrides) -> Job:
    values = dict(
        source="linkedin_auth",
        source_job_id=job_id,
        company="Acme",
        title="Security Manager",
        location="Hong Kong",
        country="Hong Kong",
        description="Lead cloud security.",
        apply_url=f"https://www.linkedin.com/jobs/view/{job_id}/",
        source_url=f"https://www.linkedin.com/jobs/view/{job_id}/",
        posted_at=NOW - timedelta(days=5),
        updated_at=NOW - timedelta(days=5),
        first_seen_at=NOW - timedelta(days=5),
        last_seen_at=NOW - timedelta(days=3),
        content_hash=job_id,
        match_score=70,
        status="active",
    )
    values.update(overrides)
    return Job(**values)


def _client(responses: dict, requested: list) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        job_id = request.url.path.rstrip("/").split("/")[-1]
        requested.append((job_id, request))
        outcome = responses[job_id]
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome
        return httpx.Response(status, text=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _state(db: Session) -> dict:
    db.expire_all()
    return {
        job.source_job_id: (job.status, job.last_verified_at is not None)
        for job in db.query(Job).all()
    }


def test_closed_marker_and_removed_posting_close_rows_and_open_rows_stay(db):
    db.add_all([_job("4100000001"), _job("4100000002"), _job("4100000003")])
    db.commit()
    requested = []
    client = _client(
        {
            "4100000001": (200, CLOSED_PAGE),
            "4100000002": (404, ""),
            "4100000003": (200, OPEN_PAGE),
        },
        requested,
    )

    stats = verify_linkedin_postings(db, settings=_settings(), client=client, now=NOW)

    assert (stats.checked, stats.closed, stats.open) == (3, 2, 1)
    assert _state(db) == {
        "4100000001": ("closed", True),
        "4100000002": ("closed", True),
        "4100000003": ("active", True),
    }


def test_not_found_for_a_posting_seen_today_does_not_close_it(db):
    db.add(_job("4100000004", last_seen_at=NOW - timedelta(hours=2)))
    db.commit()
    client = _client({"4100000004": (404, "")}, [])

    stats = verify_linkedin_postings(db, settings=_settings(), client=client, now=NOW)

    assert stats.inconclusive == 1
    assert _state(db) == {"4100000004": ("active", True)}


@pytest.mark.parametrize("status", [429, 999])
def test_throttling_stops_the_run_without_touching_rows(db, status):
    db.add_all([_job("4100000005"), _job("4100000006")])
    db.commit()
    requested = []
    client = _client(
        {"4100000005": (status, CLOSED_PAGE), "4100000006": (200, CLOSED_PAGE)},
        requested,
    )

    stats = verify_linkedin_postings(db, settings=_settings(), client=client, now=NOW)

    assert stats.throttled is True
    assert len(requested) == 1
    assert _state(db) == {
        "4100000005": ("active", False),
        "4100000006": ("active", False),
    }


@pytest.mark.parametrize(
    "outcome",
    [
        (302, ""),
        (403, ""),
        (500, ""),
        (200, "<html><body>Sign in to view this job</body></html>"),
    ],
)
def test_ambiguous_responses_never_close(db, outcome):
    db.add(_job("4100000007"))
    db.commit()
    client = _client({"4100000007": outcome}, [])

    stats = verify_linkedin_postings(db, settings=_settings(), client=client, now=NOW)

    assert stats.inconclusive == 1
    assert _state(db) == {"4100000007": ("active", True)}


def test_network_errors_leave_rows_unverified_and_abort_after_three(db):
    ids = [f"41000001{i:02d}" for i in range(5)]
    db.add_all([_job(job_id) for job_id in ids])
    db.commit()
    requested = []
    client = _client(
        {job_id: httpx.ReadTimeout("timed out") for job_id in ids},
        requested,
    )

    stats = verify_linkedin_postings(db, settings=_settings(), client=client, now=NOW)

    assert stats.errors == 3
    assert len(requested) == 3
    assert all(state == ("active", False) for state in _state(db).values())


def test_dashboard_rows_and_unverified_rows_are_checked_first_within_the_cap(db):
    db.add_all(
        [
            _job("4200000001", llm_verdict="not_fit", llm_fit_score=20),
            _job(
                "4200000002",
                llm_verdict="strong_fit",
                llm_fit_score=93,
                last_verified_at=NOW - timedelta(hours=30),
            ),
            _job("4200000003", llm_verdict="possible_fit", llm_fit_score=65),
            _job(
                "4200000004",
                llm_verdict="strong_fit",
                llm_fit_score=90,
                last_verified_at=NOW - timedelta(hours=2),
            ),
            _job("4200000005", llm_verdict="strong_fit", llm_fit_score=90, status="closed"),
            _job(
                "4200000006",
                source="official_microsoft",
                source_url="https://www.linkedin.com/jobs/view/4200000006/",
            ),
        ]
    )
    db.commit()
    requested = []
    client = _client({f"420000000{i}": (200, OPEN_PAGE) for i in range(1, 7)}, requested)

    verify_linkedin_postings(
        db,
        settings=_settings(linkedin_verify_max_per_run=2),
        client=client,
        now=NOW,
    )

    assert [job_id for job_id, _ in requested] == ["4200000003", "4200000002"]


def test_requests_are_anonymous_and_spaced_out(db):
    db.add_all([_job("4300000001"), _job("4300000002"), _job("4300000003")])
    db.commit()
    requested = []
    client = _client({f"430000000{i}": (200, OPEN_PAGE) for i in range(1, 4)}, requested)
    sleeps = []

    verify_linkedin_postings(
        db,
        settings=_settings(linkedin_verify_delay_seconds=4),
        client=client,
        sleep=sleeps.append,
        now=NOW,
    )

    assert len(sleeps) == 2
    assert all(4 <= seconds <= 6 for seconds in sleeps)
    for _, request in requested:
        assert "cookie" not in request.headers
        assert str(request.url).startswith("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/")


def test_rows_without_a_linkedin_job_id_are_skipped_without_a_request(db):
    db.add(
        _job(
            "0123abcd" * 4,
            source="linkedin_email",
            source_url="https://www.linkedin.com/jobs/search/?keywords=security",
            apply_url="https://www.linkedin.com/jobs/search/?keywords=security",
        )
    )
    db.commit()
    requested = []

    stats = verify_linkedin_postings(
        db, settings=_settings(), client=_client({}, requested), now=NOW
    )

    assert stats.skipped == 1
    assert requested == []


def test_disabled_verification_sends_nothing(db):
    db.add(_job("4400000001"))
    db.commit()
    requested = []

    verify_linkedin_postings(
        db,
        settings=_settings(linkedin_verify_enabled=False),
        client=_client({"4400000001": (200, CLOSED_PAGE)}, requested),
        now=NOW,
    )

    assert requested == []
    assert _state(db) == {"4400000001": ("active", False)}
