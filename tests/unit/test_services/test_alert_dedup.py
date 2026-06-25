"""Alert deduplication tests."""

from datetime import UTC, datetime, timedelta

from langops.models import Alert, AlertCategory, AlertSeverity, AlertSource
from langops.services import AlertNoiseReducer


def _alert(*, title: str = "CPU使用率过高") -> Alert:
    return Alert(
        id="alert-001",
        title=title,
        description="CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="prod-cluster",
            namespace="production",
            pod_name="order-pod",
        ),
    )


def test_fingerprint_is_stable_for_same_alert() -> None:
    dedup = AlertNoiseReducer(window_seconds=60)
    a = _alert()
    b = _alert()
    b.id = "alert-002"
    assert dedup.fingerprint(a) == dedup.fingerprint(b)


def test_fingerprint_changes_when_resource_changes() -> None:
    dedup = AlertNoiseReducer(window_seconds=60)
    a = _alert()
    b = _alert()
    b.source.pod_name = "other-pod"
    assert dedup.fingerprint(a) != dedup.fingerprint(b)


def test_first_alert_is_processed() -> None:
    dedup = AlertNoiseReducer(window_seconds=300)
    decision = dedup.evaluate(_alert())
    assert decision.action == "process"
    assert decision.occurrence_count == 1


def test_duplicate_alert_is_suppressed_within_window() -> None:
    dedup = AlertNoiseReducer(window_seconds=300)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    first = dedup.evaluate(_alert(), now=now)
    second = dedup.evaluate(_alert(), now=now + timedelta(seconds=30))

    assert first.action == "process"
    assert second.action == "suppress"
    assert second.occurrence_count == 2


def test_alert_is_processed_again_after_window_expires() -> None:
    dedup = AlertNoiseReducer(window_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=UTC)

    dedup.evaluate(_alert(), now=now)
    decision = dedup.evaluate(_alert(), now=now + timedelta(seconds=120))

    assert decision.action == "process"
    assert decision.occurrence_count == 1


def test_disabled_dedup_always_processes() -> None:
    dedup = AlertNoiseReducer(window_seconds=60, enabled=False)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    dedup.evaluate(_alert(), now=now)
    decision = dedup.evaluate(_alert(), now=now)
    assert decision.action == "process"
