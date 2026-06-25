"""Predictive operations models."""

from typing import Any

from pydantic import BaseModel, Field


class MetricForecast(BaseModel):
    """Forecast for a single metric series."""

    metric: str = Field(..., description="Metric identifier")
    current: float = Field(..., description="Latest observed value")
    trend: str = Field(..., description="rising | falling | stable")
    slope_per_hour: float = Field(..., description="Estimated change per hour")
    forecast_value: float | None = Field(default=None, description="Forecast at horizon")
    risk_level: str = Field(..., description="low | medium | high | critical")
    summary: str = Field(..., description="Human-readable trend summary")


class ImpactPrediction(BaseModel):
    """Predicted impact and capacity outlook."""

    affected_service: str | None = Field(default=None, description="Primary affected service")
    horizon_hours: int = Field(default=24, description="Forecast horizon in hours")
    overall_risk: str = Field(default="low", description="Aggregated risk level")
    forecasts: list[MetricForecast] = Field(default_factory=list)
    recommendation: str = Field(..., description="Proactive recommendation")
    confidence: float = Field(default=0.5, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PredictRequest(BaseModel):
    """Proactive capacity prediction request."""

    resource_type: str = Field(default="kubernetes", description="kubernetes | ecs | rds")
    system: str = Field(default="prod-cluster", description="Cluster or region")
    namespace: str | None = Field(default=None, description="K8s namespace")
    pod_name: str | None = Field(default=None, description="K8s pod name")
    instance_id: str | None = Field(default=None, description="Cloud instance ID")
    service: str | None = Field(default=None, description="Service name")
    horizon_hours: int = Field(default=24, ge=1, le=168)
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {"cpu": 0.9, "memory": 0.9},
        description="Risk thresholds by metric keyword",
    )


class PredictResponse(BaseModel):
    """API response for prediction."""

    success: bool
    data: ImpactPrediction | None = None
    error: str | None = None
