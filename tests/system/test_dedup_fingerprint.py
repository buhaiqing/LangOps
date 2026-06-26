"""Dedup fingerprint accuracy system tests.

Validates that the fingerprint algorithm correctly distinguishes alerts
based on category, severity, type, system, namespace, resource, and title.
"""

from langops.models import Alert, AlertSource, AlertSeverity, AlertCategory
from langops.services.alert_dedup import AlertNoiseReducer
from langops.storage.sql import SqlDedupRepository
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest


def _make_dedup() -> AlertNoiseReducer:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from langops.storage.models import Base
    Base.metadata.create_all(bind=engine)
    repo = SqlDedupRepository(sessionmaker(bind=engine))
    return AlertNoiseReducer(repo=repo, window_seconds=900, enabled=True)


def _make_alert(**kwargs) -> Alert:
    source_fields = {
        "type": kwargs.pop("source_type", "kubernetes"),
        "system": kwargs.pop("system", "prod-cluster"),
    }
    for key in ("namespace", "pod_name", "instance_id", "resource_type", "service"):
        if key in kwargs:
            source_fields[key] = kwargs.pop(key)

    return Alert(
        id=kwargs.pop("id", "test-001"),
        title=kwargs.pop("title", "CPU使用率过高"),
        description=kwargs.pop("description", "Test"),
        severity=kwargs.pop("severity", AlertSeverity.CRITICAL),
        category=kwargs.pop("category", AlertCategory.RESOURCE),
        source=AlertSource(**source_fields),
        **kwargs,
    )


class TestFingerprintDistinguishes:
    """Fingerprint should produce different hashes for different alerts."""

    def setup_method(self) -> None:
        self.dedup = _make_dedup()

    def test_same_alert_same_fingerprint(self) -> None:
        a1 = _make_alert()
        a2 = _make_alert(id="test-002")
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)

    def test_different_severity_different_fingerprint(self) -> None:
        a1 = _make_alert(severity=AlertSeverity.CRITICAL)
        a2 = _make_alert(severity=AlertSeverity.LOW)
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_category_different_fingerprint(self) -> None:
        a1 = _make_alert(category=AlertCategory.RESOURCE)
        a2 = _make_alert(category=AlertCategory.AVAILABILITY)
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_type_different_fingerprint(self) -> None:
        a1 = _make_alert(source_type="kubernetes")
        a2 = _make_alert(source_type="aliyun")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_system_different_fingerprint(self) -> None:
        a1 = _make_alert(system="cluster-a")
        a2 = _make_alert(system="cluster-b")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_namespace_different_fingerprint(self) -> None:
        a1 = _make_alert(namespace="production")
        a2 = _make_alert(namespace="staging")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_pod_different_fingerprint(self) -> None:
        a1 = _make_alert(pod_name="pod-a")
        a2 = _make_alert(pod_name="pod-b")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_instance_different_fingerprint(self) -> None:
        a1 = _make_alert(source_type="aliyun", instance_id="i-aaa")
        a2 = _make_alert(source_type="aliyun", instance_id="i-bbb")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_different_title_different_fingerprint(self) -> None:
        a1 = _make_alert(title="CPU使用率过高")
        a2 = _make_alert(title="内存使用率过高")
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)


class TestFingerprintNormalization:
    """Title normalization should ignore whitespace and numbers."""

    def setup_method(self) -> None:
        self.dedup = _make_dedup()

    def test_whitespace_normalized(self) -> None:
        a1 = _make_alert(title="CPU 使用率 过高")
        a2 = _make_alert(title="CPU  使用率   过高")
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)

    def test_numbers_normalized(self) -> None:
        a1 = _make_alert(title="CPU使用率超过90%")
        a2 = _make_alert(title="CPU使用率超过95%")
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)

    def test_case_normalized(self) -> None:
        a1 = _make_alert(title="CPU Usage High")
        a2 = _make_alert(title="cpu usage high")
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)


class TestFingerprintEdgeCases:
    """Edge cases in fingerprint calculation."""

    def setup_method(self) -> None:
        self.dedup = _make_dedup()

    def test_empty_system_field(self) -> None:
        """system=None should not crash, just be empty string in hash."""
        a1 = _make_alert(system="")
        a2 = _make_alert(system="")
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)

    def test_empty_namespace_field(self) -> None:
        a1 = _make_alert(namespace=None)
        a2 = _make_alert(namespace=None)
        assert self.dedup.fingerprint(a1) == self.dedup.fingerprint(a2)

    def test_aliyun_uses_instance_id_not_pod(self) -> None:
        """Aliyun alerts use instance_id as the resource dimension."""
        a1 = _make_alert(
            source_type="aliyun",
            instance_id="i-aaa",
            pod_name=None,
        )
        a2 = _make_alert(
            source_type="aliyun",
            instance_id="i-bbb",
            pod_name=None,
        )
        assert self.dedup.fingerprint(a1) != self.dedup.fingerprint(a2)

    def test_fingerprint_length(self) -> None:
        alert = _make_alert()
        fp = self.dedup.fingerprint(alert)
        assert len(fp) == 16  # SHA256 truncated to 16 chars
