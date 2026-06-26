"""Alert input validation system tests.

Validates that the API correctly rejects invalid payloads and provides
clear error messages for missing conditional fields.
"""

from fastapi.testclient import TestClient


class TestRequiredFields:
    """Top-level required fields must be present."""

    def test_empty_body_rejected(self, client: TestClient) -> None:
        response = client.post("/api/v1/alerts", json={})
        assert response.status_code == 422
        body = response.json()
        # Pydantic returns detail array with missing field info
        assert "detail" in body

    def test_missing_source_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test desc",
            "severity": "critical",
            "category": "resource",
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422

    def test_missing_severity_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test desc",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422

    def test_missing_category_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test desc",
            "severity": "critical",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422


class TestSourceFields:
    """AlertSource field validation."""

    def test_missing_type_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test desc",
            "severity": "critical",
            "category": "resource",
            "source": {"system": "test-cluster"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422

    def test_missing_system_rejected(self, client: TestClient) -> None:
        """system is currently required — verify it's enforced."""
        payload = {
            "title": "Test",
            "description": "Test desc",
            "severity": "critical",
            "category": "resource",
            "source": {
                "type": "kubernetes",
                "namespace": "default",
                "pod_name": "test-pod",
            },
        }
        response = client.post("/api/v1/alerts", json=payload)
        # Currently system is required → 422
        assert response.status_code == 422


class TestKubernetesSourceValidation:
    """Kubernetes alerts should require namespace + pod_name."""

    def test_k8s_alert_without_namespace_succeeds_currently(
        self, client: TestClient
    ) -> None:
        """NOTE: Currently namespace is Optional in schema, so this succeeds.
        But the collector will return an error internally.
        This test documents the CURRENT behavior.
        """
        payload = {
            "title": "Pod restart loop",
            "description": "Pod keeps restarting",
            "severity": "critical",
            "category": "availability",
            "source": {
                "type": "kubernetes",
                "system": "test-cluster",
                "pod_name": "my-pod",
                # namespace missing
            },
        }
        response = client.post("/api/v1/alerts", json=payload)
        # Schema allows it (namespace is Optional), but collector will fail
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True

    def test_k8s_alert_without_pod_name_succeeds_currently(
        self, client: TestClient
    ) -> None:
        """Same as above — pod_name is Optional in schema."""
        payload = {
            "title": "High memory",
            "description": "Memory usage high",
            "severity": "high",
            "category": "resource",
            "source": {
                "type": "kubernetes",
                "system": "test-cluster",
                "namespace": "production",
                # pod_name missing
            },
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200

    def test_k8s_alert_with_all_fields_succeeds(
        self, client: TestClient, k8s_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=k8s_alert_payload)
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestAliyunSourceValidation:
    """Aliyun alerts should require instance_id."""

    def test_aliyun_alert_without_instance_id_succeeds_currently(
        self, client: TestClient
    ) -> None:
        """NOTE: instance_id is Optional in schema, so this succeeds.
        But the collector will return an error internally.
        """
        payload = {
            "title": "ECS CPU high",
            "description": "CPU > 90%",
            "severity": "high",
            "category": "resource",
            "source": {
                "type": "aliyun",
                "system": "aliyun-prod",
                # instance_id missing
            },
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_aliyun_ecs_alert_with_all_fields_succeeds(
        self, client: TestClient, aliyun_ecs_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=aliyun_ecs_alert_payload)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_aliyun_rds_alert_with_all_fields_succeeds(
        self, client: TestClient, aliyun_rds_alert_payload: dict
    ) -> None:
        response = client.post("/api/v1/alerts", json=aliyun_rds_alert_payload)
        assert response.status_code == 200
        assert response.json()["success"] is True


class TestSeverityNormalization:
    """Severity string normalization.

    NOTE: Pydantic v2 with `str, Enum` validates the string against enum
    values BEFORE the field_validator runs. So "warning" and "invalid_level"
    are rejected with 422, even though the field_validator has a fallback.
    This test documents the ACTUAL behavior.
    """

    def test_valid_severity_accepted(self, client: TestClient) -> None:
        for sev in ("critical", "high", "medium", "low", "info"):
            payload = {
                "title": f"Test {sev}",
                "description": "Test",
                "severity": sev,
                "category": "resource",
                "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
            }
            response = client.post("/api/v1/alerts", json=payload)
            assert response.status_code == 200, f"severity={sev} should be accepted"

    def test_warning_rejected_by_enum(self, client: TestClient) -> None:
        """'warning' is not a valid AlertSeverity enum value → 422."""
        payload = {
            "title": "Warning level",
            "description": "Something",
            "severity": "warning",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422

    def test_invalid_severity_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test",
            "severity": "invalid_level",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422
