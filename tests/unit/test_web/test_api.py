"""Web API tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from langops.agent.alert_processor import AlertProcessor
from langops.models import AnalysisResult, RemediationSuggestion, RootCause
from langops.services import AlertNoiseReducer
from langops.web.dependencies import get_alert_dedup, get_alert_processor
from langops.web.main import create_app


@pytest.fixture
def mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-123",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(summary="调高 limit", steps=["step1"]),
            processing_time_seconds=1.2,
        )
    )
    return processor


@pytest.fixture
def dedup() -> AlertNoiseReducer:
    return AlertNoiseReducer(window_seconds=900, enabled=True)


@pytest.fixture
def client(mock_processor: MagicMock, dedup: AlertNoiseReducer) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    return TestClient(app)


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "LangOps"
    assert data["version"] == "0.1.0"


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_alerts_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/alerts/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_alert_success(client: TestClient, mock_processor: MagicMock) -> None:
    payload = {
        "title": "CPU使用率过高",
        "description": "order-service CPU > 90%",
        "severity": "critical",
        "category": "resource",
        "source": {
            "type": "kubernetes",
            "system": "prod-cluster",
            "namespace": "production",
            "pod_name": "order-pod",
        },
        "metric_data": {"cpu": 95.0},
    }

    response = client.post("/api/v1/alerts", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["trace_id"] == "trace-123"
    assert body["data"]["root_cause"]["category"] == "资源不足"
    assert body["dedup"]["action"] == "process"
    mock_processor.process.assert_awaited_once()


def test_create_alert_suppresses_duplicate(client: TestClient, mock_processor: MagicMock) -> None:
    payload = {
        "title": "CPU使用率过高",
        "description": "order-service CPU > 90%",
        "severity": "critical",
        "category": "resource",
        "source": {
            "type": "kubernetes",
            "system": "prod-cluster",
            "namespace": "production",
            "pod_name": "order-pod",
        },
    }

    first = client.post("/api/v1/alerts", json=payload)
    second = client.post("/api/v1/alerts", json=payload)

    assert first.json()["dedup"]["action"] == "process"
    assert second.json()["success"] is True
    assert second.json()["data"] is None
    assert second.json()["dedup"]["action"] == "suppress"
    mock_processor.process.assert_awaited_once()


def test_create_alert_validation_error(client: TestClient) -> None:
    response = client.post("/api/v1/alerts", json={"title": "only title"})
    assert response.status_code == 422
