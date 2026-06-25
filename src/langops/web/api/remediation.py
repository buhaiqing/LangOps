"""Remediation approval and execution API."""

from fastapi import APIRouter, Depends, HTTPException, status

from langops.models import (
    RemediationExecuteRequest,
    RemediationExecuteResponse,
    RemediationPlan,
    RemediationRejectRequest,
    RemediationStatus,
)
from langops.services.remediation_executor import RemediationExecutor, RemediationRegistry
from langops.web.dependencies import get_remediation_executor, get_remediation_registry

router = APIRouter(prefix="/remediation", tags=["remediation"])


@router.get(
    "",
    response_model=list[RemediationPlan],
    summary="List pending remediation plans",
)
async def list_pending_plans(
    registry: RemediationRegistry = Depends(get_remediation_registry),
) -> list[RemediationPlan]:
    """List remediation plans awaiting approval."""
    return registry.list_pending()


@router.get(
    "/{plan_id}",
    response_model=RemediationPlan,
    summary="Get remediation plan",
)
async def get_plan(
    plan_id: str,
    registry: RemediationRegistry = Depends(get_remediation_registry),
) -> RemediationPlan:
    """Get a remediation plan by ID."""
    plan = registry.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return plan


@router.post(
    "/{plan_id}/execute",
    response_model=RemediationExecuteResponse,
    summary="Approve and execute remediation",
)
async def execute_plan(
    plan_id: str,
    request: RemediationExecuteRequest,
    registry: RemediationRegistry = Depends(get_remediation_registry),
    executor: RemediationExecutor = Depends(get_remediation_executor),
) -> RemediationExecuteResponse:
    """Approve and execute (or dry-run) a low-risk remediation plan."""
    plan = registry.get(plan_id)
    if plan is None:
        return RemediationExecuteResponse(success=False, plan=None, error="Plan not found")

    try:
        updated = await executor.approve_and_execute(plan, request)
        registry.save(updated)
        success = updated.status in (RemediationStatus.EXECUTED, RemediationStatus.DRY_RUN)
        error = None if success else updated.execution_output
        return RemediationExecuteResponse(success=success, plan=updated, error=error)
    except ValueError as exc:
        return RemediationExecuteResponse(success=False, plan=plan, error=str(exc))
    except Exception as exc:
        return RemediationExecuteResponse(success=False, plan=plan, error=str(exc))


@router.post(
    "/{plan_id}/reject",
    response_model=RemediationExecuteResponse,
    summary="Reject remediation plan",
)
async def reject_plan(
    plan_id: str,
    request: RemediationRejectRequest,
    registry: RemediationRegistry = Depends(get_remediation_registry),
    executor: RemediationExecutor = Depends(get_remediation_executor),
) -> RemediationExecuteResponse:
    """Reject a pending remediation plan."""
    plan = registry.get(plan_id)
    if plan is None:
        return RemediationExecuteResponse(success=False, plan=None, error="Plan not found")

    try:
        updated = executor.reject(plan, request.rejected_by, request.reason)
        registry.save(updated)
        return RemediationExecuteResponse(success=True, plan=updated, error=None)
    except ValueError as exc:
        return RemediationExecuteResponse(success=False, plan=plan, error=str(exc))
