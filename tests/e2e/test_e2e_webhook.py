"""End-to-end integration tests for LangOps webhook ingestion pipeline.

These tests hit a **real running server** (started by conftest.py) and verify
the full request lifecycle: HTTP → adapter → dedup → analysis → response.

Run via:  make e2e   (or:  pytest tests/e2e/ -v)
"""

from __future__ import annotations

import time

import pytest
import requests

# ── helpers ──────────────────────────────────────────────────────────────

_TS = int(time.time())  # unique per test-run, used in fingerprints/pod names


def _post(server_url: str, path: str, payload: dict, **kw) -> requests.Response:
    return requests.post(f"{server_url}{path}", json=payload, timeout=120, **kw)


# ═══════════════════════════════════════════════════════════════════════════
# Health & root
# ═══════════════════════════════════════════════════════════════════════════


class TestHealth:
    def test_root_returns_version(self, server_url: str):
        r = requests.get(f"{server_url}/", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "LangOps"
        assert "version" in body

    def test_health_status_is_valid(self, server_url: str):
        r = requests.get(f"{server_url}/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("healthy", "degraded", "unhealthy")
        assert body["checks"]["storage"]["status"] == "up"


# ═══════════════════════════════════════════════════════════════════════════
# AlertManager Webhook
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertmanagerWebhook:
    """POST /api/v1/webhooks/alertmanager"""

    def _make_payload(self, **alert_overrides) -> dict:
        alert = {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": f"am-pod-{_TS}",
            },
            "annotations": {"summary": "High CPU", "description": "CPU > 90%"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph",
            "fingerprint": f"fp-{_TS}",
        }
        alert.update(alert_overrides)
        return {
            "version": "4",
            "groupKey": f"{{}}:{{alertname=\"HighCPU\"}}",
            "status": "firing",
            "receiver": "langops",
            "groupLabels": {"alertname": "HighCPU"},
            "commonLabels": {"alertname": "HighCPU", "severity": "critical"},
            "commonAnnotations": {"summary": "CPU > 90%"},
            "externalURL": "http://alertmanager:9093",
            "alerts": [alert],
        }

    def test_single_alert_returns_200(self, server_url: str):
        r = _post(server_url, "/api/v1/webhooks/alertmanager", self._make_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["received"] == 1
        assert len(body["results"]) == 1
        assert body["audit"]["coalesced"] is False

    def test_batch_3_alerts(self, server_url: str):
        alerts = []
        for i in range(3):
            alerts.append({
                "status": "firing",
                "labels": {"alertname": f"Alert-{i}", "severity": "warning", "namespace": "prod", "pod": f"batch-pod-{_TS}-{i}"},
                "annotations": {"summary": f"Alert-{i}"},
                "startsAt": "2024-01-15T10:30:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://prom:9090",
                "fingerprint": f"batch-{_TS}-{i}",
            })
        payload = self._make_payload()
        payload["alerts"] = alerts

        r = _post(server_url, "/api/v1/webhooks/alertmanager", payload)
        assert r.status_code == 200
        body = r.json()
        assert body["received"] == 3
        assert len(body["results"]) == 3

    def test_invalid_json_returns_422(self, server_url: str):
        r = requests.post(
            f"{server_url}/api/v1/webhooks/alertmanager",
            data=b"{bad",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 422

    def test_unicode_roundtrip(self, server_url: str):
        payload = self._make_payload()
        payload["alerts"][0]["labels"]["alertname"] = "🚨 高CPU告警"
        payload["alerts"][0]["annotations"]["summary"] = "订单服务 CPU 使用率超过 90% ⚠️"

        r = _post(server_url, "/api/v1/webhooks/alertmanager", payload)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Aliyun CMS Webhook
# ═══════════════════════════════════════════════════════════════════════════


class TestAliyunCmsWebhook:
    """POST /api/v1/webhooks/aliyun-cms"""

    def _make_payload(self, **overrides) -> dict:
        base = {
            "alertName": f"CMS-ECS-CPU-{_TS}",
            "alertState": "ALERT",
            "curValue": "95.5",
            "dimensions": f'{{"instanceId":"i-cms-{_TS}"}}',
            "expression": "Average > 90",
            "instanceName": "web-server-01",
            "metricName": "CPUUtilization",
            "namespace": "acs_ecs_dashboard",
            "regionId": "cn-hangzhou",
            "timestamp": "1705300000000",
            "userId": "123456789",
            "level": "critical",
        }
        base.update(overrides)
        return base

    def test_ecs_alert_returns_200(self, server_url: str):
        r = _post(server_url, "/api/v1/webhooks/aliyun-cms", self._make_payload())
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["received"] == 1
        assert len(body["results"]) == 1

    def test_rds_alert_returns_200(self, server_url: str):
        payload = self._make_payload(
            alertName=f"CMS-RDS-Conn-{_TS}",
            namespace="acs_rds_dashboard",
            metricName="ConnectionUsage",
            level="warning",
            dimensions=f'{{"instanceId":"rm-rds-{_TS}"}}',
        )
        r = _post(server_url, "/api/v1/webhooks/aliyun-cms", payload)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True

    def test_slb_alert_returns_200(self, server_url: str):
        payload = self._make_payload(
            alertName=f"CMS-SLB-5xx-{_TS}",
            namespace="acs_slb_dashboard",
            metricName="HighQps5xx",
            dimensions=f'{{"instanceId":"lb-slb-{_TS}"}}',
        )
        r = _post(server_url, "/api/v1/webhooks/aliyun-cms", payload)
        assert r.status_code == 200

    def test_recovery_ok_skips_analysis(self, server_url: str):
        payload = self._make_payload(alertState="OK", curValue="45")
        r = _post(server_url, "/api/v1/webhooks/aliyun-cms", payload)
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["results"] == []  # no analysis for recovery

    def test_invalid_json_returns_422(self, server_url: str):
        r = requests.post(
            f"{server_url}/api/v1/webhooks/aliyun-cms",
            data=b"{bad",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Dedup
# ═══════════════════════════════════════════════════════════════════════════


class TestDedup:
    """POST /api/v1/alerts — dedup within 15-min window."""

    def test_duplicate_suppressed(self, server_url: str):
        payload = {
            "title": f"Dedup-{_TS}",
            "description": "dedup test",
            "severity": "medium",
            "category": "resource",
            "source": {"type": "kubernetes", "system": "s", "namespace": "n", "pod_name": f"dedup-pod-{_TS}"},
        }

        # First request — should attempt analysis
        r1 = _post(server_url, "/api/v1/alerts", payload)
        assert r1.status_code == 200

        # Second request — same pod → suppressed
        r2 = _post(server_url, "/api/v1/alerts", payload)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["success"] is True
        assert body2["dedup"]["action"] == "suppress"
        assert body2["dedup"]["occurrence_count"] == 2
