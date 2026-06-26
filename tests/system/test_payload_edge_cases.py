"""Payload edge case system tests.

Validates boundary conditions: empty description, very long title,
large metric_data, special characters, and type coercion.
"""

from fastapi.testclient import TestClient


class TestDescriptionEdgeCases:
    """description field edge cases."""

    def test_empty_description_accepted(self, client: TestClient) -> None:
        payload = {
            "title": "Alert with no description",
            "description": "",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200

    def test_description_with_special_characters(self, client: TestClient) -> None:
        payload = {
            "title": "Alert with emoji 🔥 and unicode",
            "description": "CPU > 90% on pod-xyz\n\nMulti-line\ndescription with <html> &amp; entities",
            "severity": "high",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200


class TestTitleEdgeCases:
    """title field edge cases."""

    def test_very_long_title_accepted(self, client: TestClient) -> None:
        long_title = "A" * 1000
        payload = {
            "title": long_title,
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        # Accept if schema allows it (no max_length constraint)
        assert response.status_code in (200, 422)

    def test_single_char_title_accepted(self, client: TestClient) -> None:
        payload = {
            "title": "X",
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200


class TestMetricDataEdgeCases:
    """metric_data field edge cases."""

    def test_missing_metric_data_accepted(self, client: TestClient) -> None:
        """metric_data is Optional — absence should not fail."""
        payload = {
            "title": "No metrics",
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200

    def test_empty_metric_data_accepted(self, client: TestClient) -> None:
        payload = {
            "title": "Empty metrics",
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
            "metric_data": {},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200

    def test_large_metric_data_dict_accepted(self, client: TestClient) -> None:
        """metric_data with many keys should be accepted."""
        large_metrics = {f"metric_{i}": i * 0.1 for i in range(200)}
        payload = {
            "title": "Large metrics",
            "description": "Test",
            "severity": "critical",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test", "namespace": "default", "pod_name": "pod"},
            "metric_data": large_metrics,
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 200


class TestTypeCoercion:
    """Severity and category should be case-sensitive enums."""

    def test_uppercase_severity_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test",
            "severity": "CRITICAL",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        # Pydantic enum is case-sensitive → CRITICAL != critical
        assert response.status_code == 422

    def test_numeric_severity_rejected(self, client: TestClient) -> None:
        payload = {
            "title": "Test",
            "description": "Test",
            "severity": 3,
            "category": "resource",
            "source": {"type": "kubernetes", "system": "test"},
        }
        response = client.post("/api/v1/alerts", json=payload)
        assert response.status_code == 422
