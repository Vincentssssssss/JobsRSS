import json
from pathlib import Path

from app.api.routes.health import healthz
from app.core.config import APP_VERSION, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_healthz_reports_the_code_version_even_with_a_stale_env_value(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "2.1.0")
    get_settings.cache_clear()
    try:
        get_settings()
        assert healthz() == {"status": "ok", "version": APP_VERSION}
    finally:
        get_settings.cache_clear()


def test_frontend_and_backend_versions_match():
    package = json.loads((REPO_ROOT / "frontend" / "package.json").read_text())
    lock = json.loads((REPO_ROOT / "frontend" / "package-lock.json").read_text())

    assert package["version"] == APP_VERSION
    assert lock["version"] == APP_VERSION
    assert lock["packages"][""]["version"] == APP_VERSION
