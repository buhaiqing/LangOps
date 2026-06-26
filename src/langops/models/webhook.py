"""Webhook payload and response models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from langops.models.analysis import AnalysisResult


class AlertmanagerAlert(BaseModel):
    """Single alert inside an AlertManager webhook payload."""

    model_config = ConfigDict(extra="ignore")

    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str = ""
    endsAt: str = ""
    generatorURL: str = ""
    fingerprint: str = ""


class AlertmanagerWebhookPayload(BaseModel):
    """AlertManager v4 webhook payload."""

    model_config = ConfigDict(extra="ignore")

    version: str = "4"
    groupKey: str = ""
    status: str = ""
    receiver: str = ""
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    alerts: list[AlertmanagerAlert] = Field(..., min_length=1)


class WebhookAlertResult(BaseModel):
    """Per-alert result inside a webhook batch response."""

    alert_id: str | None = None
    success: bool
    data: AnalysisResult | None = None
    error: str | None = None
    dedup: dict[str, Any] | None = None
    remediation_plan_id: str | None = None


class WebhookBatchResponse(BaseModel):
    """Response for POST /api/v1/webhooks/{source}."""

    success: bool
    received: int
    results: list[WebhookAlertResult] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
