"""Alert API routes."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status

from langops.agent import AlertProcessor
from langops.models import Alert, AlertCreate, AnalysisResponse, DedupInfo
from langops.services import AlertNoiseReducer
from langops.web.dependencies import get_alert_dedup, get_alert_processor

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
        return AnalysisResponse(success=True, data=result, error=None, dedup=decision)

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
