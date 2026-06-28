"""End-to-end tests for LangOps."""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_root_endpoint(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "LangOps"
        assert "version" in data

    def test_health_endpoint(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Non-core dependencies (ChromaDB, Prometheus) may be down in test
        assert data["status"] in ("healthy", "degraded")
        assert "checks" in data
        assert "storage" in data["checks"]

    def test_alerts_health(self, client: TestClient) -> None:
        response = client.get("/api/v1/alerts/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAlertProcessing:
    """Test alert processing API."""

    def test_create_alert_success(
        self,
        client: TestClient,
        sample_alert_data: dict,
        mock_processor: MagicMock,
    ) -> None:
        response = client.post("/api/v1/alerts", json=sample_alert_data)

        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True
        assert result["data"]["alert_id"]
        assert result["data"]["trace_id"] == "trace-123"
        assert result["data"]["root_cause"]
        assert result["data"]["suggestion"]
        mock_processor.process.assert_awaited_once()

    def test_create_alert_validation_error(self, client: TestClient) -> None:
        invalid_data = {"title": "Test"}
        response = client.post("/api/v1/alerts", json=invalid_data)
        assert response.status_code == 422
