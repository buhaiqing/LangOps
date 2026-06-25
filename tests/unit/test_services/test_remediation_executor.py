"""Remediation executor tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from langops.models import (
    AnalysisResult,
    RemediationExecuteRequest,
    RemediationPlan,
    RemediationStatus,
    RemediationSuggestion,
    RootCause,
)
from langops.services.remediation_executor import (
    RemediationExecutor,
    RemediationRegistry,
    assess_command_risk,
    is_allowed_command,
)
from langops.storage.models import Base
from langops.storage.sql import SqlRemediationRepository


def _repo():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


def test_is_allowed_command_accepts_kubectl_scale() -> None:
    assert is_allowed_command("kubectl scale deployment/order --replicas=3")


def test_is_allowed_command_blocks_delete() -> None:
    assert not is_allowed_command("kubectl delete pod order-abc")


def test_assess_command_risk_low_for_allowlisted_commands() -> None:
    cmds = ["kubectl scale deployment/order --replicas=3"]
    assert assess_command_risk(cmds) == "low"


@pytest.mark.asyncio
async def test_registry_creates_plan_from_analysis() -> None:
    registry = RemediationRegistry(repo=_repo())
    result = AnalysisResult(
        alert_id="alert-1",
        trace_id="trace-1",
        root_cause=RootCause(category="资源不足", description="CPU 高", confidence=0.9),
        suggestion=RemediationSuggestion(
            summary="扩容",
            commands=["kubectl scale deployment/order --replicas=3"],
        ),
        processing_time_seconds=1.0,
    )

    plan = await registry.create_from_analysis(result)
    assert plan.plan_id.startswith("plan-")
    assert plan.risk_level == "low"
    assert plan.status == RemediationStatus.PENDING_APPROVAL


@pytest.mark.asyncio
async def test_executor_dry_run_does_not_execute_commands() -> None:
    executor = RemediationExecutor(execution_enabled=True)
    plan = RemediationPlan(
        plan_id="plan-1",
        alert_id="alert-1",
        trace_id="trace-1",
        summary="扩容",
        commands=["kubectl scale deployment/order --replicas=3"],
        risk_level="low",
    )

    updated = await executor.approve_and_execute(
        plan,
        RemediationExecuteRequest(approved_by="ops-user", confirm=True, dry_run=True),
    )

    assert updated.status == RemediationStatus.DRY_RUN
    assert "kubectl scale" in (updated.execution_output or "")


@pytest.mark.asyncio
async def test_executor_rejects_high_risk_plan() -> None:
    executor = RemediationExecutor(execution_enabled=True)
    plan = RemediationPlan(
        plan_id="plan-2",
        alert_id="alert-2",
        trace_id="trace-2",
        summary="危险操作",
        commands=["kubectl delete pod order-abc"],
        risk_level="high",
    )

    with pytest.raises(ValueError, match="低风险"):
        await executor.approve_and_execute(
            plan,
            RemediationExecuteRequest(approved_by="ops-user", confirm=True),
        )


def test_reject_plan_updates_status() -> None:
    executor = RemediationExecutor()
    plan = RemediationPlan(
        plan_id="plan-3",
        alert_id="alert-3",
        trace_id="trace-3",
        summary="暂缓",
        commands=["kubectl scale deployment/order --replicas=2"],
        risk_level="low",
    )

    updated = executor.reject(plan, "ops-lead", "业务高峰期禁止变更")
    assert updated.status == RemediationStatus.REJECTED
