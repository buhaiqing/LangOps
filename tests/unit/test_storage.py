"""Unit tests for the storage layer."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from langops.models import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertSource,
    AnalysisResult,
    RemediationPlan,
    RemediationStatus,
    RemediationSuggestion,
    RootCause,
)
from langops.storage.models import Base
from langops.storage.sql import (
    SqlAlertRepository,
    SqlAnalysisRepository,
    SqlDedupRepository,
    SqlRemediationRepository,
    SqlStorage,
)


@pytest.fixture
def engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=e)
    yield e
    e.dispose()


@pytest.fixture
def sf(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def alert_repo(sf):
    return SqlAlertRepository(sf)


@pytest.fixture
def analysis_repo(sf):
    return SqlAnalysisRepository(sf)


@pytest.fixture
def dedup_repo(sf):
    return SqlDedupRepository(sf)


@pytest.fixture
def remediation_repo(sf):
    return SqlRemediationRepository(sf)


# ── AlertRepository ──────────────────────────────────────────────────


class TestSqlAlertRepository:

    @pytest.mark.asyncio
    async def test_save_and_get(self, alert_repo):
        ts = datetime.now(UTC)
        alert = Alert(
            id="a1",
            title="CPU高",
            description="CPU>90%",
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.RESOURCE,
            source=AlertSource(type="kubernetes", system="prod", namespace="ns1", pod_name="pod1"),
            timestamp=ts,
            metric_data={"cpu": 95},
        )
        await alert_repo.save(alert)
        result = await alert_repo.get("a1")
        assert result is not None
        assert result["id"] == "a1"
        assert result["severity"] == "critical"
        assert result["metric_data"] == {"cpu": 95}

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, alert_repo):
        assert await alert_repo.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list_recent_ordering(self, alert_repo):
        now = datetime.now(UTC)
        alert_old = Alert(
            id="a-old",
            title="old",
            description="d",
            severity=AlertSeverity.LOW,
            category=AlertCategory.RESOURCE,
            source=AlertSource(type="k8s", system="s"),
            timestamp=now - timedelta(hours=1),
            metric_data={},
        )
        alert_new = Alert(
            id="a-new",
            title="new",
            description="d",
            severity=AlertSeverity.HIGH,
            category=AlertCategory.RESOURCE,
            source=AlertSource(type="k8s", system="s"),
            timestamp=now,
            metric_data={},
        )
        await alert_repo.save(alert_old)
        await alert_repo.save(alert_new)
        rows = await alert_repo.list_recent(limit=10)
        assert len(rows) == 2
        assert rows[0]["id"] == "a-new"

    @pytest.mark.asyncio
    async def test_count(self, alert_repo):
        assert await alert_repo.count() == 0
        alert = Alert(
            id="a1",
            title="t",
            description="d",
            severity=AlertSeverity.LOW,
            category=AlertCategory.RESOURCE,
            source=AlertSource(type="k8s", system="s"),
            timestamp=datetime.now(UTC),
            metric_data={},
        )
        await alert_repo.save(alert)
        assert await alert_repo.count() == 1


# ── AnalysisRepository ───────────────────────────────────────────────


class TestSqlAnalysisRepository:

    @pytest.mark.asyncio
    async def test_save_and_get_by_alert(self, analysis_repo):
        result = AnalysisResult(
            alert_id="a1",
            trace_id="t1",
            root_cause=RootCause(category="资源不足", description="CPU不足", confidence=0.9),
            suggestion=RemediationSuggestion(summary="扩容"),
            similar_cases=[],
            impact_prediction={"risk": "high"},
            processing_time_seconds=2.5,
        )
        await analysis_repo.save(result)
        stored = await analysis_repo.get_by_alert("a1")
        assert stored is not None
        assert stored["trace_id"] == "t1"
        assert stored["root_cause"]["category"] == "资源不足"
        assert stored["processing_time"] == 2.5

    @pytest.mark.asyncio
    async def test_get_by_alert_missing(self, analysis_repo):
        assert await analysis_repo.get_by_alert("no-such") is None

    @pytest.mark.asyncio
    async def test_list_recent(self, analysis_repo):
        for i in range(5):
            result = AnalysisResult(
                alert_id=f"a{i}",
                trace_id=f"t{i}",
                root_cause=RootCause(category="test", description="d", confidence=0.5),
                suggestion=RemediationSuggestion(summary="s"),
                similar_cases=[],
                impact_prediction={},
                processing_time_seconds=1.0,
            )
            await analysis_repo.save(result)
        rows = await analysis_repo.list_recent(limit=3)
        assert len(rows) == 3


# ── DedupRepository ──────────────────────────────────────────────────


class TestSqlDedupRepository:

    @pytest.mark.asyncio
    async def test_upsert_and_get(self, dedup_repo):
        now = datetime.now(UTC)
        await dedup_repo.upsert("fp1", first_seen=now, last_seen=now, count=1)
        result = await dedup_repo.get("fp1")
        assert result is not None
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self, dedup_repo):
        now = datetime.now(UTC)
        await dedup_repo.upsert("fp1", first_seen=now, last_seen=now, count=1)
        later = now + timedelta(minutes=5)
        await dedup_repo.upsert("fp1", first_seen=now, last_seen=later, count=3)
        result = await dedup_repo.get("fp1")
        assert result["count"] == 3

    @pytest.mark.asyncio
    async def test_purge_expired(self, dedup_repo):
        old = datetime(2020, 1, 1, tzinfo=UTC)
        recent = datetime.now(UTC)
        await dedup_repo.upsert("old", first_seen=old, last_seen=old, count=1)
        await dedup_repo.upsert("new", first_seen=recent, last_seen=recent, count=1)
        deleted = await dedup_repo.purge_expired(datetime(2021, 1, 1, tzinfo=UTC))
        assert deleted == 1
        assert await dedup_repo.get("old") is None
        assert await dedup_repo.get("new") is not None

    @pytest.mark.asyncio
    async def test_count(self, dedup_repo):
        assert await dedup_repo.count() == 0
        now = datetime.now(UTC)
        await dedup_repo.upsert("fp1", first_seen=now, last_seen=now, count=1)
        assert await dedup_repo.count() == 1


# ── RemediationRepository ────────────────────────────────────────────


class TestSqlRemediationRepository:

    @pytest.mark.asyncio
    async def test_save_and_get(self, remediation_repo):
        plan = RemediationPlan(
            plan_id="p1",
            alert_id="a1",
            trace_id="t1",
            summary="扩容",
            commands=["kubectl scale ..."],
            risks=["risk1"],
            rollback_plan=None,
            risk_level="low",
            status=RemediationStatus.PENDING_APPROVAL,
        )
        await remediation_repo.save(plan)
        result = await remediation_repo.get("p1")
        assert result is not None
        assert result["plan_id"] == "p1"
        assert result["commands"] == ["kubectl scale ..."]
        assert result["status"] == "pending_approval"

    @pytest.mark.asyncio
    async def test_update_status(self, remediation_repo):
        plan = RemediationPlan(
            plan_id="p1",
            alert_id="a1",
            trace_id="t1",
            summary="s",
            commands=[],
            risks=[],
            rollback_plan=None,
            risk_level="low",
            status=RemediationStatus.PENDING_APPROVAL,
        )
        await remediation_repo.save(plan)
        await remediation_repo.update_status(
            "p1",
            status="executed",
            approved_by="ops",
            execution_output="ok",
        )
        result = await remediation_repo.get("p1")
        assert result["status"] == "executed"
        assert result["approved_by"] == "ops"
        assert result["execution_output"] == "ok"

    @pytest.mark.asyncio
    async def test_list_pending(self, remediation_repo):
        plan1 = RemediationPlan(
            plan_id="p1",
            alert_id="a1",
            trace_id="t1",
            summary="s1",
            commands=[],
            risks=[],
            rollback_plan=None,
            risk_level="low",
            status=RemediationStatus.PENDING_APPROVAL,
        )
        plan2 = RemediationPlan(
            plan_id="p2",
            alert_id="a2",
            trace_id="t2",
            summary="s2",
            commands=[],
            risks=[],
            rollback_plan=None,
            risk_level="low",
            status=RemediationStatus.EXECUTED,
        )
        await remediation_repo.save(plan1)
        await remediation_repo.save(plan2)
        pending = await remediation_repo.list_pending()
        assert len(pending) == 1
        assert pending[0]["plan_id"] == "p1"


# ── SqlStorage facade ────────────────────────────────────────────────


class TestSqlStorage:

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self):
        from sqlalchemy import inspect

        storage = SqlStorage("sqlite://")
        await storage.initialize()
        inspector = inspect(storage._engine)
        assert inspector.has_table("alerts")
        assert inspector.has_table("analyses")
        assert inspector.has_table("dedup")
        assert inspector.has_table("remediations")
        await storage.close()

    @pytest.mark.asyncio
    async def test_repository_properties(self):
        storage = SqlStorage("sqlite://")
        await storage.initialize()
        assert storage.alerts is not None
        assert storage.analyses is not None
        assert storage.dedup is not None
        assert storage.remediations is not None
        await storage.close()


# ── Error handling / edge cases ──────────────────────────────────────


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_plan(self, remediation_repo):
        await remediation_repo.update_status("nonexistent", "executed")

    @pytest.mark.asyncio
    async def test_get_nonexistent_analysis(self, analysis_repo):
        result = await analysis_repo.get_by_alert("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_nonexistent_remediation(self, remediation_repo):
        result = await remediation_repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_recent_empty(self, alert_repo):
        result = await alert_repo.list_recent(limit=10)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_pending_empty(self, remediation_repo):
        result = await remediation_repo.list_pending()
        assert result == []
