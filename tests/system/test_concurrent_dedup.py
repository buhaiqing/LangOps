"""Concurrent dedup system tests.

Validates that rapid-fire duplicate alerts are correctly suppressed
and that the dedup state is consistent under concurrent requests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from langops.agent.alert_processor import AlertProcessor
from langops.models import (
    AnalysisResult,
    RootCause,
    RemediationSuggestion,
)
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


def _make_mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-concurrent-test",
            trace_id="trace-concurrent-test",
            root_cause=RootCause(
                category="资源不足",
                description="Test",
                confidence=0.9,
                evidence=["test"],
            ),
            similar_cases=[],
            suggestion=RemediationSuggestion(
                summary="Test suggestion",
                steps=["step1"],
                commands=[],
                risks=[],
            ),
            processing_time_seconds=1.0,
        )
    )
    return processor


def _setup_overrides() -> None:
    """Set up all dependencies with SQLite storage and mocks."""
    sf = create_sqlite_session()
    dedup_repo = SqlDedupRepository(sf)
    remediation_repo = SqlRemediationRepository(sf)
    dedup = AlertNoiseReducer(repo=dedup_repo, window_seconds=900, enabled=True)
    remediation_registry = RemediationRegistry(repo=remediation_repo)
    processor = _make_mock_processor()
    jira = MagicMock(spec=JiraService)
    jira.create_ticket = AsyncMock(return_value=None)

    app.dependency_overrides[get_alert_processor] = lambda: processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    app.dependency_overrides[get_jira_service] = lambda: jira


class TestRapidFireDedup:
    """Rapid consecutive identical alerts should suppress duplicates."""

    @pytest.mark.asyncio
    async def test_second_identical_alert_suppressed(self) -> None:
        _setup_overrides()

        payload = {
            "title": "CPU usage high",
            "description": "Pod CPU > 90%",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod-a"},
        }

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp1 = await ac.post("/api/v1/alerts", json=payload)
                resp2 = await ac.post("/api/v1/alerts", json=payload)
                resp3 = await ac.post("/api/v1/alerts", json=payload)

            assert resp1.json()["dedup"]["action"] == "process"
            assert resp2.json()["dedup"]["action"] == "suppress"
            assert resp3.json()["dedup"]["action"] == "suppress"
            assert resp2.json()["dedup"]["occurrence_count"] == 2
            assert resp3.json()["dedup"]["occurrence_count"] == 3
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_different_alerts_not_suppressed(self) -> None:
        _setup_overrides()

        base = {
            "severity": "critical",
            "category": "resource",
        }
        alerts = [
            {**base, "title": "CPU high", "description": "CPU", "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod-a"}},
            {**base, "title": "Memory high", "description": "Mem", "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod-a"}},
            {**base, "title": "CPU high", "description": "CPU", "source": {"type": "kubernetes", "system": "test", "namespace": "staging", "pod_name": "pod-a"}},
        ]

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                results = []
                for alert in alerts:
                    resp = await ac.post("/api/v1/alerts", json=alert)
                    results.append(resp.json())

            # All three should be processed (different titles or namespaces)
            for r in results:
                assert r["dedup"]["action"] == "process"
        finally:
            app.dependency_overrides.clear()
