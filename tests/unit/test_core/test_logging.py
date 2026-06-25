"""Structured logging tests."""

import logging

import pytest

from langops.core.config import get_settings
from langops.core.logging import configure_logging, get_logger


def test_configure_logging_and_get_logger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    get_settings.cache_clear()

    configure_logging()
    logger = get_logger("langops.test")

    assert logger is not None
    assert logging.getLogger().level == logging.WARNING
