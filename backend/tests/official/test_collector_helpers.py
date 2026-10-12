import json

import httpx

from app.official.collectors.base import interleave_capped
from app.official.collectors.phenom import fetch_phenom_listing, phenom_multi_location


def test_interleave_takes_alternately_until_cap():
    shanghai = [f"sh{i}" for i in range(10)]
    malaysia = ["my0", "my1"]

    merged = interleave_capped([shanghai, malaysia], 6, key=lambda item: item)

    assert merged == ["sh0", "my0", "sh1", "my1", "sh2", "sh3"]


def test_interleave_drops_repeats_across_locations():
    merged = interleave_capped([["a", "b"], ["a", "c"]], 10, key=lambda item: item)

    assert merged == ["a", "c", "b"]


def test_interleave_returns_everything_under_cap():
    assert interleave_capped([[1, 2], [], [3]], 150, key=lambda item: item) == [1, 3, 2]


def test_phenom_listing_pages_with_from_offset_until_total_hits():
    offsets = []

    def handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        offsets.append(data["from"])
        assert data["size"] == 50
        assert data["selected_fields"] == {"country": ["Malaysia"]}
        start = data["from"]
        count = max(0, min(50, 65 - start))
        jobs = [{"jobSeqNo": f"J{start + i}"} for i in range(count)]
        return httpx.Response(
            200,
            json={"refineSearch": {"totalHits": 65, "data": {"jobs": jobs}}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = fetch_phenom_listing(
            client,
            "https://careers.example.com/widgets",
            {"lang": "en_global"},
            {"country": ["Malaysia"]},
            limit=150,
            max_pages=20,
        )

    assert offsets == [0, 50]
    assert len(jobs) == 65


def test_phenom_listing_stops_at_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        jobs = [{"jobSeqNo": str(i)} for i in range(50)]
        return httpx.Response(
            200,
            json={"refineSearch": {"totalHits": 500, "data": {"jobs": jobs}}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = fetch_phenom_listing(
            client,
            "https://careers.example.com/widgets",
            {},
            {},
            limit=120,
            max_pages=20,
        )

    assert len(jobs) == 120


def test_phenom_multi_location_joins_every_site():
    listing = {
        "location": "Jakarta, Indonesia",
        "multi_location": ["Jakarta, Indonesia", "Kuala Lumpur, Malaysia", ""],
    }

    assert phenom_multi_location(listing) == "Jakarta, Indonesia / Kuala Lumpur, Malaysia"
    assert phenom_multi_location({"location": "Shanghai"}) == ""
