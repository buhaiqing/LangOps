"""Tests for persist_alert_and_result — verifies best-effort persistence."""

from unittest.mock import AsyncMock, patch

import pytest

from langops.models import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertSource,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)
from langops.storage.sql import SqlStorage


@pytest.fixture
async def storage():
    s = SqlStorage("sqlite://")
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def alert():
    return Alert(
        id="alert-test-001",
        title="CPU过高",
        description="Pod CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(type="kubernetes", system="prod", namespace="ns1", pod_name="pod1"),
    )


@pytest.fixture
def result():
    return AnalysisResult(
        alert_id="alert-test-001",
        trace_id="trace-abc",
        root_cause=RootCause(category="资源不足", description="CPU limit过低", confidence=0.9),
        suggestion=RemediationSuggestion(summary="扩容", commands=["kubectl scale ..."]),
        similar_cases=[],
        impact_prediction={"risk": "high"},
        processing_time_seconds=2.5,
    )


@pytest.mark.asyncio
async def test_persist_alert_and_result_succeeds(storage, alert, result):
    """Verify that alert and analysis are persisted to the database."""
    from langops.web.dependencies import persist_alert_and_result

    with patch("langops.web.dependencies.get_storage", return_value=storage):
        await persist_alert_and_result(alert, result)

    # Verify alert was persisted
    stored_alert = await storage.alerts.get("alert-test-001")
    assert stored_alert is not None
    assert stored_alert["title"] == "CPU过高"
    assert stored_alert["severity"] == "critical"

    # Verify analysis was persisted
    stored_analysis = await storage.analyses.get_by_alert("alert-test-001")
    assert stored_analysis is not None
    assert stored_analysis["trace_id"] == "trace-abc"
    assert stored_analysis["root_cause"]["category"] == "资源不足"
    assert stored_analysis["processing_time"] == 2.5


@pytest.mark.asyncio
async def test_persist_alert_and_result_survives_storage_error():
    """Verify that storage errors are caught and logged, not raised."""
    from langops.web.dependencies import persist_alert_and_result

    mock_storage = AsyncMock()
    mock_storage.alerts.save.side_effect = RuntimeError("DB connection lost")

    alert = Alert(
        id="alert-fail",
        title="test",
        description="d",
        severity=AlertSeverity.LOW,
        category=AlertCategory.RESOURCE,
        source=AlertSource(type="k8s", system="s"),
    )
    result = AnalysisResult(
        alert_id="alert-fail",
        trace_id="trace-fail",
        root_cause=RootCause(category="x", description="y", confidence=0.5),
        suggestion=RemediationSuggestion(summary="s"),
        processing_time_seconds=1.0,
    )

    with patch("langops.web.dependencies.get_storage", return_value=mock_storage):
        # Should NOT raise — best-effort persistence
        await persist_alert_and_result(alert, result)

    # If we got here, the exception was properly caught
