"""Custom exception tests."""

from langops.core.exceptions import (
    AnalysisError,
    CollectorError,
    ConfigurationError,
    LangOpsException,
    LLMError,
    VectorStoreError,
)


def test_collector_error_stores_source() -> None:
    err = CollectorError("query failed", source="prometheus")
    assert str(err) == "query failed"
    assert err.source == "prometheus"


def test_llm_error_stores_model() -> None:
    err = LLMError("timeout", model="gpt-4")
    assert str(err) == "timeout"
    assert err.model == "gpt-4"


def test_exception_hierarchy() -> None:
    assert issubclass(ConfigurationError, LangOpsException)
    assert issubclass(CollectorError, LangOpsException)
    assert issubclass(LLMError, LangOpsException)
    assert issubclass(VectorStoreError, LangOpsException)
    assert issubclass(AnalysisError, LangOpsException)
