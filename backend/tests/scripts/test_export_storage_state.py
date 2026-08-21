from scripts.export_storage_state import filter_storage_state


def test_filters_storage_state_to_requested_site_domain():
    state = {
        "cookies": [
            {"name": "liepin-session", "domain": ".liepin.com"},
            {"name": "linkedin-session", "domain": ".linkedin.com"},
            {"name": "evil", "domain": "liepin.com.attacker.example"},
        ],
        "origins": [
            {"origin": "https://www.liepin.com", "localStorage": []},
            {"origin": "https://www.linkedin.com", "localStorage": []},
        ],
    }

    filtered = filter_storage_state(state, ("liepin.com",))

    assert [cookie["name"] for cookie in filtered["cookies"]] == ["liepin-session"]
    assert [origin["origin"] for origin in filtered["origins"]] == ["https://www.liepin.com"]
