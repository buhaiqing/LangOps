"""Predictive operations API routes."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status

from langops.agent.predictive_engine import PredictiveEngine
from langops.collectors import AliyunCmsCollector, PrometheusCollector
from langops.models import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertSource,
    PredictRequest,
    PredictResponse,
)
from langops.web.dependencies import (
    get_aliyun_collector,
    get_predictive_engine,
    get_prometheus_collector,
)

router = APIRouter(prefix="/predict", tags=["predict"])


def _alert_from_request(request: PredictRequest) -> Alert:
    if request.resource_type == "kubernetes":
        source = AlertSource(
            type="kubernetes",
            system=request.system,
            namespace=request.namespace,
            pod_name=request.pod_name,
            service=request.service,
        )
    else:
        source = AlertSource(
            type="aliyun",
            system=request.system,
            instance_id=request.instance_id,
            resource_type=request.resource_type,
            service=request.service,
        )

    return Alert(
        id=f"predict-{datetime.now(UTC).timestamp():.0f}",
        title="容量预测",
        description="Proactive capacity prediction",
        severity=AlertSeverity.MEDIUM,
        category=AlertCategory.RESOURCE,
        source=source,
    )


async def _collect_metrics(
    request: PredictRequest,
    prometheus: PrometheusCollector | None,
    aliyun: AliyunCmsCollector | None,
) -> dict:
    alert = _alert_from_request(request)
    if alert.source.type == "kubernetes" and prometheus:
        return await prometheus.collect(alert, time_window=timedelta(hours=6))
    if alert.source.type == "aliyun" and aliyun:
        return await aliyun.collect(alert, time_window=timedelta(hours=6))
    return {"error": "No collector available for the requested resource type"}


@router.post(
    "",
    response_model=PredictResponse,
    status_code=status.HTTP_200_OK,
    summary="Proactive capacity prediction",
    description="Collect metrics and forecast resource trends.",
)
async def predict_capacity(
    request: PredictRequest,
    engine: PredictiveEngine = Depends(get_predictive_engine),
    prometheus: PrometheusCollector | None = Depends(get_prometheus_collector),
    aliyun: AliyunCmsCollector | None = Depends(get_aliyun_collector),
) -> PredictResponse:
    """Run predictive analysis for a resource."""
    try:
        metrics = await _collect_metrics(request, prometheus, aliyun)
        if metrics.get("error") and len(metrics) == 1:
            return PredictResponse(success=False, data=None, error=str(metrics["error"]))

        prediction = await engine.predict_from_metrics(
            metrics,
            horizon_hours=request.horizon_hours,
            service=request.service,
            resource_label=request.pod_name or request.instance_id,
            thresholds=request.thresholds,
        )
        return PredictResponse(success=True, data=prediction, error=None)
    except Exception as exc:
        return PredictResponse(success=False, data=None, error=str(exc))
