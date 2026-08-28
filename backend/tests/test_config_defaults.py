from app.core.config import Settings


def test_official_sources_enabled_by_default_for_v2(monkeypatch):
    monkeypatch.delenv("OFFICIAL_SOURCES_ENABLED", raising=False)
    monkeypatch.delenv("LLM_REJECT_EARLY_CAREER", raising=False)

    settings = Settings(_env_file=None)

    assert settings.official_sources_enabled is True
    assert settings.llm_reject_early_career is True
