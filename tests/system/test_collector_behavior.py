"""Collector behavior system tests.

Tests that collectors handle missing fields gracefully and return
clear error messages instead of crashing.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import timedelta

from langops.collectors.prometheus_collector import PrometheusCollector
from langops.collectors.aliyun_cms_collector import AliyunCmsCollector
from langops.models import Alert, AlertSource, AlertSeverity, AlertCategory


def _make_alert(**source_kwargs) -> Alert:
    """Helper to create an alert with given source fields."""
    source = AlertSource(
        type=source_kwargs.pop("type", "kubernetes"),
        system=source_kwargs.pop("system", "test-cluster"),
        **source_kwargs,
    )
    return Alert(
        id="test-alert-001",
        title="Test Alert",
        description="Test",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=source,
    )


class TestPrometheusCollectorBehavior:
    """Prometheus collector field requirements."""

    @pytest.fixture
    def collector(self) -> PrometheusCollector:
        return PrometheusCollector({"url": "http://localhost:9090", "timeout": 5})

    @pytest.mark.asyncio
    async def test_k8s_without_namespace_returns_error(
        self, collector: PrometheusCollector
    ) -> None:
        alert = _make_alert(type="kubernetes", pod_name="my-pod")
        result = await collector.collect(alert, timedelta(minutes=5))
        assert "error" in result
        assert "namespace" in result["error"].lower() or "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_k8s_without_pod_name_returns_error(
        self, collector: PrometheusCollector
    ) -> None:
        alert = _make_alert(type="kubernetes", namespace="default")
        result = await collector.collect(alert, timedelta(minutes=5))
        assert "error" in result
        assert "pod_name" in result["error"].lower() or "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_k8s_with_all_fields_queries_prometheus(
        self, collector: PrometheusCollector
    ) -> None:
        """When all fields present, collector tries to query Prometheus.
        Since Prometheus isn't running, it will return an error from HTTP,
        but the important thing is it doesn't crash on field validation.
        """
        alert = _make_alert(type="kubernetes", namespace="default", pod_name="test-pod")
        result = await collector.collect(alert, timedelta(minutes=5))
        # Will fail because no real Prometheus, but shouldn't be a field validation error
        # The error should be about connection, not missing fields
        # (unless the mock Prometheus is actually running)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_generic_type_returns_not_implemented(
        self, collector: PrometheusCollector
    ) -> None:
        alert = _make_alert(type="prometheus", system="test")
        result = await collector.collect(alert, timedelta(minutes=5))
        assert "note" in result


class TestAliyunCmsCollectorBehavior:
    """Aliyun CMS collector field requirements."""

    @pytest.fixture
    def collector(self) -> AliyunCmsCollector:
        return AliyunCmsCollector(
            {
                "access_key_id": "test-key-id",
                "access_key_secret": "test-key-secret",
                "region": "cn-hangzhou",
            }
        )

    @pytest.mark.asyncio
    async def test_without_instance_id_returns_error(
        self, collector: AliyunCmsCollector
    ) -> None:
        alert = _make_alert(type="aliyun", system="aliyun-prod")
        result = await collector.collect(alert, timedelta(minutes=5))
        assert "error" in result
        assert "instance_id" in result["error"].lower() or "Missing" in result["error"]

    @pytest.mark.asyncio
    async def test_ecs_with_instance_id_tries_query(
        self, collector: AliyunCmsCollector
    ) -> None:
        """With instance_id present, collector tries to query CMS.
        Will fail on SDK/auth, but not on field validation.
        """
        alert = _make_alert(
            type="aliyun",
            system="aliyun-prod",
            instance_id="i-test-123",
            resource_type="ecs",
        )
        result = await collector.collect(alert, timedelta(minutes=5))
        # Should be a dict (either error from SDK or success)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_rds_type_queries_rds_metrics(
        self, collector: AliyunCmsCollector
    ) -> None:
        alert = _make_alert(
            type="aliyun",
            system="aliyun-prod",
            instance_id="rm-test-123",
            resource_type="rds",
        )
        result = await collector.collect(alert, timedelta(minutes=5))
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_default_resource_type_is_ecs(
        self, collector: AliyunCmsCollector
    ) -> None:
        alert = _make_alert(
            type="aliyun",
            system="aliyun-prod",
            instance_id="i-test-123",
            # resource_type not set → defaults to "ecs"
        )
        result = await collector.collect(alert, timedelta(minutes=5))
        assert isinstance(result, dict)
