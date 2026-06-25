"""Alert model tests."""

from langops.models import (
    Alert,
    AlertCategory,
    AlertContext,
    AlertCreate,
    AlertSeverity,
    AlertSource,
)


def _sample_source() -> AlertSource:
    return AlertSource(type="kubernetes", system="prod-cluster", namespace="production")


def test_alert_creates_with_enum_fields() -> None:
    alert = Alert(
        id="test-001",
        title="Test Alert",
        description="Test description",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=_sample_source(),
    )
    assert alert.id == "test-001"
    assert alert.severity == AlertSeverity.HIGH
    assert alert.category == AlertCategory.RESOURCE
    assert alert.metric_data == {}


def test_alert_normalizes_severity_from_string() -> None:
    alert = Alert(
        id="test-002",
        title="Critical",
        description="Test",
        severity="CRITICAL",
        category=AlertCategory.PERFORMANCE,
        source={"type": "k8s", "system": "cluster-1"},
    )
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.category == AlertCategory.PERFORMANCE


def test_alert_maps_warning_severity_to_medium() -> None:
    alert = Alert(
        id="test-003",
        title="Warning",
        description="Test",
        severity="warning",
        category="resource",
        source={"type": "prometheus", "system": "prod"},
    )
    assert alert.severity == AlertSeverity.MEDIUM


def test_alert_source_allows_extra_fields() -> None:
    source = AlertSource(type="aliyun", system="cn-hangzhou", custom_tag="ecs-1")
    assert source.type == "aliyun"
    assert source.model_dump()["custom_tag"] == "ecs-1"


def test_alert_create_request_model() -> None:
    payload = AlertCreate(
        title="CPU高",
        description="CPU > 90%",
        severity="high",
        category="resource",
        source={"type": "kubernetes", "system": "prod"},
        metric_data={"cpu": 95.0},
    )
    assert payload.severity == AlertSeverity.HIGH
    assert payload.metric_data["cpu"] == 95.0


def test_alert_context_wraps_alert_and_metrics() -> None:
    alert = Alert(
        id="ctx-001",
        title="Ctx",
        description="Ctx",
        severity=AlertSeverity.LOW,
        category=AlertCategory.AVAILABILITY,
        source=_sample_source(),
    )
    context = AlertContext(alert=alert, metrics={"cpu": 1}, logs=["oom"], time_range_minutes=15)
    assert context.alert.id == "ctx-001"
    assert context.metrics["cpu"] == 1
    assert context.time_range_minutes == 15
