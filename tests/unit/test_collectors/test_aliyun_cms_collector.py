"""Aliyun CMS collector tests."""

import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from langops.collectors import AliyunCmsCollector, BaseCollector
from langops.models import Alert, AlertCategory, AlertSeverity, AlertSource


def _aliyun_alert(
    *,
    instance_id: str | None = "i-abc123",
    resource_type: str | None = "ecs",
) -> Alert:
    return Alert(
        id="alert-ecs-001",
        title="ECS CPU过高",
        description="CPU > 90%",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="aliyun",
            system="cn-hangzhou",
            instance_id=instance_id,
            resource_type=resource_type,
        ),
    )


def test_aliyun_collector_is_base_collector() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    assert isinstance(collector, BaseCollector)
    assert collector.name == "aliyun_cms"


def test_parse_datapoints_returns_no_data_for_empty_input() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    assert collector._parse_datapoints(None) == {"status": "no_data", "points": []}
    assert collector._parse_datapoints("[]") == {"status": "no_data", "points": []}


def test_parse_datapoints_extracts_latest_average() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    raw = json.dumps(
        [
            {"timestamp": 1700000000000, "Average": 55.0},
            {"timestamp": 1700000060000, "Average": 92.5},
        ]
    )
    parsed = collector._parse_datapoints(raw)
    assert parsed["status"] == "success"
    assert parsed["points_count"] == 2
    assert parsed["current_value"] == 92.5
    assert parsed["current_timestamp"] == 1700000060000


@pytest.mark.asyncio
async def test_health_check_false_without_credentials() -> None:
    collector = AliyunCmsCollector({"access_key_id": "", "access_key_secret": ""})
    assert await collector.health_check() is False


@pytest.mark.asyncio
async def test_health_check_true_when_client_can_be_created() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    collector._get_client = MagicMock(return_value=MagicMock())
    assert await collector.health_check() is True


@pytest.mark.asyncio
async def test_collect_returns_error_when_instance_id_missing() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    result = await collector.collect(_aliyun_alert(instance_id=None))
    assert result == {"error": "Missing instance_id for Aliyun metrics"}


@pytest.mark.asyncio
async def test_collect_ecs_metrics_queries_all_ecs_metrics() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    success = {"status": "success", "current_value": 80.0}

    with patch.object(collector, "_query_metric", return_value=success) as mock_query:
        results = await collector.collect_ecs_metrics("i-abc123", timedelta(minutes=30))

    assert len(results) == 6
    assert results["CPUUtilization"] == success
    assert mock_query.await_count == 6
    mock_query.assert_any_await(
        namespace="acs_ecs_dashboard",
        metric_name="CPUUtilization",
        instance_id="i-abc123",
        time_window=timedelta(minutes=30),
    )


@pytest.mark.asyncio
async def test_collect_rds_metrics_queries_rds_namespace() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    success = {"status": "success", "current_value": 70.0}

    with patch.object(collector, "_query_metric", return_value=success) as mock_query:
        results = await collector.collect_rds_metrics("rm-abc123", timedelta(minutes=15))

    assert len(results) == 5
    assert results["CpuUsage"] == success
    mock_query.assert_any_await(
        namespace="acs_rds_dashboard",
        metric_name="CpuUsage",
        instance_id="rm-abc123",
        time_window=timedelta(minutes=15),
    )


@pytest.mark.asyncio
async def test_collect_routes_to_rds_when_resource_type_is_rds() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    expected = {"CpuUsage": {"status": "success"}}

    with patch.object(collector, "collect_rds_metrics", return_value=expected) as mock_rds:
        result = await collector.collect(_aliyun_alert(resource_type="rds"))

    mock_rds.assert_awaited_once()
    assert result == expected


@pytest.mark.asyncio
async def test_query_metric_sync_calls_cms_client() -> None:
    collector = AliyunCmsCollector({"access_key_id": "ak", "access_key_secret": "sk"})
    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.datapoints = json.dumps([{"timestamp": 1, "Average": 88.0}])
    mock_client.describe_metric_list.return_value = MagicMock(body=mock_body)
    collector._client = mock_client

    result = collector._query_metric_sync(
        namespace="acs_ecs_dashboard",
        metric_name="CPUUtilization",
        instance_id="i-abc123",
        time_window=timedelta(minutes=30),
    )

    assert result["status"] == "success"
    assert result["current_value"] == 88.0
    mock_client.describe_metric_list.assert_called_once()
