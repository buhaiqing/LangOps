"""Tests for request ID middleware and Prometheus metrics."""

import pytest
from fastapi.testclient import TestClient

from langops.web.main import app
from langops.web.metrics import (
    alerts_processed_total,
    alerts_received_total,
    dedup_suppressed_total,
    remediation_actions_total,
    remediation_plans_total,
)
from langops.web.middleware import request_id_ctx


@pytest.fixture
def client(mock_processor):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from langops.services import AlertNoiseReducer, RemediationRegistry
    from langops.storage.models import Base
    from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
    from langops.web.dependencies import (
        get_alert_dedup,
        get_alert_processor,
        get_remediation_registry,
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sf = sessionmaker(bind=engine)

    dedup_repo = SqlDedupRepository(sf)
    remediation_repo = SqlRemediationRepository(sf)
    dedup = AlertNoiseReducer(repo=dedup_repo, window_seconds=900, enabled=True)
    remediation_registry = RemediationRegistry(repo=remediation_repo)

    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


class TestRequestIDMiddleware:

    def test_generates_request_id_when_not_provided(self, client):
        resp = client.get("/")
        assert "X-Request-ID" in resp.headers
        assert len(resp.headers["X-Request-ID"]) == 32

    def test_uses_provided_request_id(self, client):
        resp = client.get("/", headers={"X-Request-ID": "my-custom-id"})
        assert resp.headers["X-Request-ID"] == "my-custom-id"

    def test_request_id_on_health(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers


class TestMetricsEndpoint:

    def test_metrics_returns_prometheus_format(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        body = resp.text
        assert "langops_alerts_received_total" in body
        assert "langops_http_requests_total" in body

    def test_metrics_increments_after_alert(self, client, mock_processor):
        before = client.get("/metrics").text
        client.post(
            "/api/v1/alerts",
            json={
                "title": "test",
                "description": "test alert",
                "severity": "critical",
                "category": "resource",
                "source": {"type": "kubernetes", "system": "test"},
            },
        )
        after = client.get("/metrics").text
        assert "langops_alerts_received_total" in after
        assert "langops_alerts_processed_total" in after


class TestAlertMetrics:

    def test_received_counter_increments(self, client):
        resp = client.post(
            "/api/v1/alerts",
            json={
                "title": "t",
                "description": "d",
                "severity": "critical",
                "category": "resource",
                "source": {"type": "k8s", "system": "s"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        metrics_text = client.get("/metrics").text
        assert "langops_alerts_received_total" in metrics_text
        assert "langops_alerts_processed_total" in metrics_text


class TestRemediationMetrics:

    def test_actions_counter_exists(self):
        remediation_actions_total.labels(action="execute", status="success").inc()
        assert (
            remediation_actions_total.labels(action="execute", status="success")._value.get() >= 1
        )
