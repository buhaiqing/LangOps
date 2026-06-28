"""Webhook payload and response models.

Callback 数据结构定义
────────────────────
- AlertmanagerWebhookPayload — Prometheus AlertManager v4 推送格式
- AliyunCmsCallbackPayload  — 阿里云云监控(Cloud Monitor)报警回调格式
"""

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


class AliyunCmsCallbackPayload(BaseModel):
    """阿里云云监控(Cloud Monitor)报警推送回调的数据结构。

    当云监控中配置的报警规则被触发时，CMS 会 POST JSON 到注册的 URL。
    字段说明见 https://www.alibabacloud.com/help/zh/cms/user-guide/use-callback-urls
    """

    model_config = ConfigDict(extra="ignore")

    alertName: str = Field(default="", description="报警规则名称，如 'CPU使用率过高'")
    alertState: str = Field(default="ALERT", description="报警状态：ALERT（告警）| OK（恢复）")
    curValue: str = Field(default="", description="当前监控值，如 '95.5'")
    dimensions: str = Field(default="", description="维度 JSON 字符串，如 '{\"instanceId\":\"i-xxxxx\"}'")
    expression: str = Field(default="", description="报警表达式，如 'Average > 90'")
    instanceName: str = Field(default="", description="实例名称或 ID")
    metricName: str = Field(default="", description="监控指标名，如 'CPUUtilization'")
    namespace: str = Field(default="", description="产品命名空间，如 'acs_ecs_dashboard'")
    regionId: str = Field(default="", description="地域 ID，如 'cn-hangzhou'")
    timestamp: str = Field(default="", description="报警时间戳(ms)")
    userId: str = Field(default="", description="阿里云账号 ID")
    level: str = Field(default="info", description="报警级别：critical | warning | info")
