"""Aliyun Cloud Monitor (CMS) metrics collector."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from langops.collectors.base import COLLECTOR_RETRY, BaseCollector
from langops.core import get_logger
from langops.models import Alert

logger = get_logger(__name__)

ECS_METRICS = (
    "CPUUtilization",
    "memory_usedutilization",
    "DiskReadIOPS",
    "DiskWriteIOPS",
    "InternetInRate",
    "InternetOutRate",
)

RDS_METRICS = (
    "CpuUsage",
    "MemoryUsage",
    "IOPSUsage",
    "ConnectionUsage",
    "DiskUsage",
)


class AliyunCmsCollector(BaseCollector):
    """Collector for Alibaba Cloud Monitor metrics."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.access_key_id = str(config.get("access_key_id", ""))
        self.access_key_secret = str(config.get("access_key_secret", ""))
        self.region = str(config.get("region", "cn-hangzhou"))
        self.endpoint = str(config.get("endpoint", "metrics.aliyuncs.com"))
        self._client: Any = None

    @property
    def name(self) -> str:
        return "aliyun_cms"

    def _get_client(self) -> Any:
        """Create or return cached CMS SDK client."""
        if self._client is not None:
            return self._client

        from alibabacloud_cms20190101.client import Client as CmsClient
        from alibabacloud_tea_openapi import models as open_api_models

        cfg = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            region_id=self.region,
        )
        cfg.endpoint = self.endpoint
        self._client = CmsClient(cfg)
        return self._client

    async def health_check(self) -> bool:
        """Check if CMS collector is configured."""
        if not self.access_key_id or not self.access_key_secret:
            return False
        try:
            await asyncio.to_thread(self._get_client)
            return True
        except Exception as exc:
            logger.warning("Aliyun CMS health check failed", error=str(exc))
            return False

    @COLLECTOR_RETRY
    async def _do_collect(
        self,
        alert: Alert,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect CMS metrics for an Aliyun alert."""
        instance_id = alert.source.instance_id
        if not instance_id:
            return {"error": "Missing instance_id for Aliyun metrics"}

        resource_type = (alert.source.resource_type or "ecs").lower()
        if resource_type == "rds":
            return await self.collect_rds_metrics(instance_id, time_window)
        return await self.collect_ecs_metrics(instance_id, time_window)

    async def collect_ecs_metrics(
        self,
        instance_id: str,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect ECS instance metrics from CMS."""
        results: dict[str, Any] = {}
        for metric_name in ECS_METRICS:
            try:
                results[metric_name] = await self._query_metric(
                    namespace="acs_ecs_dashboard",
                    metric_name=metric_name,
                    instance_id=instance_id,
                    time_window=time_window,
                )
            except Exception as exc:
                logger.warning("Failed to query ECS metric", metric=metric_name, error=str(exc))
                results[metric_name] = {"error": str(exc)}
        return results

    async def collect_rds_metrics(
        self,
        instance_id: str,
        time_window: timedelta = timedelta(minutes=30),
    ) -> dict[str, Any]:
        """Collect RDS instance metrics from CMS."""
        results: dict[str, Any] = {}
        for metric_name in RDS_METRICS:
            try:
                results[metric_name] = await self._query_metric(
                    namespace="acs_rds_dashboard",
                    metric_name=metric_name,
                    instance_id=instance_id,
                    time_window=time_window,
                )
            except Exception as exc:
                logger.warning("Failed to query RDS metric", metric=metric_name, error=str(exc))
                results[metric_name] = {"error": str(exc)}
        return results

    async def _query_metric(
        self,
        namespace: str,
        metric_name: str,
        instance_id: str,
        time_window: timedelta,
    ) -> dict[str, Any]:
        """Query a single CMS metric (async wrapper)."""
        return await asyncio.to_thread(
            self._query_metric_sync,
            namespace,
            metric_name,
            instance_id,
            time_window,
        )

    def _query_metric_sync(
        self,
        namespace: str,
        metric_name: str,
        instance_id: str,
        time_window: timedelta,
    ) -> dict[str, Any]:
        """Query a single CMS metric via SDK."""
        from alibabacloud_cms20190101 import models as cms_models

        end_time = datetime.now(UTC)
        start_time = end_time - time_window
        request = cms_models.DescribeMetricListRequest(
            namespace=namespace,
            metric_name=metric_name,
            dimensions=json.dumps([{"instanceId": instance_id}]),
            start_time=str(int(start_time.timestamp() * 1000)),
            end_time=str(int(end_time.timestamp() * 1000)),
            period="60",
        )
        response = self._get_client().describe_metric_list(request)
        datapoints = response.body.datapoints if response.body else None
        return self._parse_datapoints(datapoints)

    def _parse_datapoints(self, datapoints: str | None) -> dict[str, Any]:
        """Parse CMS datapoints JSON string into a readable structure."""
        if not datapoints:
            return {"status": "no_data", "points": []}

        try:
            points = json.loads(datapoints)
        except json.JSONDecodeError:
            return {"status": "parse_error", "raw": datapoints}

        if not isinstance(points, list) or not points:
            return {"status": "no_data", "points": []}

        latest = points[-1]
        current_value = latest.get("Average")
        if current_value is None:
            current_value = latest.get("Value", latest.get("Maximum"))

        return {
            "status": "success",
            "points_count": len(points),
            "points": points,
            "current_value": current_value,
            "current_timestamp": latest.get("timestamp"),
        }
