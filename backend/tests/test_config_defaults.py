from app.core.config import Settings


def test_official_sources_enabled_by_default_for_v2(monkeypatch):
    monkeypatch.delenv("OFFICIAL_SOURCES_ENABLED", raising=False)
    monkeypatch.delenv("LLM_REJECT_EARLY_CAREER", raising=False)
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("LINKEDIN_ALLOWED_LOCATIONS", raising=False)
    monkeypatch.delenv("LLM_TARGET_PROFILE", raising=False)

    settings = Settings(_env_file=None)

    assert settings.official_sources_enabled is True
    assert settings.llm_reject_early_career is True
    assert "http://localhost:3000" in settings.allowed_origins
    assert "http://127.0.0.1:3000" in settings.allowed_origins
    assert "Jiangsu" in settings.linkedin_allowed_locations
    assert "Zhejiang" in settings.linkedin_allowed_locations
    assert "Hong Kong" in settings.llm_target_profile


def test_allowed_origins_accepts_csv_value(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_allowed_origins_accepts_json_array(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        '["http://localhost:3000", "http://127.0.0.1:3000"]',
    )
    settings = Settings(_env_file=None)
    assert settings.allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
