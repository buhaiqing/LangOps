"""Alert API routes."""

import time

from fastapi import APIRouter, Depends, status

from langops.agent import AlertProcessor
from langops.models import AlertCreate, AnalysisResponse
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.web._alert_flow import process_one_alert
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.metrics import (
    alert_processing_duration_seconds,
    alerts_processed_total,
    alerts_received_total,
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
    alerts_received_total.labels(
        severity=alert_create.severity.value,
        category=alert_create.category.value,
    ).inc()

    start = time.monotonic()
    try:
        response = await process_one_alert(
            alert_create, processor, dedup, remediation_registry, jira
        )
    finally:
        duration = time.monotonic() - start
        alert_processing_duration_seconds.observe(duration)

    if response.success:
        status_label = (
            "suppressed" if response.dedup and response.dedup.action == "suppress" else "success"
        )
    else:
        status_label = "failure"
    alerts_processed_total.labels(severity=alert_create.severity.value, status=status_label).inc()

    return response


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
