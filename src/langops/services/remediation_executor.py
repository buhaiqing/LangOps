"""Remediation plan registry and command executor."""

import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from langops.core import get_logger
from langops.models import AnalysisResult, RemediationExecuteRequest, RemediationPlan, RemediationStatus

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
    """Classify remediation command risk."""
    if not commands:
        return "high"

    allowed = [cmd for cmd in commands if is_allowed_command(cmd)]
    if len(allowed) == len(commands):
        return "low"
    if allowed:
        return "medium"
    return "high"


def is_allowed_command(command: str) -> bool:
    """Return True if command matches the kubectl allowlist."""
    cmd = command.strip()
    if not cmd:
        return False
    lowered = cmd.lower()
    if any(blocked in lowered for blocked in BLOCKED_SUBSTRINGS):
        return False
    return any(pattern.match(cmd) for pattern in ALLOWLIST_PATTERNS)


@dataclass
class RemediationRegistry:
    """In-memory store for remediation plans. ponytail: upgrade path = Redis/DB."""

    _plans: dict[str, RemediationPlan] = field(default_factory=dict)

    def create_from_analysis(self, result: AnalysisResult) -> RemediationPlan:
        """Create a pending remediation plan from analysis output."""
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        commands = list(result.suggestion.commands)
        plan = RemediationPlan(
            plan_id=plan_id,
            alert_id=result.alert_id,
            trace_id=result.trace_id,
            summary=result.suggestion.summary,
            commands=commands,
            risks=list(result.suggestion.risks),
            rollback_plan=result.suggestion.rollback_plan,
            risk_level=assess_command_risk(commands),
            status=RemediationStatus.PENDING_APPROVAL,
        )
        self._plans[plan_id] = plan
        logger.info("Remediation plan created", plan_id=plan_id, risk_level=plan.risk_level)
        return plan

    def get(self, plan_id: str) -> RemediationPlan | None:
        return self._plans.get(plan_id)

    def list_pending(self) -> list[RemediationPlan]:
        return [
            plan
            for plan in self._plans.values()
            if plan.status == RemediationStatus.PENDING_APPROVAL
        ]

    def save(self, plan: RemediationPlan) -> None:
        self._plans[plan.plan_id] = plan


class RemediationExecutor:
    """Execute approved low-risk remediation commands."""

    def __init__(self, *, execution_enabled: bool = True) -> None:
        self.execution_enabled = execution_enabled

    async def approve_and_execute(
        self,
        plan: RemediationPlan,
        request: RemediationExecuteRequest,
    ) -> RemediationPlan:
        """Approve and optionally execute a remediation plan."""
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

    def reject(self, plan: RemediationPlan, rejected_by: str, reason: str | None = None) -> RemediationPlan:
        """Reject a pending remediation plan."""
        if plan.status != RemediationStatus.PENDING_APPROVAL:
            raise ValueError(f"Plan is not pending approval (status={plan.status.value})")
        plan.status = RemediationStatus.REJECTED
        plan.approved_by = rejected_by
        plan.execution_output = reason or "rejected by operator"
        return plan

    async def _run_command(self, command: str) -> str:
        """Run a shell command and return combined output."""
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
