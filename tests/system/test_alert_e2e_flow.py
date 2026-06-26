"""End-to-end alert processing flow system tests.

Tests the complete pipeline: HTTP request → validation → dedup → processor → response.
Validates response schema, dedup behavior, remediation plan creation.
"""

from fastapi.testclient import TestClient
from unittest.mock import MagicMock


class TestK8sAlertFlow:
    """Full flow for Kubernetes alert type."""

    def test_k8s_alert_returns_analysis_result(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["data"] is not None

        data = body["data"]
        assert data["alert_id"].startswith("alert-")
        assert data["trace_id"] == "trace-sys-test"
        assert data["root_cause"]["category"] == "资源不足"
        assert data["root_cause"]["confidence"] == 0.92
        assert len(data["root_cause"]["evidence"]) > 0
        assert data["suggestion"]["summary"] == "调高 Pod CPU limit 至 1000m"
        assert len(data["suggestion"]["commands"]) > 0
        assert data["processing_time_seconds"] > 0

    def test_k8s_alert_creates_remediation_plan(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        body = response.json()

        assert body["remediation_plan_id"] is not None
        assert body["remediation_plan_id"].startswith("plan-")

    def test_k8s_alert_first_occurrence_is_processed(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        body = response.json()
        assert body["dedup"]["action"] == "process"
        assert body["dedup"]["occurrence_count"] == 1


class TestAliyunAlertFlow:
    """Full flow for Aliyun alert type."""

    def test_aliyun_ecs_alert_returns_analysis_result(
        self, client: TestClient, aliyun_ecs_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=aliyun_ecs_alert_payload)
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["data"]["root_cause"]["category"] == "资源不足"

    def test_aliyun_rds_alert_returns_analysis_result(
        self, client: TestClient, aliyun_rds_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=aliyun_rds_alert_payload)
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True


class TestDeduplication:
    """Dedup suppresses duplicate alerts within time window."""

    def test_duplicate_alert_suppressed(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        # First alert → processed
        first = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert first.json()["dedup"]["action"] == "process"

        # Second identical alert → suppressed
        second = client.post("/api/v1/alerts", json=k8s_alert_payload)
        body = second.json()
        assert body["success"] is True
        assert body["data"] is None  # No analysis result
        assert body["dedup"]["action"] == "suppress"
        assert body["dedup"]["occurrence_count"] == 2

    def test_different_severity_not_suppressed(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        # First: critical
        first = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert first.json()["dedup"]["action"] == "process"

        # Second: same alert but different severity → different fingerprint
        modified = {**k8s_alert_payload, "severity": "low"}
        second = client.post("/api/v1/alerts", json=modified)
        assert second.json()["dedup"]["action"] == "process"

    def test_different_pod_not_suppressed(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        first = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert first.json()["dedup"]["action"] == "process"

        modified = {
            **k8s_alert_payload,
            "source": {**k8s_alert_payload["source"], "pod_name": "other-pod-xyz"},
        }
        second = client.post("/api/v1/alerts", json=modified)
        assert second.json()["dedup"]["action"] == "process"

    def test_different_namespace_not_suppressed(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        first = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert first.json()["dedup"]["action"] == "process"

        modified = {
            **k8s_alert_payload,
            "source": {**k8s_alert_payload["source"], "namespace": "staging"},
        }
        second = client.post("/api/v1/alerts", json=modified)
        assert second.json()["dedup"]["action"] == "process"


class TestProcessorInvocation:
    """Verify the processor receives correct data."""

    def test_processor_called_once_per_unique_alert(
        self,
        client: TestClient,
        k8s_alert_payload: dict,
        mock_processor: MagicMock,
    ) -> None:
        mock_processor.process.reset_mock()

        client.post("/api/v1/alerts", json=k8s_alert_payload)

        assert mock_processor.process.await_count == 1
        call_args = mock_processor.process.call_args
        alert = call_args[0][0]  # First positional arg
        assert alert.title == k8s_alert_payload["title"]
        assert alert.source.type == "kubernetes"
        assert alert.source.namespace == "production"
        assert alert.source.pod_name == "order-service-abc123"

    def test_suppressed_alert_does_not_invoke_processor(
        self,
        client: TestClient,
        k8s_alert_payload: dict,
        mock_processor: MagicMock,
    ) -> None:
        mock_processor.process.reset_mock()

        client.post("/api/v1/alerts", json=k8s_alert_payload)
        client.post("/api/v1/alerts", json=k8s_alert_payload)

        # Only first alert should trigger processor
        assert mock_processor.process.await_count == 1


class TestRemediationPlanFlow:
    """Test remediation plan creation and retrieval."""

    def test_plan_created_with_commands(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = response.json()["remediation_plan_id"]
        assert plan_id is not None

        # Retrieve the plan
        plan_response = client.get(f"/api/v1/remediation/{plan_id}")
        assert plan_response.status_code == 200

    def test_reject_plan(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        plan_id = response.json()["remediation_plan_id"]

        reject_response = client.post(
            f"/api/v1/remediation/{plan_id}/reject",
            json={"rejected_by": "ops-user", "reason": "Too risky"},
        )
        assert reject_response.status_code == 200


class TestHealthEndpoints:
    """Health check endpoints under system test."""

    def test_root(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "LangOps"

    def test_health(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_alerts_health(self, client: TestClient) -> None:
        response = client.get("/api/v1/alerts/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
