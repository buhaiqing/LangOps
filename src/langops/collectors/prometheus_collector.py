"""Prometheus metrics collector."""

from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp

from langops.collectors.base import COLLECTOR_RETRY, BaseCollector
from langops.core import get_logger
from langops.models import Alert

logger = get_logger(__name__)


class PrometheusCollector(BaseCollector):
    """Collector for Prometheus metrics."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("url", "http://localhost:9090")
        self.timeout = config.get("timeout", 10)
        self._session: aiohttp.ClientSession | None = None

    @property
    def name(self) -> str:
        return "prometheus"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def health_check(self) -> bool:
        """Check Prometheus health."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/-/healthy") as resp:
                return resp.status == 200
        except Exception as exc:
            logger.warning("Prometheus health check failed", error=str(exc))
            return False

    @COLLECTOR_RETRY
    async def _do_collect(
        self,
        alert: Alert,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect Prometheus metrics for an alert."""
        if alert.source.type == "kubernetes":
            return await self._collect_k8s_metrics(alert, time_window)
        return await self._collect_generic_metrics(alert, time_window)

    async def _collect_k8s_metrics(
        self,
        alert: Alert,
        time_window: timedelta,
    ) -> dict[str, Any]:
        """Collect Kubernetes pod metrics."""
        namespace = alert.source.namespace
        pod_name = alert.source.pod_name

        if not namespace or not pod_name:
            return {"error": "Missing namespace or pod_name for K8s metrics"}

        end_time = datetime.now(UTC)
        start_time = end_time - time_window

        queries = {
            "cpu_usage": f"""
                sum(rate(container_cpu_usage_seconds_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m])) by (container)
            """,
            "memory_usage": f"""
                container_memory_usage_bytes{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "memory_limit": f"""
                container_spec_memory_limit_bytes{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "restart_count": f"""
                kube_pod_container_status_restarts_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "network_receive_errors": f"""
                sum(rate(container_network_receive_errors_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m]))
            """,
            "network_transmit_errors": f"""
                sum(rate(container_network_transmit_errors_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m]))
            """,
        }

        results: dict[str, Any] = {}
        for metric_name, query in queries.items():
            try:
                data = await self._query_range(query, start_time, end_time)
                results[metric_name] = self._parse_metric_data(data)
            except Exception as exc:
                logger.warning("Failed to query metric", metric=metric_name, error=str(exc))
                results[metric_name] = {"error": str(exc)}
        return results

    async def _collect_generic_metrics(
        self,
        alert: Alert,
        time_window: timedelta,
    ) -> dict[str, Any]:
        """Collect generic metrics based on alert labels."""
        _ = alert, time_window
        return {"note": "Generic metric collection not yet implemented"}

    async def query_instant(self, query: str) -> list[dict[str, Any]]:
        """Execute PromQL instant query."""
        session = await self._get_session()
        params = {"query": query.strip()}
        url = f"{self.base_url}/api/v1/query"

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Prometheus query failed: {resp.status} - {text}")

            data = await resp.json()
            if data.get("status") != "success":
                raise RuntimeError(f"Prometheus error: {data.get('error', 'Unknown')}")

            result = data.get("data", {}).get("result", [])
            if not isinstance(result, list):
                return []
            return self._parse_instant_result(result)

    def _parse_instant_result(self, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Parse Prometheus instant query result."""
        parsed: list[dict[str, Any]] = []
        for series in result:
            metric = series.get("metric", {})
            value = series.get("value", [])
            entry: dict[str, Any] = {"metric": metric}
            if len(value) == 2:
                entry["timestamp"] = float(value[0])
                entry["value"] = value[1]
            parsed.append(entry)
        return parsed

    async def _query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s",
    ) -> list[dict[str, Any]]:
        """Execute PromQL range query."""
        session = await self._get_session()
        params: dict[str, str | float] = {
            "query": query.strip(),
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step,
        }
        url = f"{self.base_url}/api/v1/query_range"

        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Prometheus query failed: {resp.status} - {text}")

            data = await resp.json()
            if data.get("status") != "success":
                raise RuntimeError(f"Prometheus error: {data.get('error', 'Unknown')}")

            result = data.get("data", {}).get("result", [])
            if not isinstance(result, list):
                return []
            return result

    def _parse_metric_data(self, result: list[dict[str, Any]]) -> dict[str, Any]:
        """Parse Prometheus query result into readable format."""
        if not result:
            return {"status": "no_data"}

        parsed: dict[str, Any] = {
            "status": "success",
            "series_count": len(result),
            "series": [],
        }

        for series in result:
            metric_info: dict[str, Any] = {
                "metric": series.get("metric", {}),
                "values": [],
            }
            for value in series.get("values", []):
                timestamp, val = value
                metric_info["values"].append({"timestamp": float(timestamp), "value": val})

            if metric_info["values"]:
                latest = metric_info["values"][-1]
                metric_info["current_value"] = latest["value"]
                metric_info["current_timestamp"] = latest["timestamp"]

            parsed["series"].append(metric_info)

        return parsed

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
