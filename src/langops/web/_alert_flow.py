"""Shared alert pipeline helper used by ``POST /api/v1/alerts`` and the
AlertManager webhook receiver.

Extracted from ``web.api.alerts.create_alert`` so the HTTP route and the
webhook adapter can reuse identical dedup → process → persist → remediation
behavior without re-implementing the pipeline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from langops.agent import AlertProcessor
from langops.core import get_logger, settings
from langops.models import Alert, AlertCreate, AnalysisResponse
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.web.dependencies import persist_alert_and_result
from langops.web.metrics import (
    dedup_suppressed_total,
    remediation_plans_total,
)

if TYPE_CHECKING:
    from langops.core.audit import AuditLogger

logger = get_logger(__name__)


async def process_one_alert(
    alert_create: AlertCreate,
    processor: AlertProcessor,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
    *,
    webhook_source: str | None = None,
    audit: AuditLogger | None = None,
) -> AnalysisResponse:
    """Run one alert through the full pipeline.

    ``processor`` is the AlertProcessor that performs the LLM-backed analysis.
    ``dedup`` short-circuits duplicates. ``remediation_registry`` and ``jira``
    are best-effort side effects: failures are logged but never propagate.

    When ``audit`` is provided, an ``alert.processed`` event is emitted for
    every terminal state (suppressed, success, failure). ``webhook_source``
    is attached to the audit payload when set.
    """
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

    try:
        decision = await dedup.evaluate(alert)
        if decision.action == "suppress":
            dedup_suppressed_total.inc()
            logger.info(
                "Alert suppressed by dedup",
                alert_id=alert.id,
                fingerprint=decision.fingerprint,
            )
            _emit_audit(
                audit,
                alert,
                decision="suppress",
                webhook_source=webhook_source,
                fingerprint=decision.fingerprint,
            )
            return AnalysisResponse(success=True, data=None, error=None, dedup=decision)

        result = await processor.process(alert)
        await persist_alert_and_result(alert, result)

        plan_id = None
        if settings.remediation.enabled and result.suggestion.commands:
            plan = await remediation_registry.create_from_analysis(result)
            plan_id = plan.plan_id
            remediation_plans_total.labels(risk_level=plan.risk_level).inc()

            # best-effort: jira failure should not break the alert response
            try:
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
            except Exception as exc:
                logger.warning(
                    "Jira ticket creation failed",
                    error=str(exc),
                    alert_id=alert.id,
                    plan_id=plan_id,
                )

        logger.info(
            "Alert processed successfully",
            alert_id=alert.id,
            trace_id=result.trace_id,
        )
        _emit_audit(
            audit,
            alert,
            decision="success",
            webhook_source=webhook_source,
            trace_id=result.trace_id,
            plan_id=plan_id,
        )
        return AnalysisResponse(
            success=True,
            data=result,
            error=None,
            dedup=decision,
            remediation_plan_id=plan_id,
        )

    except Exception as exc:
        logger.error(
            "Alert processing failed",
            alert_id=alert.id,
            error=str(exc),
        )
        _emit_audit(
            audit,
            alert,
            decision="failure",
            webhook_source=webhook_source,
            error=str(exc),
        )
        return AnalysisResponse(success=False, data=None, error=str(exc), dedup=None)


def _emit_audit(
    audit: AuditLogger | None,
    alert: Alert,
    *,
    decision: str,
    webhook_source: str | None,
    **extra: object,
) -> None:
    if audit is None:
        return
    fields: dict[str, object] = {
        "alert_id": alert.id,
        "severity": alert.severity.value,
        "category": alert.category.value,
        "decision": decision,
    }
    if webhook_source is not None:
        fields["webhook_source"] = webhook_source
    fields.update(extra)
    audit.info("alert.processed", **fields)
