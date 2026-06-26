"""AlertManager webhook payload model tests."""

import pytest
from pydantic import ValidationError

from langops.models.webhook import AlertmanagerAlert, AlertmanagerWebhookPayload

SAMPLE_PAYLOAD = {
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


def test_parses_am_v4_payload() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(SAMPLE_PAYLOAD)
    assert payload.version == "4"
    assert len(payload.alerts) == 1
    assert payload.alerts[0].labels["alertname"] == "HighCPU"


def test_rejects_missing_alerts() -> None:
    bad = {**SAMPLE_PAYLOAD, "alerts": []}
    with pytest.raises(ValidationError):
        AlertmanagerWebhookPayload.model_validate(bad)


def test_ignores_unknown_fields() -> None:
    extended = {**SAMPLE_PAYLOAD, "futureField": "ok"}
    payload = AlertmanagerWebhookPayload.model_validate(extended)
    assert payload.receiver == "langops"
