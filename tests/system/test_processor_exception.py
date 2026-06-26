"""Processor exception handling system tests.

Validates that when the AlertProcessor (LLM / collectors) raises exceptions,
the API returns a graceful error response instead of crashing with 500.
"""

import pytest
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from langops.agent.alert_processor import AlertProcessor
from langops.models import AnalysisResult, RootCause, RemediationSuggestion
from langops.services import AlertNoiseReducer, RemediationRegistry
from langops.services.jira_integration import JiraService
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.main import app

from tests.system.conftest import create_sqlite_session


def _make_failing_processor(error_msg: str = "LLM API timeout") -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(side_effect=RuntimeError(error_msg))
    return processor


def _make_working_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-recovery-test",
            trace_id="trace-recovery-test",
            root_cause=RootCause(
                category="资源不足", description="Test", confidence=0.9, evidence=["test"],
            ),
            similar_cases=[],
            suggestion=RemediationSuggestion(
                summary="Test", steps=[], commands=[], risks=[],
            ),
            processing_time_seconds=1.0,
        )
    )
    return processor


def _setup_all_overrides(processor) -> None:
    """Override ALL dependencies so storage/langfuse init don't cause 500."""
    sf = create_sqlite_session()
    dedup_repo = SqlDedupRepository(sf)
    remediation_repo = SqlRemediationRepository(sf)
    dedup = AlertNoiseReducer(repo=dedup_repo, window_seconds=900, enabled=True)
    remediation_registry = RemediationRegistry(repo=remediation_repo)
    jira = MagicMock(spec=JiraService)
    jira.create_ticket = AsyncMock(return_value=None)

    app.dependency_overrides[get_alert_processor] = lambda: processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    app.dependency_overrides[get_jira_service] = lambda: jira


class TestProcessorRaisesException:
    """When processor.process() raises, API should return success=False with error string."""

    @pytest.fixture
    def client_with_failing_processor(self) -> Generator[TestClient, None, None]:
        _setup_all_overrides(_make_failing_processor())
        try:
            yield TestClient(app, raise_server_exceptions=False)
        finally:
            app.dependency_overrides.clear()

    def test_llm_timeout_returns_error_response(
        self, client_with_failing_processor: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client_with_failing_processor.post("/api/v1/alerts", json=k8s_alert_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["data"] is None
        assert body["error"] is not None
        assert "timeout" in body["error"].lower()

    def test_exception_does_not_return_500(
        self, client_with_failing_processor: TestClient, k8s_alert_payload: dict
    ) -> None:
        """The API must never return 500 from processor exceptions — always 200 with error field."""
        response = client_with_failing_processor.post("/api/v1/alerts", json=k8s_alert_payload)
        assert response.status_code == 200

    def test_error_field_is_string_not_structured(
        self, client_with_failing_processor: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client_with_failing_processor.post("/api/v1/alerts", json=k8s_alert_payload)
        body = response.json()
        assert isinstance(body["error"], str)


class TestProcessorRaisesVariousExceptions:
    """Different exception types all produce graceful error responses."""

    @pytest.fixture(params=["value_error", "connection_error", "generic_exception"])
    def client_with_param_exception(self, request: pytest.FixtureRequest) -> Generator[TestClient, None, None]:
        if request.param == "value_error":
            exc = ValueError("Invalid model response format")
        elif request.param == "connection_error":
            exc = ConnectionError("Cannot reach LLM endpoint")
        else:
            exc = RuntimeError("Unexpected internal error")

        _setup_all_overrides(_make_failing_processor(str(exc)))
        try:
            yield TestClient(app, raise_server_exceptions=False)
        finally:
            app.dependency_overrides.clear()

    def test_various_exceptions_return_200_with_error(
        self, client_with_param_exception: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client_with_param_exception.post("/api/v1/alerts", json=k8s_alert_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"] is not None


class TestProcessorRecovery:
    """After a failed alert, subsequent alerts should still work.
    NOTE: Because dedup is enabled, sending the SAME payload will be suppressed.
    We use different titles to get different fingerprints.
    """

    def test_next_alert_succeeds_after_previous_failure(
        self,
        client: TestClient,
        k8s_alert_payload: dict,
    ) -> None:
        # First alert: swap to failing processor
        failing = _make_failing_processor("LLM down")
        app.dependency_overrides[get_alert_processor] = lambda: failing

        resp1 = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert resp1.json()["success"] is False

        # Restore working processor
        working = _make_working_processor()
        app.dependency_overrides[get_alert_processor] = lambda: working

        # Second alert: different title → different fingerprint → not suppressed
        second_payload = {**k8s_alert_payload, "title": "Memory usage high - recovery test"}
        resp2 = client.post("/api/v1/alerts", json=second_payload)
        assert resp2.json()["success"] is True
        assert resp2.json()["data"] is not None
