"""Analysis result models."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from langops.models.dedup import DedupInfo


class RootCause(BaseModel):
    """Root cause analysis result."""

    category: str = Field(..., description="Root cause category")
    description: str = Field(..., description="Detailed description")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence")
    related_metrics: list[str] = Field(default_factory=list, description="Related metrics")
    impact_analysis: str | None = Field(default=None, description="Impact analysis")


class SimilarCase(BaseModel):
    """Similar historical case."""

    case_id: str = Field(..., description="Case identifier")
    similarity_score: float = Field(..., ge=0, le=1, description="Similarity score")
    title: str = Field(..., description="Case title")
    root_cause: str = Field(..., description="Root cause summary")
    solution: str = Field(..., description="Solution applied")
    resolution_time: int | None = Field(default=None, description="Resolution time in minutes")


class RemediationSuggestion(BaseModel):
    """Remediation suggestion."""

    summary: str = Field(..., description="Suggestion summary")
    steps: list[str] = Field(default_factory=list, description="Action steps")
    commands: list[str] = Field(default_factory=list, description="CLI commands")
    risks: list[str] = Field(default_factory=list, description="Potential risks")
    rollback_plan: str | None = Field(default=None, description="Rollback plan")
    estimated_time: str = Field(default="unknown", description="Estimated fix time")


class AnalysisResult(BaseModel):
    """Complete analysis result."""

    alert_id: str = Field(..., description="Reference to original alert")
    trace_id: str = Field(..., description="Langfuse trace ID")
    root_cause: RootCause = Field(..., description="Root cause analysis")
    similar_cases: list[SimilarCase] = Field(default_factory=list, description="Similar cases")
    suggestion: RemediationSuggestion = Field(..., description="Remediation suggestion")
    impact_prediction: dict[str, Any] = Field(default_factory=dict, description="Impact prediction")
    processing_time_seconds: float = Field(..., description="Total processing time")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Analysis timestamp",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "alert_id": "alert-001",
                "trace_id": "trace-abc123",
                "root_cause": {
                    "category": "资源不足",
                    "description": "Pod CPU 资源不足，导致性能下降",
                    "confidence": 0.92,
                    "evidence": ["CPU使用率95%", "无CPU limit配置"],
                },
                "suggestion": {
                    "summary": "增加 Pod CPU limit 或扩容",
                    "steps": ["检查当前资源配置", "修改 deployment CPU limit"],
                    "commands": [
                        "kubectl set resources deployment/order-service --limits=cpu=1000m"
                    ],
                },
            }
        }
    )


class AnalysisResponse(BaseModel):
    """API response for ``POST /api/v1/alerts``.

    On success ``data`` contains the full ``AnalysisResult``.  When the alert is
    suppressed by noise-reduction, ``data`` is ``None`` and ``dedup.action`` is
    ``"suppress"``.  If a remediation plan was created, ``remediation_plan_id``
    is populated for the approval workflow.
    """

    success: bool = Field(..., description="Whether analysis was successful")
    data: AnalysisResult | None = Field(default=None, description="Analysis result")
    error: str | None = Field(default=None, description="Error message if failed")
    dedup: DedupInfo | None = Field(default=None, description="Noise reduction metadata")
    remediation_plan_id: str | None = Field(
        default=None,
        description="Remediation plan ID for approval workflow",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "description": "Successful analysis",
                    "value": {
                        "success": True,
                        "data": {
                            "alert_id": "alert-a1b2c3d4",
                            "trace_id": "trace-abc123",
                            "root_cause": {
                                "category": "资源不足",
                                "description": "Pod CPU 资源不足，导致性能下降",
                                "confidence": 0.92,
                                "evidence": ["CPU使用率95%", "无CPU limit配置"],
                            },
                            "similar_cases": [],
                            "suggestion": {
                                "summary": "增加 Pod CPU limit 或扩容",
                                "steps": [
                                    "检查当前资源配置",
                                    "修改 deployment CPU limit",
                                ],
                                "commands": [
                                    "kubectl set resources deployment/order-service --limits=cpu=1000m"
                                ],
                                "risks": [],
                                "estimated_time": "10 minutes",
                            },
                            "impact_prediction": {},
                            "processing_time_seconds": 12.34,
                        },
                        "error": None,
                        "dedup": {
                            "fingerprint": "fp-abc123",
                            "action": "process",
                            "occurrence_count": 1,
                            "window_seconds": 900,
                            "message": "First occurrence, proceeding with analysis",
                        },
                        "remediation_plan_id": "plan-a1b2c3d4",
                    },
                },
                {
                    "description": "Suppressed by dedup",
                    "value": {
                        "success": True,
                        "data": None,
                        "error": None,
                        "dedup": {
                            "fingerprint": "fp-abc123",
                            "action": "suppress",
                            "occurrence_count": 3,
                            "window_seconds": 900,
                            "message": "Duplicate alert within 900s window, suppressed",
                        },
                        "remediation_plan_id": None,
                    },
                },
            ]
        }
    )
