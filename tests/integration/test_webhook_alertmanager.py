"""Integration tests for POST /api/v1/webhooks/alertmanager."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.agent.alert_processor import AlertProcessor
from langops.core.audit import AuditLogger
from langops.models import (
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web._coalesce import CoalesceBuffer
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_alertmanager_adapter,
    get_audit_logger,
    get_coalesce_buffer,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.main import create_app

SAMPLE_PAYLOAD: dict[str, Any] = {
    "version": "4",
    "groupKey": '{}:{alertname="HighCPU"}',
    "status": "firing",
    "receiver": "langops",
    "groupLabels": {"alertname": "HighCPU"},
    "commonLabels": {"alertname": "HighCPU", "severity": "critical"},
    "commonAnnotations": {"summary": "CPU > 90%"},
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": "order-service-abc",
            },
            "annotations": {"summary": "High CPU", "description": "CPU > 90% for 5m"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph",
            "fingerprint": "abc123",
        }
    ],
}


def _dedup_repo(tmp_path_factory):
    # ponytail: file-based SQLite (tmp per fixture) avoids the read-then-write
    # race in SqlDedupRepository when the route fires concurrent alerts via gather.
    # The default `sqlite://` shares a single in-process connection across
    # threads which corrupts under concurrent inserts.
    db_file = tmp_path_factory.mktemp("dedup") / "dedup.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlDedupRepository(sessionmaker(bind=engine))


def _remediation_repo(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("remediation") / "remediation.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


@pytest.fixture
def mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-123",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(
                summary="调高 limit",
                steps=["step1"],
                commands=["kubectl scale deployment/order --replicas=3"],
            ),
            processing_time_seconds=1.2,
        )
    )
    return processor


@pytest.fixture
def dedup(tmp_path_factory) -> AlertNoiseReducer:
    return AlertNoiseReducer(repo=_dedup_repo(tmp_path_factory), window_seconds=900, enabled=True)


@pytest.fixture
def remediation_registry(tmp_path_factory) -> RemediationRegistry:
    return RemediationRegistry(repo=_remediation_repo(tmp_path_factory))


@pytest.fixture
def jira() -> JiraService:
    return JiraService(url="", username="", api_token="", enabled=False)


@pytest.fixture
def audit(tmp_path) -> AuditLogger:
    """File-based AuditLogger isolated to a tmp file."""
    return AuditLogger(path=str(tmp_path / "audit.log"), retention_days=1)


@pytest.fixture
def coalesce_buffer(audit: AuditLogger) -> CoalesceBuffer:
    """CoalesceBuffer wired with a no-op flush callback.

    Tests that exercise coalesce behavior override ``buffer._on_flush``.
    """
    return CoalesceBuffer(
        cap=100,
        on_flush=lambda src, alerts: asyncio.sleep(0),  # type: ignore[arg-type,return-value]
        window_seconds=5.0,
        audit=audit,
    )


@pytest.fixture
def client(
    mock_processor: MagicMock,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
    audit: AuditLogger,
    coalesce_buffer: CoalesceBuffer,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    app.dependency_overrides[get_jira_service] = lambda: jira
    app.dependency_overrides[get_alertmanager_adapter] = lambda: AlertmanagerAdapter()
    app.dependency_overrides[get_audit_logger] = lambda: audit
    app.dependency_overrides[get_coalesce_buffer] = lambda: coalesce_buffer
    return TestClient(app)


# ─── single alert ───────────────────────────────────────────────────────


def test_post_single_alert_returns_200_with_results(
    client: TestClient, mock_processor: MagicMock
) -> None:
    response = client.post("/api/v1/webhooks/alertmanager", json=SAMPLE_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["received"] == 1
    assert len(body["results"]) == 1
    assert body["results"][0]["success"] is True
    assert body["audit"]["coalesced"] is False
    mock_processor.process.assert_awaited_once()


def test_post_multiple_alerts_processed_in_batch(
    client: TestClient, mock_processor: MagicMock
) -> None:
    # Each alert needs a unique dedup fingerprint → distinct pod_name.
    distinct = [
        {
            **SAMPLE_PAYLOAD["alerts"][0],
            "labels": {**SAMPLE_PAYLOAD["alerts"][0]["labels"], "pod": f"order-pod-{i}"},
        }
        for i in range(3)
    ]
    payload = {**SAMPLE_PAYLOAD, "alerts": distinct}

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 3
    assert len(body["results"]) == 3
    assert all(r["success"] for r in body["results"])
    assert mock_processor.process.await_count == 3


# ─── validation errors ─────────────────────────────────────────────────


def test_post_oversized_payload_returns_422(
    client: TestClient,
) -> None:
    """A body larger than settings.webhook.max_payload_bytes must be rejected.

    We use a content-length header so the route rejects before parsing.
    """
    # Build a payload larger than the default 1MB limit
    big_alerts = [
        {**SAMPLE_PAYLOAD["alerts"][0], "annotations": {"big": "x" * 2_000_000}} for _ in range(1)
    ]
    payload = {**SAMPLE_PAYLOAD, "alerts": big_alerts}

    # Send raw JSON so the server sees the actual content-length.
    import json

    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "too large" in response.text.lower()


def test_post_invalid_json_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_post_invalid_coalesce_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/webhooks/alertmanager?coalesce=10x", json=SAMPLE_PAYLOAD)
    assert response.status_code == 422
    assert "coalesce" in response.text.lower()


# ─── coalesce ───────────────────────────────────────────────────────────


def test_coalesce_returns_immediately(client: TestClient, mock_processor: MagicMock) -> None:
    response = client.post("/api/v1/webhooks/alertmanager?coalesce=1s", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["received"] == 1
    assert body["results"] == []
    assert body["audit"]["coalesced"] is True
    assert body["audit"]["coalesce_seconds"] == 1
    # Coalesced → processor must NOT be awaited inline
    mock_processor.process.assert_not_awaited()


# ─── partial failure ────────────────────────────────────────────────────


def test_per_alert_failure_returns_partial_results(
    client: TestClient,
    mock_processor: MagicMock,
) -> None:
    """If processor.process raises for one alert, others should still succeed."""

    success_result = AnalysisResult(
        alert_id="alert-success",
        trace_id="trace-success",
        root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
        suggestion=RemediationSuggestion(
            summary="调高 limit",
            steps=["step1"],
            commands=["kubectl scale deployment/order --replicas=3"],
        ),
        processing_time_seconds=1.2,
    )

    async def selective(alert, *args, **kwargs):
        if alert.title == "High CPU":  # default sample title
            raise RuntimeError("simulated processing failure")
        return success_result

    mock_processor.process = AsyncMock(side_effect=selective)

    # Build two distinct alerts so we can target one for failure
    payload = {
        **SAMPLE_PAYLOAD,
        "alerts": [
            SAMPLE_PAYLOAD["alerts"][0],
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "labels": {
                    **SAMPLE_PAYLOAD["alerts"][0]["labels"],
                    "alertname": "LowCPU",
                },
                "annotations": {"summary": "Low CPU"},
                "fingerprint": "def456",
            },
        ],
    }

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 2
    assert len(body["results"]) == 2
    # One fails, one succeeds
    successes = [r for r in body["results"] if r["success"]]
    failures = [r for r in body["results"] if not r["success"]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert "simulated processing failure" in failures[0]["error"]
