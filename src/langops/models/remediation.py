"""Remediation execution models."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class RemediationStatus(str, Enum):
    """Remediation plan lifecycle status."""

    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    DRY_RUN = "dry_run"
    EXECUTED = "executed"
    FAILED = "failed"


class RemediationPlan(BaseModel):
    """Actionable remediation plan awaiting approval."""

    plan_id: str = Field(..., description="Plan identifier")
    alert_id: str = Field(..., description="Source alert ID")
    trace_id: str = Field(..., description="Langfuse trace ID")
    summary: str = Field(..., description="Remediation summary")
    commands: list[str] = Field(default_factory=list, description="Proposed commands")
    risks: list[str] = Field(default_factory=list, description="Known risks")
    rollback_plan: str | None = Field(default=None, description="Rollback guidance")
    risk_level: str = Field(..., description="low | medium | high")
    status: RemediationStatus = Field(default=RemediationStatus.PENDING_APPROVAL)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_by: str | None = Field(default=None)
    execution_output: str | None = Field(default=None)


class RemediationExecuteRequest(BaseModel):
    """Request to approve and optionally execute a remediation plan."""

    approved_by: str = Field(..., min_length=1, description="Approver identity")
    confirm: bool = Field(..., description="Must be true to proceed")
    dry_run: bool = Field(default=False, description="Simulate execution without running commands")


class RemediationExecuteResponse(BaseModel):
    """Response for remediation approval/execution."""

    success: bool
    plan: RemediationPlan | None = None
    error: str | None = None


class RemediationRejectRequest(BaseModel):
    """Reject a remediation plan."""

    rejected_by: str = Field(..., min_length=1)
    reason: str | None = None
