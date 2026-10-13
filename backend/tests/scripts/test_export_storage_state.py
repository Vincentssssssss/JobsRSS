import json
import sys

import pytest

from scripts.export_storage_state import filter_storage_state
import scripts.export_storage_state as export_storage_state


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


def test_main_interactive_mode_writes_filtered_state(monkeypatch, tmp_path):
    out_file = tmp_path / "linkedin_state.json"

    def fake_export_state_interactive(site: str, browser_channel: str, user_data_dir: str) -> dict:
        assert site == "linkedin"
        assert browser_channel == "chrome"
        assert user_data_dir
        return {
            "cookies": [{"name": "li_at", "domain": ".linkedin.com"}],
            "origins": [{"origin": "https://www.linkedin.com", "localStorage": []}],
        }

    monkeypatch.setattr(export_storage_state, "export_state_interactive", fake_export_state_interactive)
    monkeypatch.setattr(sys, "argv", [
        "export_storage_state.py",
        "--site",
        "linkedin",
        "--mode",
        "interactive",
        "--out",
        str(out_file),
    ])

    export_storage_state.main()

    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["cookies"][0]["name"] == "li_at"


def test_main_cdp_mode_shows_interactive_hint_on_context_error(monkeypatch, tmp_path):
    out_file = tmp_path / "linkedin_state.json"

    def fake_export_state_from_cdp(site: str, cdp_url: str) -> dict:
        raise Exception("Browser context management is not supported.")

    monkeypatch.setattr(export_storage_state, "export_state_from_cdp", fake_export_state_from_cdp)
    monkeypatch.setattr(sys, "argv", [
        "export_storage_state.py",
        "--site",
        "linkedin",
        "--out",
        str(out_file),
    ])

    with pytest.raises(SystemExit, match="--mode interactive"):
        export_storage_state.main()
