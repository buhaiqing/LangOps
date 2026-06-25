"""Alert API routes."""

import time
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from langops.agent import AlertProcessor
from langops.core import get_logger, settings
from langops.models import Alert, AlertCreate, AnalysisResponse
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_jira_service,
    get_remediation_registry,
    persist_alert_and_result,
)
from langops.web.metrics import (
    alert_processing_duration_seconds,
    alerts_processed_total,
    alerts_received_total,
    dedup_suppressed_total,
    remediation_plans_total,
)

logger = get_logger(__name__)

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
    alerts_received_total.labels(
        severity=alert_create.severity.value,
        category=alert_create.category.value,
    ).inc()

    start = time.monotonic()
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

        logger.info("Alert received", alert_id=alert.id, severity=alert.severity.value)

        decision = await dedup.evaluate(alert)
        if decision.action == "suppress":
            dedup_suppressed_total.inc()
            alerts_processed_total.labels(severity=alert.severity.value, status="suppressed").inc()
            logger.info(
                "Alert suppressed by dedup", alert_id=alert.id, fingerprint=decision.fingerprint
            )
            return AnalysisResponse(success=True, data=None, error=None, dedup=decision)

        result = await processor.process(alert)

        await persist_alert_and_result(alert, result)

        plan_id = None
        if settings.remediation.enabled and result.suggestion.commands:
            plan = await remediation_registry.create_from_analysis(result)
            plan_id = plan.plan_id
            remediation_plans_total.labels(risk_level=plan.risk_level).inc()

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
                await remediation_registry.save(plan)

        duration = time.monotonic() - start
        alert_processing_duration_seconds.observe(duration)
        alerts_processed_total.labels(severity=alert.severity.value, status="success").inc()

        logger.info(
            "Alert processed successfully",
            alert_id=alert.id,
            trace_id=result.trace_id,
            duration_ms=round(duration * 1000, 2),
        )

        return AnalysisResponse(
            success=True,
            data=result,
            error=None,
            dedup=decision,
            remediation_plan_id=plan_id,
        )

    except Exception as exc:
        duration = time.monotonic() - start
        alert_processing_duration_seconds.observe(duration)
        alerts_processed_total.labels(severity=alert_create.severity.value, status="failure").inc()
        logger.error(
            "Alert processing failed", error=str(exc), duration_ms=round(duration * 1000, 2)
        )
        return AnalysisResponse(success=False, data=None, error=str(exc), dedup=None)


@router.get(
    "/dedup/stats",
    summary="Dedup statistics",
    description="Return active alert group count for noise reduction.",
)
async def dedup_stats(dedup: AlertNoiseReducer = Depends(get_alert_dedup)) -> dict[str, int]:
    """Return deduplication statistics."""
    return await dedup.stats()


@router.get(
    "/health",
    summary="Health check",
    description="Check if the alert service is healthy.",
)
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "alerts"}
