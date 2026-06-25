"""Configuration management tests."""

import pytest

from langops.core.config import LLMSettings, Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "LangOps-Test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LLM_API_KEY", "sk-from-env")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-from-env")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-from-env")
    monkeypatch.setenv("PROMETHEUS_URL", "http://prom:9090")

    settings = Settings()

    assert settings.app_name == "LangOps-Test"
    assert settings.log_level == "DEBUG"
    assert settings.llm.model == "gpt-4o-mini"
    assert settings.llm.api_key == "sk-from-env"
    assert settings.prometheus.url == "http://prom:9090"


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-cache")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-cache")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-cache")

    first = get_settings()
    second = get_settings()

    assert first is second


def test_llm_settings_validates_temperature_bounds() -> None:
    with pytest.raises(ValueError):
        LLMSettings(api_key="sk-test", temperature=3.0)
