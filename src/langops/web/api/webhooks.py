"""Webhook receivers for external alert sources."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.adapters.aliyun_cms import AliyunCmsWebhookAdapter
from langops.agent import AlertProcessor
from langops.core import get_logger, settings
from langops.core.audit import AuditLogger
from langops.models import AlertCreate
from langops.models.webhook import (
    AlertmanagerWebhookPayload,
    AliyunCmsCallbackPayload,
    WebhookAlertResult,
    WebhookBatchResponse,
)
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.web._alert_flow import process_one_alert
from langops.web._coalesce import CoalesceBuffer, parse_coalesce_duration
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_alertmanager_adapter,
    get_aliyun_cms_adapter,
    get_audit_logger,
    get_coalesce_buffer,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.metrics import (
    webhook_alerts_received_total,
    webhook_duration_seconds,
    webhook_received_total,
)

logger = get_logger(__name__)

WEBHOOK_SOURCE = "alertmanager"
CMS_WEBHOOK_SOURCE = "aliyun-cms"

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/alertmanager",
    response_model=WebhookBatchResponse,
    summary="Receive Prometheus AlertManager webhook",
    description=(
        "Accepts an AlertManager v4 webhook payload, maps each alert to "
        "`AlertCreate`, and runs it through the standard analysis pipeline. "
        "Optional `?coalesce=Nm` enables a time-window buffer for storm scenarios."
    ),
)
async def alertmanager_webhook(
    request: Request,
    coalesce: str | None = None,
    adapter: AlertmanagerAdapter = Depends(get_alertmanager_adapter),
    processor: AlertProcessor = Depends(get_alert_processor),
    dedup: AlertNoiseReducer = Depends(get_alert_dedup),
    remediation_registry: RemediationRegistry = Depends(get_remediation_registry),
    jira: JiraService = Depends(get_jira_service),
    audit: AuditLogger = Depends(get_audit_logger),
    buffer: CoalesceBuffer = Depends(get_coalesce_buffer),
) -> WebhookBatchResponse:
    start = time.monotonic()
    request_id = request.headers.get("X-Request-ID", "")

    try:
        # 1. Pre-check Content-Length before reading the body
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.webhook.max_payload_bytes:
            audit.warning(
                "webhook.rejected",
                webhook_source=WEBHOOK_SOURCE,
                reason="payload_too_large",
                content_length=int(content_length),
                max_bytes=settings.webhook.max_payload_bytes,
            )
            raise HTTPException(status_code=422, detail="payload too large")

        # 2. Read body and re-check size (in case Content-Length was missing/wrong)
        body = await request.body()
        if len(body) > settings.webhook.max_payload_bytes:
            audit.warning(
                "webhook.rejected",
                webhook_source=WEBHOOK_SOURCE,
                reason="payload_too_large",
                body_bytes=len(body),
                max_bytes=settings.webhook.max_payload_bytes,
            )
            raise HTTPException(status_code=422, detail="payload too large")

        # 3. Parse payload
        try:
            payload = AlertmanagerWebhookPayload.model_validate_json(body)
        except ValidationError as exc:
            audit.warning(
                "webhook.received",
                webhook_source=WEBHOOK_SOURCE,
                error=str(exc)[:200],
                request_id=request_id,
            )
            raise HTTPException(status_code=422, detail=f"invalid payload: {str(exc)[:200]}")

        # 4. Batch size enforcement
        if len(payload.alerts) > settings.webhook.max_alerts_per_batch:
            audit.warning(
                "webhook.rejected",
                webhook_source=WEBHOOK_SOURCE,
                reason="batch_too_large",
                alert_count=len(payload.alerts),
                max_alerts=settings.webhook.max_alerts_per_batch,
            )
            raise HTTPException(status_code=422, detail="batch too large")

        # 5. Audit + metrics for accepted payload
        audit.info(
            "webhook.received",
            webhook_source=WEBHOOK_SOURCE,
            request_id=request_id,
            alert_count=len(payload.alerts),
        )
        webhook_alerts_received_total.labels(webhook_source=WEBHOOK_SOURCE).inc(len(payload.alerts))

        # 6. Map → list[AlertCreate]
        alert_creates: list[AlertCreate] = adapter.to_alert_creates(payload)

        # 7. Coalesce branch
        if coalesce:
            try:
                coalesce_seconds = parse_coalesce_duration(coalesce)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"invalid coalesce: {coalesce}")
            if settings.workers > 1:
                logger.warning(
                    "coalesce.disabled_multi_worker",
                    workers=settings.workers,
                    webhook_source=WEBHOOK_SOURCE,
                )
            else:
                for ac in alert_creates:
                    await buffer.push(WEBHOOK_SOURCE, ac)
                return WebhookBatchResponse(
                    success=True,
                    received=len(alert_creates),
                    results=[],
                    audit={"coalesced": True, "coalesce_seconds": coalesce_seconds},
                )

        # 8. Default: gather per-alert processing
        results = await _gather_process(
            alert_creates, processor, dedup, remediation_registry, jira, audit
        )
        webhook_received_total.labels(webhook_source=WEBHOOK_SOURCE, status="success").inc()
        return WebhookBatchResponse(
            success=True,
            received=len(alert_creates),
            results=results,
            audit={"coalesced": False},
        )

    except HTTPException:
        webhook_received_total.labels(
            webhook_source=WEBHOOK_SOURCE, status="validation_error"
        ).inc()
        raise
    except Exception:
        webhook_received_total.labels(webhook_source=WEBHOOK_SOURCE, status="error").inc()
        logger.exception("webhook processing failed", webhook_source=WEBHOOK_SOURCE, exc_info=True)
        raise
    finally:
        webhook_duration_seconds.labels(webhook_source=WEBHOOK_SOURCE).observe(
            time.monotonic() - start
        )


async def _gather_process(
    alert_creates: list[AlertCreate],
    processor: AlertProcessor,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
    audit: AuditLogger,
    webhook_source: str = WEBHOOK_SOURCE,
) -> list[WebhookAlertResult]:
    """Process every alert through the shared pipeline; never raise.

    ``process_one_alert`` is contractually total — it converts exceptions into
    ``AnalysisResponse(success=False)`` — so plain ``gather`` is safe here.
    """
    coros = [
        process_one_alert(
            ac,
            processor,
            dedup,
            remediation_registry,
            jira,
            webhook_source=webhook_source,
            audit=audit,
        )
        for ac in alert_creates
    ]
    responses = await asyncio.gather(*coros)
    return [
        WebhookAlertResult(
            alert_id=r.data.alert_id if r.data else None,
            success=r.success,
            data=r.data,
            error=r.error,
            dedup=r.dedup.model_dump() if r.dedup else None,
            remediation_plan_id=r.remediation_plan_id,
        )
        for r in responses
    ]


# ─── Aliyun CMS webhook ──────────────────────────────────────────────────


@router.post(
    "/aliyun-cms",
    response_model=WebhookBatchResponse,
    summary="Receive Aliyun Cloud Monitor callback",
    description=(
        "Accepts an Alibaba Cloud Monitor (CMS) alert callback, maps it to "
        "`AlertCreate`, and runs it through the standard analysis pipeline."
    ),
)
async def aliyun_cms_webhook(
    request: Request,
    payload: AliyunCmsCallbackPayload,
    adapter: AliyunCmsWebhookAdapter = Depends(get_aliyun_cms_adapter),
    processor: AlertProcessor = Depends(get_alert_processor),
    dedup: AlertNoiseReducer = Depends(get_alert_dedup),
    remediation_registry: RemediationRegistry = Depends(get_remediation_registry),
    jira: JiraService = Depends(get_jira_service),
    audit: AuditLogger = Depends(get_audit_logger),
) -> WebhookBatchResponse:
    """Receive and process a single Aliyun CMS alert callback.

    The ``payload`` parameter is automatically validated against
    :class:`AliyunCmsCallbackPayload` — invalid JSON or missing required
    fields return **422** before any business logic runs.
    """
    start = time.monotonic()
    request_id = request.headers.get("X-Request-ID", "")
    CMS_SOURCE = "aliyun-cms"

    if payload.alertState == "OK":
        # Resolution notification — acknowledge but skip processing
        audit.info(
            "webhook.resolved",
            webhook_source=CMS_SOURCE,
            alert_name=payload.alertName,
            request_id=request_id,
        )
        webhook_duration_seconds.labels(webhook_source=CMS_SOURCE).observe(time.monotonic() - start)
        return WebhookBatchResponse(success=True, received=1, results=[])

    try:
        alert_create = adapter.to_alert_create(payload)
    except Exception as exc:
        audit.warning(
            "webhook.rejected",
            webhook_source=CMS_SOURCE,
            reason="adapter_error",
            error=str(exc),
        )
        raise HTTPException(status_code=422, detail=f"adapter error: {str(exc)[:200]}")

    audit.info(
        "webhook.received",
        webhook_source=CMS_SOURCE,
        request_id=request_id,
        alert_name=alert_create.title,
    )
    webhook_alerts_received_total.labels(webhook_source=CMS_SOURCE).inc()

    results = await _gather_process(
        [alert_create], processor, dedup, remediation_registry, jira, audit,
        webhook_source=CMS_SOURCE,
    )

    webhook_received_total.labels(webhook_source=CMS_SOURCE, status="success").inc()
    webhook_duration_seconds.labels(webhook_source=CMS_SOURCE).observe(time.monotonic() - start)
    return WebhookBatchResponse(success=True, received=1, results=results)
