"""Prometheus collector tests."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.collectors import BaseCollector, PrometheusCollector
from langops.models import Alert, AlertCategory, AlertSeverity, AlertSource


def _k8s_alert(*, namespace: str | None = "production", pod_name: str | None = "app-pod") -> Alert:
    return Alert(
        id="alert-001",
        title="CPU high",
        description="CPU > 90%",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="prod-cluster",
            namespace=namespace,
            pod_name=pod_name,
        ),
    )


def test_prometheus_collector_is_base_collector() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    assert isinstance(collector, BaseCollector)
    assert collector.name == "prometheus"


def test_parse_metric_data_returns_no_data_for_empty_result() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    parsed = collector._parse_metric_data([])
    assert parsed == {"status": "no_data"}


def test_parse_metric_data_extracts_latest_value() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    raw = [
        {
            "metric": {"container": "app"},
            "values": [[1700000000.0, "0.5"], [1700000015.0, "0.8"]],
        }
    ]
    parsed = collector._parse_metric_data(raw)
    assert parsed["status"] == "success"
    assert parsed["series_count"] == 1
    assert parsed["series"][0]["current_value"] == "0.8"


@pytest.mark.asyncio
async def test_health_check_returns_true_when_prometheus_is_healthy() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090", "timeout": 5})

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.get.return_value = mock_response
    collector._get_session = AsyncMock(return_value=mock_session)

    assert await collector.health_check() is True
    mock_session.get.assert_called_once_with("http://prometheus:9090/-/healthy")


@pytest.mark.asyncio
async def test_health_check_returns_false_on_connection_error() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    collector._get_session = AsyncMock(side_effect=ConnectionError("down"))

    assert await collector.health_check() is False


@pytest.mark.asyncio
async def test_collect_k8s_requires_namespace_and_pod() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    alert = _k8s_alert(namespace=None, pod_name="app-pod")

    result = await collector.collect(alert, timedelta(minutes=5))

    assert result["error"] == "Missing namespace or pod_name for K8s metrics"


@pytest.mark.asyncio
async def test_collect_k8s_queries_core_metrics() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    collector._query_range = AsyncMock(return_value=[])

    result = await collector.collect(_k8s_alert(), timedelta(minutes=10))

    assert collector._query_range.await_count == 6
    assert "cpu_usage" in result
    assert "memory_usage" in result
    assert result["cpu_usage"] == {"status": "no_data"}


@pytest.mark.asyncio
async def test_close_closes_open_session() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    mock_session = AsyncMock()
    mock_session.closed = False
    collector._session = mock_session

    await collector.close()

    mock_session.close.assert_awaited_once()


def test_parse_instant_result_extracts_value() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    parsed = collector._parse_instant_result(
        [{"metric": {"pod": "app"}, "value": [1700000000.0, "0.75"]}]
    )
    assert parsed[0]["value"] == "0.75"
    assert parsed[0]["metric"]["pod"] == "app"


@pytest.mark.asyncio
async def test_query_instant_calls_prometheus_api() -> None:
    collector = PrometheusCollector({"url": "http://prometheus:9090"})
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value={
            "status": "success",
            "data": {
                "result": [{"metric": {"job": "api"}, "value": [1.0, "1"]}],
            },
        }
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.get.return_value = mock_response
    collector._get_session = AsyncMock(return_value=mock_session)

    result = await collector.query_instant("up")

    assert len(result) == 1
    mock_session.get.assert_called_once()
    assert mock_session.get.call_args[0][0] == "http://prometheus:9090/api/v1/query"
