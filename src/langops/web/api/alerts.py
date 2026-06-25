"""Alert API routes."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from langops.agent import AlertProcessor
from langops.core import settings
from langops.models import Alert, AlertCreate, AnalysisResponse, DedupInfo
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_jira_service,
    get_remediation_registry,
)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post(
    "",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Process an alert",
    description="Receive an alert and trigger AI analysis pipeline.",
)
async def create_alert(
    alert_create: AlertCreate,
    processor: AlertProcessor = Depends(get_alert_processor),
    dedup: AlertNoiseReducer = Depends(get_alert_dedup),
    remediation_registry: RemediationRegistry = Depends(get_remediation_registry),
    jira: JiraService = Depends(get_jira_service),
) -> AnalysisResponse:
    """Process a new alert through the AI analysis pipeline."""
    try:
        alert = Alert(
            id=f"alert-{uuid.uuid4().hex[:8]}",
            title=alert_create.title,
            description=alert_create.description,
            severity=alert_create.severity,
            category=alert_create.category,
            source=alert_create.source,
            timestamp=datetime.now(UTC),
            metric_data=alert_create.metric_data,
            log_snippets=alert_create.log_snippets,
            context=alert_create.context,
        )

        decision = dedup.evaluate(alert)
        if decision.action == "suppress":
            return AnalysisResponse(success=True, data=None, error=None, dedup=decision)

        result = await processor.process(alert)
        plan_id = None
        if settings.remediation.enabled and result.suggestion.commands:
            plan = remediation_registry.create_from_analysis(result)
            plan_id = plan.plan_id

            # Phase A: JIRA ticket creation (best-effort)
            issue_key = await jira.create_ticket(
                alert_id=result.alert_id,
                severity=alert.severity.value,
                category=alert.category.value,
                source_type=alert.source.type,
                system=alert.source.system,
                resource=alert.source.pod_name or alert.source.instance_id,
                root_cause=result.root_cause.description,
                confidence=result.root_cause.confidence,
                evidence=result.root_cause.evidence,
                summary=result.suggestion.summary,
                risk_level=plan.risk_level,
                steps=result.suggestion.steps,
                trace_id=result.trace_id,
                remediation_plan_id=plan_id,
            )
            if issue_key:
                plan.jira_issue_key = issue_key
                remediation_registry.save(plan)

        return AnalysisResponse(
            success=True,
            data=result,
            error=None,
            dedup=decision,
            remediation_plan_id=plan_id,
        )

    except Exception as exc:
        return AnalysisResponse(success=False, data=None, error=str(exc), dedup=None)


@router.get(
    "/dedup/stats",
    summary="Dedup statistics",
    description="Return active alert group count for noise reduction.",
)
async def dedup_stats(dedup: AlertNoiseReducer = Depends(get_alert_dedup)) -> dict[str, int]:
    """Return deduplication statistics."""
    return dedup.stats()


@router.get(
    "/health",
    summary="Health check",
    description="Check if the alert service is healthy.",
)
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "alerts"}
