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
    RemediationSuggestion,
    RootCause,
)
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web._alert_flow import process_one_alert


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
