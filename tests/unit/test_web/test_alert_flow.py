"""Tests for the shared ``process_one_alert`` pipeline helper."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from langops.agent.alert_processor import AlertProcessor
from langops.core.audit import AuditLogger
from langops.models import (
    Alert,
    AlertCategory,
    AlertCreate,
    AlertSeverity,
    AlertSource,
    AnalysisResult,
    DedupInfo,
    RemediationSuggestion,
    RootCause,
)
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web._alert_flow import process_one_alert
from langops.web.api.webhooks import _gather_process


def _dedup_repo():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return SqlDedupRepository(sessionmaker(bind=engine))


def _remediation_repo():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


def _alert_create() -> AlertCreate:
    return AlertCreate(
        title="CPU使用率过高",
        description="order-service CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="prod-cluster",
            namespace="production",
            pod_name="order-pod",
        ),
    )


def _seed_alert() -> Alert:
    return Alert(
        id="alert-seed",
        title="CPU使用率过高",
        description="order-service CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="prod-cluster",
            namespace="production",
            pod_name="order-pod",
        ),
    )


@pytest.fixture
def dedup() -> AlertNoiseReducer:
    return AlertNoiseReducer(repo=_dedup_repo(), window_seconds=900, enabled=True)


@pytest.fixture
def remediation_registry() -> RemediationRegistry:
    return RemediationRegistry(repo=_remediation_repo())


@pytest.fixture
def jira() -> JiraService:
    return JiraService(url="", username="", api_token="", enabled=False)


def test_returns_suppressed_response_on_dedup(
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
) -> None:
    # Seed dedup state with one prior occurrence so the next call is a duplicate.
    asyncio.run(dedup.evaluate(_seed_alert()))

    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock()

    response = asyncio.run(
        process_one_alert(_alert_create(), processor, dedup, remediation_registry, jira)
    )

    assert response.success is True
    assert response.data is None
    assert response.error is None
    assert response.dedup is not None
    assert response.dedup.action == "suppress"
    processor.process.assert_not_awaited()


def test_returns_failure_response_on_processor_exception(
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
) -> None:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(side_effect=RuntimeError("boom"))

    response = asyncio.run(
        process_one_alert(_alert_create(), processor, dedup, remediation_registry, jira)
    )

    assert response.success is False
    assert response.data is None
    assert response.dedup is None
    assert response.error is not None
    assert "boom" in response.error


def test_emits_audit_event_when_audit_logger_provided(
    tmp_path: Path,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
) -> None:
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-xyz",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(
                summary="调高 limit",
                steps=["step1"],
                commands=["kubectl scale deployment/order --replicas=3"],
            ),
            processing_time_seconds=1.2,
        )
    )

    response = asyncio.run(
        process_one_alert(
            _alert_create(),
            processor,
            dedup,
            remediation_registry,
            jira,
            webhook_source="alertmanager",
            audit=audit,
        )
    )

    assert response.success is True
    audit.close()

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert "alert.processed" in events
    record = json.loads(lines[-1])
    assert record["webhook_source"] == "alertmanager"
    assert record["decision"] == "success"


# ─── audit events for each terminal decision ────────────────────────────


def test_process_one_alert_records_audit_suppress_event(
    tmp_path: Path,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
) -> None:
    """Dedup suppressing the alert must emit ``alert.processed`` with decision=suppress."""
    # Seed dedup state so the next call is a duplicate
    asyncio.run(dedup.evaluate(_seed_alert()))

    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock()  # never called

    response = asyncio.run(
        process_one_alert(
            _alert_create(),
            processor,
            dedup,
            remediation_registry,
            jira,
            webhook_source="alertmanager",
            audit=audit,
        )
    )

    assert response.success is True
    assert response.dedup is not None
    assert response.dedup.action == "suppress"
    processor.process.assert_not_awaited()

    audit.close()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    suppress_records = [r for r in records if r["event"] == "alert.processed"]
    assert len(suppress_records) == 1
    record = suppress_records[0]
    assert record["decision"] == "suppress"
    assert record["webhook_source"] == "alertmanager"
    assert record.get("fingerprint")  # dedup fingerprint recorded


def test_process_one_alert_records_audit_failure_event(
    tmp_path: Path,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
) -> None:
    """Processor raising must emit ``alert.processed`` with decision=failure and error."""
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(side_effect=RuntimeError("processor boom"))

    response = asyncio.run(
        process_one_alert(
            _alert_create(),
            processor,
            dedup,
            remediation_registry,
            jira,
            webhook_source="alertmanager",
            audit=audit,
        )
    )

    assert response.success is False
    assert "boom" in (response.error or "")

    audit.close()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    failure_records = [r for r in records if r["event"] == "alert.processed"]
    assert len(failure_records) == 1
    record = failure_records[0]
    assert record["decision"] == "failure"
    assert record["webhook_source"] == "alertmanager"
    assert "boom" in record.get("error", "")


# ─── concurrency limit in _gather_process ────────────────────────────────


@pytest.mark.asyncio
async def test_gather_process_respects_concurrency_limit(monkeypatch) -> None:
    """_gather_process must not run more than concurrency tasks simultaneously."""
    from langops.core import settings

    CONCURRENCY = 5
    BATCH_SIZE = 20

    monkeypatch.setattr(settings.webhook, "concurrency", CONCURRENCY)

    processor = MagicMock()

    async def _slow_process(alert: object) -> object:
        await asyncio.sleep(0.05)
        return AnalysisResult(
            alert_id=getattr(alert, "id", "test-id"),
            trace_id="trace-concurrency-test",
            root_cause=RootCause(category="test", description="test", confidence=0.5),
            suggestion=RemediationSuggestion(summary="test", steps=[], commands=[]),
            processing_time_seconds=0.01,
        )

    processor.process = _slow_process

    dedup = MagicMock()
    dedup.evaluate = AsyncMock(
        return_value=DedupInfo(
            action="process",
            fingerprint="fp-test",
            occurrence_count=1,
            window_seconds=900,
            message="first",
        )
    )
    remediation_registry = MagicMock()
    remediation_registry.create_from_analysis = AsyncMock(
        return_value=MagicMock(plan_id="plan-test", risk_level="low")
    )
    jira = JiraService(url="", username="", api_token="", enabled=False)

    alerts = [
        AlertCreate(
            title=f"alert-{i}",
            description=f"test {i}",
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.RESOURCE,
            source=AlertSource(type="prometheus", system="test"),
        )
        for i in range(BATCH_SIZE)
    ]

    loop = asyncio.get_running_loop()
    start = loop.time()
    results = await _gather_process(
        alerts,
        processor,
        dedup,
        remediation_registry,
        jira,
        audit=None,
    )
    elapsed = loop.time() - start

    assert len(results) == BATCH_SIZE
    assert all(r.success for r in results)

    # With CONCURRENCY=5 and BATCH_SIZE=20, each taking 0.05s:
    #   without concurrency limit: ≈0.05s  (all 20 in parallel)
    #   with concurrency limit:   ≥(20/5)*0.05 = 0.20s
    # Add generous slack for CI variability.
    assert elapsed >= 0.15, (
        f"concurrency={CONCURRENCY}, batch={BATCH_SIZE}: "
        f"elapsed={elapsed:.3f}s — expected ≥0.15s"
    )
