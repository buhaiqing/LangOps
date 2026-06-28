"""Aliyun Cloud Monitor (CMS) webhook callback → AlertCreate mapping."""

from __future__ import annotations

import json

from langops.models import AlertCategory, AlertCreate, AlertSeverity, AlertSource
from langops.models.webhook import AliyunCmsCallbackPayload

_CATEGORY_RULES: list[tuple[frozenset[str], AlertCategory]] = [
    (frozenset({"cpu", "memory", "disk", "fs", "filesystem"}), AlertCategory.RESOURCE),
    (frozenset({"connection", "iops", "bandwidth"}), AlertCategory.RESOURCE),
    (frozenset({"down", "unreachable", "timeout", "unavailable"}), AlertCategory.AVAILABILITY),
    (frozenset({"latency", "slow", "throttle", "backlog"}), AlertCategory.PERFORMANCE),
]

_NAMESPACE_CATEGORY: dict[str, AlertCategory] = {
    "acs_ecs_dashboard": AlertCategory.RESOURCE,
    "acs_rds_dashboard": AlertCategory.RESOURCE,
    "acs_slb_dashboard": AlertCategory.PERFORMANCE,
}

_SEVERITY_LEVEL: dict[str | int, AlertSeverity] = {
    "critical": AlertSeverity.CRITICAL,
    "CRITICAL": AlertSeverity.CRITICAL,
    "1": AlertSeverity.CRITICAL,
    1: AlertSeverity.CRITICAL,
    "warning": AlertSeverity.HIGH,
    "WARNING": AlertSeverity.HIGH,
    "2": AlertSeverity.HIGH,
    2: AlertSeverity.HIGH,
    "info": AlertSeverity.INFO,
    "INFO": AlertSeverity.INFO,
    "3": AlertSeverity.INFO,
    3: AlertSeverity.INFO,
}


def _infer_category(alert_name: str, namespace: str) -> AlertCategory:
    cat = _NAMESPACE_CATEGORY.get(namespace)
    if cat:
        return cat
    text = alert_name.lower()
    for keywords, category in _CATEGORY_RULES:
        if any(kw in text for kw in keywords):
            return category
    return AlertCategory.PERFORMANCE


def _parse_dimensions(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        if isinstance(val, dict):
            return {str(k): str(v) for k, v in val.items()}
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


def _resource_type(namespace: str) -> str | None:
    mapping = {
        "acs_ecs_dashboard": "ecs",
        "acs_rds_dashboard": "rds",
        "acs_slb_dashboard": "slb",
    }
    return mapping.get(namespace)


class AliyunCmsWebhookAdapter:
    """Maps Alibaba Cloud Monitor callback payloads to LangOps AlertCreate."""

    def to_alert_create(self, payload: AliyunCmsCallbackPayload) -> AlertCreate:
        alert_name = payload.alertName
        namespace = payload.namespace
        dimensions = _parse_dimensions(payload.dimensions)
        instance_id = dimensions.get("instanceId", "")

        source = AlertSource(
            type="aliyun",
            system="aliyun-cms",
            service=payload.instanceName or None,
            resource_type=_resource_type(namespace),
            instance_id=instance_id,
        )

        desc = payload.expression
        cur = payload.curValue
        if cur:
            desc = f"{desc} (current: {cur})" if desc else f"value: {cur}"

        return AlertCreate(
            title=alert_name,
            description=desc,
            severity=_SEVERITY_LEVEL.get(payload.level, AlertSeverity.INFO),
            category=_infer_category(alert_name, namespace),
            source=source,
            context={
                "alert_state": payload.alertState,
                "metric_name": payload.metricName,
                "namespace": namespace,
                "dimensions": dimensions,
                "expression": payload.expression,
                "cur_value": payload.curValue,
                "region_id": payload.regionId,
                "user_id": payload.userId,
                "timestamp": payload.timestamp,
            },
        )
