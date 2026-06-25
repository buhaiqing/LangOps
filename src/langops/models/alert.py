"""Alert data models."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertCategory(str, Enum):
    """Alert categories."""

    RESOURCE = "resource"
    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    SECURITY = "security"


class AlertSource(BaseModel):
    """Alert source information."""

    model_config = ConfigDict(extra="allow")

    type: str = Field(..., description="Source type: prometheus, aliyun, kubernetes")
    system: str = Field(..., description="System or cluster name")
    service: str | None = Field(default=None, description="Service name")
    namespace: str | None = Field(default=None, description="K8s namespace")
    pod_name: str | None = Field(default=None, description="Pod name")
    instance_id: str | None = Field(default=None, description="Cloud instance ID")
    resource_type: str | None = Field(default=None, description="Resource type: ecs, rds, slb")


class Alert(BaseModel):
    """Standardized alert model."""

    id: str = Field(..., description="Unique alert identifier")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    severity: AlertSeverity = Field(..., description="Alert severity")
    category: AlertCategory = Field(..., description="Alert category")
    source: AlertSource = Field(..., description="Alert source")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Alert timestamp")
    metric_data: dict[str, Any] = Field(default_factory=dict, description="Raw metric data")
    log_snippets: list[str] = Field(default_factory=list, description="Related log snippets")
    related_events: list[str] = Field(default_factory=list, description="Related event IDs")
    context: dict[str, Any] = Field(default_factory=dict, description="Additional context")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: object) -> object:
        """Normalize severity string to enum."""
        if isinstance(value, str):
            normalized = value.lower()
            mapping = {
                "critical": AlertSeverity.CRITICAL,
                "high": AlertSeverity.HIGH,
                "medium": AlertSeverity.MEDIUM,
                "low": AlertSeverity.LOW,
                "info": AlertSeverity.INFO,
                "warning": AlertSeverity.MEDIUM,
            }
            return mapping.get(normalized, AlertSeverity.INFO)
        return value

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "alert-001",
                "title": "CPU使用率过高",
                "description": "order-service Pod CPU使用率超过90%",
                "severity": "critical",
                "category": "resource",
                "source": {
                    "type": "kubernetes",
                    "system": "prod-cluster",
                    "namespace": "production",
                    "pod_name": "order-service-abc123",
                },
                "metric_data": {
                    "cpu_usage_percent": 95.5,
                    "memory_usage_percent": 78.2,
                },
            }
        }
    )


class AlertCreate(BaseModel):
    """Alert creation request."""

    title: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    source: AlertSource
    metric_data: dict[str, Any] = Field(default_factory=dict)
    log_snippets: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class AlertContext(BaseModel):
    """Enriched alert context for analysis."""

    alert: Alert
    metrics: dict[str, Any] = Field(default_factory=dict, description="Collected metrics")
    logs: list[str] = Field(default_factory=list, description="Collected logs")
    events: list[dict[str, Any]] = Field(default_factory=list, description="Related events")
    time_range_minutes: int = Field(default=30, description="Context time range")
