"""AlertManager webhook payload → AlertCreate mapping."""

import re
from urllib.parse import urlparse

from langops.models import AlertCategory, AlertCreate, AlertSeverity, AlertSource
from langops.models.webhook import AlertmanagerAlert, AlertmanagerWebhookPayload

_ZERO_ENDS_AT = "0001-01-01T00:00:00Z"

_CATEGORY_RULES: list[tuple[re.Pattern[str], AlertCategory]] = [
    (re.compile(r"cpu|memory|disk|fs|filesystem", re.IGNORECASE), AlertCategory.RESOURCE),
    (
        re.compile(r"down|unreachable|timeout|unavailable|outage", re.IGNORECASE),
        AlertCategory.AVAILABILITY,
    ),
    (
        re.compile(r"latency|slow|throttle|backlog", re.IGNORECASE),
        AlertCategory.PERFORMANCE,
    ),
    (
        re.compile(r"auth|unauthorized|forbidden|intrusion", re.IGNORECASE),
        AlertCategory.SECURITY,
    ),
]

_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "critical": AlertSeverity.CRITICAL,
    "page": AlertSeverity.CRITICAL,
    "high": AlertSeverity.HIGH,
    "medium": AlertSeverity.MEDIUM,
    "warning": AlertSeverity.MEDIUM,
    "warn": AlertSeverity.MEDIUM,
    "low": AlertSeverity.LOW,
    "info": AlertSeverity.INFO,
    "information": AlertSeverity.INFO,
}


def _infer_category(alert: AlertmanagerAlert) -> AlertCategory:
    text = alert.labels.get("alertname", "") + " ".join(alert.labels.values())
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(text):
            return category
    return AlertCategory.PERFORMANCE


def _normalize_severity(raw: str | None) -> AlertSeverity:
    if raw is None:
        return AlertSeverity.MEDIUM
    return _SEVERITY_MAP.get(raw.lower(), AlertSeverity.INFO)


def _title(alert: AlertmanagerAlert) -> str:
    summary = alert.annotations.get("summary", "").strip()
    if summary:
        return summary[:500]
    for value in alert.annotations.values():
        if value.strip():
            return value.strip()[:500]
    alertname = alert.labels.get("alertname", "").strip()
    if alertname:
        return alertname[:500]
    return "Unknown alert"


def _description(alert: AlertmanagerAlert) -> str:
    for key in ("description", "summary", "message"):
        value = alert.annotations.get(key, "").strip()
        if value:
            return value[:10000]
    alertname = alert.labels.get("alertname", "unknown")
    return f"{alertname}: {alert.status}"


def _system(payload: AlertmanagerWebhookPayload, alert: AlertmanagerAlert) -> str:
    if payload.externalURL:
        host = urlparse(payload.externalURL).hostname
        if host:
            return host
    job = alert.labels.get("job", "").strip()
    if job:
        return job
    return "unknown"


def _build_context(
    payload: AlertmanagerWebhookPayload, alert: AlertmanagerAlert
) -> dict[str, object]:
    context: dict[str, object] = {
        "labels": dict(alert.labels),
        "annotations": dict(alert.annotations),
        "alertmanager_status": alert.status,
    }
    if alert.startsAt:
        context["starts_at"] = alert.startsAt
    if alert.endsAt and alert.endsAt != _ZERO_ENDS_AT:
        context["ends_at"] = alert.endsAt
    return context


class AlertmanagerAdapter:
    """Maps AlertManager v4 webhook payloads to LangOps AlertCreate requests."""

    def to_alert_creates(self, payload: AlertmanagerWebhookPayload) -> list[AlertCreate]:
        return [self._map_alert(payload, alert) for alert in payload.alerts]

    def _map_alert(
        self, payload: AlertmanagerWebhookPayload, alert: AlertmanagerAlert
    ) -> AlertCreate:
        labels = alert.labels
        source = AlertSource(
            type="prometheus",
            system=_system(payload, alert),
            service=labels.get("service"),
            namespace=labels.get("namespace"),
            pod_name=labels.get("pod"),
            instance_id=labels.get("instance"),
        )
        return AlertCreate(
            title=_title(alert),
            description=_description(alert),
            severity=_normalize_severity(labels.get("severity")),
            category=_infer_category(alert),
            source=source,
            context=_build_context(payload, alert),
        )
