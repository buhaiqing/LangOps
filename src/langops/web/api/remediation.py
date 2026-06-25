"""Remediation approval and execution API."""

from fastapi import APIRouter, Depends, HTTPException, status

from langops.core import get_logger
from langops.models import (
    RemediationExecuteRequest,
    RemediationExecuteResponse,
    RemediationPlan,
    RemediationRejectRequest,
    RemediationStatus,
)
from langops.services.remediation_executor import RemediationExecutor, RemediationRegistry
from langops.web.dependencies import get_remediation_executor, get_remediation_registry
from langops.web.metrics import remediation_actions_total

logger = get_logger(__name__)

router = APIRouter(prefix="/remediation", tags=["remediation"])


@router.get(
    "",
    response_model=list[RemediationPlan],
    summary="List pending remediation plans",
)
async def list_pending_plans(
    registry: RemediationRegistry = Depends(get_remediation_registry),
) -> list[RemediationPlan]:
    return await registry.list_pending()


@router.get(
    "/{plan_id}",
    response_model=RemediationPlan,
    summary="Get remediation plan",
)
async def get_plan(
    plan_id: str,
    registry: RemediationRegistry = Depends(get_remediation_registry),
) -> RemediationPlan:
    plan = await registry.get(plan_id)
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
    plan = await registry.get(plan_id)
    if plan is None:
        return RemediationExecuteResponse(success=False, plan=None, error="Plan not found")

    try:
        updated = await executor.approve_and_execute(plan, request)
        await registry.save(updated)
        success = updated.status in (RemediationStatus.EXECUTED, RemediationStatus.DRY_RUN)
        action = "execute" if not request.dry_run else "dry_run"
        remediation_actions_total.labels(
            action=action, status="success" if success else "failure"
        ).inc()
        logger.info(
            "Remediation executed",
            plan_id=plan_id,
            action=action,
            status=updated.status.value,
            approved_by=request.approved_by,
        )
        error = None if success else updated.execution_output
        return RemediationExecuteResponse(success=success, plan=updated, error=error)
    except ValueError as exc:
        remediation_actions_total.labels(action="execute", status="rejected").inc()
        logger.warning("Remediation rejected", plan_id=plan_id, reason=str(exc))
        return RemediationExecuteResponse(success=False, plan=plan, error=str(exc))
    except Exception as exc:
        remediation_actions_total.labels(action="execute", status="failure").inc()
        logger.error("Remediation execution failed", plan_id=plan_id, error=str(exc))
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
    plan = await registry.get(plan_id)
    if plan is None:
        return RemediationExecuteResponse(success=False, plan=None, error="Plan not found")

    try:
        updated = executor.reject(plan, request.rejected_by, request.reason)
        await registry.save(updated)
        remediation_actions_total.labels(action="reject", status="success").inc()
        logger.info(
            "Remediation rejected",
            plan_id=plan_id,
            rejected_by=request.rejected_by,
            reason=request.reason,
        )
        return RemediationExecuteResponse(success=True, plan=updated, error=None)
    except ValueError as exc:
        remediation_actions_total.labels(action="reject", status="failure").inc()
        logger.warning("Remediation reject failed", plan_id=plan_id, reason=str(exc))
        return RemediationExecuteResponse(success=False, plan=plan, error=str(exc))
