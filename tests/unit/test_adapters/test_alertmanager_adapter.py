"""AlertmanagerAdapter mapping tests."""

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.models import AlertCategory, AlertSeverity
from langops.models.webhook import AlertmanagerWebhookPayload

SAMPLE = {
    "version": "4",
    "status": "firing",
    "receiver": "langops",
    "externalURL": "http://alertmanager.prod:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": "order-abc",
            },
            "annotations": {"summary": "High CPU"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}


def test_maps_to_alert_create() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(SAMPLE)
    results = AlertmanagerAdapter().to_alert_creates(payload)
    assert len(results) == 1
    ac = results[0]
    assert ac.title == "High CPU"
    assert ac.description == "High CPU"  # fallback: summary when no description
    assert ac.severity == AlertSeverity.CRITICAL
    assert ac.category == AlertCategory.RESOURCE
    assert ac.source.type == "prometheus"
    assert ac.source.system == "alertmanager.prod"
    assert ac.source.namespace == "production"
    assert ac.source.pod_name == "order-abc"
    assert ac.context["alertmanager_status"] == "firing"


def test_description_fallback_to_alertname() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(
        {
            **SAMPLE,
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "DiskFull", "severity": "warning"},
                    "annotations": {},
                    "startsAt": "2024-01-15T10:30:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        }
    )
    ac = AlertmanagerAdapter().to_alert_creates(payload)[0]
    assert ac.description == "DiskFull: firing"
    assert ac.severity == AlertSeverity.MEDIUM  # warning → medium via enum


def test_multi_alert_payload() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(
        {
            **SAMPLE,
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "AlertOne", "severity": "high"},
                    "annotations": {"summary": "First"},
                    "startsAt": "2024-01-15T10:30:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                },
                {
                    "status": "firing",
                    "labels": {"alertname": "AlertTwo", "severity": "low"},
                    "annotations": {"summary": "Second"},
                    "startsAt": "2024-01-15T10:31:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                },
            ],
        }
    )
    results = AlertmanagerAdapter().to_alert_creates(payload)
    assert len(results) == 2
    assert results[0].title == "First"
    assert results[1].title == "Second"


def test_resolved_alert_status_in_context() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(
        {
            **SAMPLE,
            "alerts": [
                {
                    "status": "resolved",
                    "labels": {"alertname": "HighCPU", "severity": "critical"},
                    "annotations": {"summary": "Resolved CPU"},
                    "startsAt": "2024-01-15T10:30:00Z",
                    "endsAt": "2024-01-15T11:00:00Z",
                }
            ],
        }
    )
    ac = AlertmanagerAdapter().to_alert_creates(payload)[0]
    assert ac.context["alertmanager_status"] == "resolved"
    assert ac.context["ends_at"] == "2024-01-15T11:00:00Z"
