"""Remediation plan registry and command executor."""

import asyncio
import re
import uuid
from datetime import datetime

from langops.core import get_logger
from langops.models import (
    AnalysisResult,
    RemediationExecuteRequest,
    RemediationPlan,
    RemediationStatus,
)
from langops.storage.base import RemediationRepository

logger = get_logger(__name__)

ALLOWLIST_PATTERNS = (
    re.compile(r"^kubectl\s+scale\s+", re.IGNORECASE),
    re.compile(r"^kubectl\s+patch\s+", re.IGNORECASE),
    re.compile(r"^kubectl\s+rollout\s+restart\s+", re.IGNORECASE),
    re.compile(r"^kubectl\s+set\s+resources\s+", re.IGNORECASE),
)

BLOCKED_SUBSTRINGS = (
    "delete",
    " exec ",
    "apply -f http",
    "curl ",
    "wget ",
    "bash ",
    "sh -c",
    "rm -",
    "dd ",
)


def assess_command_risk(commands: list[str]) -> str:
    if not commands:
        return "high"
    allowed = [cmd for cmd in commands if is_allowed_command(cmd)]
    if len(allowed) == len(commands):
        return "low"
    if allowed:
        return "medium"
    return "high"


def is_allowed_command(command: str) -> bool:
    cmd = command.strip()
    if not cmd:
        return False
    lowered = cmd.lower()
    if any(blocked in lowered for blocked in BLOCKED_SUBSTRINGS):
        return False
    return any(pattern.match(cmd) for pattern in ALLOWLIST_PATTERNS)


class RemediationRegistry:
    """Persists remediation plans via the repository layer."""

    def __init__(self, repo: RemediationRepository) -> None:
        self._repo = repo

    async def create_from_analysis(self, result: AnalysisResult) -> RemediationPlan:
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        commands = list(result.suggestion.commands)
        risk_level = assess_command_risk(commands)

        plan = RemediationPlan(
            plan_id=plan_id,
            alert_id=result.alert_id,
            trace_id=result.trace_id,
            summary=result.suggestion.summary,
            commands=commands,
            risks=list(result.suggestion.risks),
            rollback_plan=result.suggestion.rollback_plan,
            risk_level=risk_level,
            status=RemediationStatus.PENDING_APPROVAL,
        )

        await self._repo.save(plan)
        logger.info("Remediation plan created", plan_id=plan_id, risk_level=risk_level)
        return plan

    async def get(self, plan_id: str) -> RemediationPlan | None:
        data = await self._repo.get(plan_id)
        if data is None:
            return None
        return self._from_dict(data)

    async def list_pending(self) -> list[RemediationPlan]:
        rows = await self._repo.list_pending()
        return [self._from_dict(r) for r in rows]

    async def save(self, plan: RemediationPlan) -> None:
        await self._repo.save(plan)

    @staticmethod
    def _from_dict(data: dict) -> RemediationPlan:
        return RemediationPlan(
            plan_id=data["plan_id"],
            alert_id=data["alert_id"],
            trace_id=data["trace_id"],
            summary=data["summary"],
            commands=data["commands"],
            risks=data["risks"],
            rollback_plan=data.get("rollback_plan"),
            risk_level=data["risk_level"],
            status=RemediationStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            approved_by=data.get("approved_by"),
            execution_output=data.get("execution_output"),
            jira_issue_key=data.get("jira_issue_key"),
        )


class RemediationExecutor:
    """Execute approved low-risk remediation commands."""

    def __init__(self, *, execution_enabled: bool = True) -> None:
        self.execution_enabled = execution_enabled

    async def approve_and_execute(
        self,
        plan: RemediationPlan,
        request: RemediationExecuteRequest,
    ) -> RemediationPlan:
        if plan.status != RemediationStatus.PENDING_APPROVAL:
            raise ValueError(f"Plan is not pending approval (status={plan.status.value})")
        if not request.confirm:
            raise ValueError("confirm must be true to approve remediation")
        if plan.risk_level != "low":
            raise ValueError("仅低风险 kubectl 命令支持自动执行，请人工在集群操作")

        plan.approved_by = request.approved_by

        if request.dry_run or not self.execution_enabled:
            plan.status = RemediationStatus.DRY_RUN
            plan.execution_output = "dry-run:\n" + "\n".join(plan.commands)
            return plan

        outputs: list[str] = []
        try:
            for command in plan.commands:
                if not is_allowed_command(command):
                    raise ValueError(f"Command blocked by allowlist: {command}")
                output = await self._run_command(command)
                outputs.append(f"$ {command}\n{output}")
            plan.status = RemediationStatus.EXECUTED
            plan.execution_output = "\n\n".join(outputs)
        except Exception as exc:
            plan.status = RemediationStatus.FAILED
            plan.execution_output = str(exc)
            logger.error("Remediation execution failed", plan_id=plan.plan_id, error=str(exc))

        return plan

    def reject(
        self, plan: RemediationPlan, rejected_by: str, reason: str | None = None
    ) -> RemediationPlan:
        if plan.status != RemediationStatus.PENDING_APPROVAL:
            raise ValueError(f"Plan is not pending approval (status={plan.status.value})")
        plan.status = RemediationStatus.REJECTED
        plan.approved_by = rejected_by
        plan.execution_output = reason or "rejected by operator"
        return plan

    async def _run_command(self, command: str) -> str:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        output = (stdout or b"").decode() + (stderr or b"").decode()
        if process.returncode != 0:
            raise RuntimeError(output.strip() or f"command failed with code {process.returncode}")
        return output.strip() or "(no output)"
