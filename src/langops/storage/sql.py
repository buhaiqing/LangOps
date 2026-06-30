"""SQLAlchemy-backed repository implementations (SQLite and PostgreSQL)."""

import asyncio
import json
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, delete, desc, select
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from langops.models import Alert, AnalysisResult, RemediationPlan

from langops.core import get_logger
from langops.storage.base import (
    AlertRepository,
    AnalysisRepository,
    DedupRepository,
    RemediationRepository,
    Storage,
)
from langops.storage.models import (
    AlertRecord,
    AnalysisRecord,
    Base,
    DedupRecord,
    RemediationRecord,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Alert Repository
# ---------------------------------------------------------------------------


class SqlAlertRepository(AlertRepository):

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _sync_save_alert(self, alert):
        with self._session_factory() as session:
            record = AlertRecord(
                id=alert.id,
                title=alert.title,
                description=alert.description,
                severity=alert.severity.value,
                category=alert.category.value,
                source_type=alert.source.type,
                source_system=alert.source.system,
                source_namespace=alert.source.namespace,
                source_pod=alert.source.pod_name,
                source_instance=alert.source.instance_id,
                metric_data=json.dumps(alert.metric_data, ensure_ascii=False),
                created_at=alert.timestamp,
            )
            session.merge(record)
            session.commit()

    async def save(self, alert: "Alert") -> None:
        await asyncio.to_thread(self._sync_save_alert, alert)

    def _sync_get_alert(self, alert_id):
        with self._session_factory() as session:
            record = session.get(AlertRecord, alert_id)
            if record is None:
                return None
            return self._to_dict(record)

    async def get(self, alert_id: str) -> dict | None:
        return await asyncio.to_thread(self._sync_get_alert, alert_id)

    def _sync_count_alerts(self):
        with self._session_factory() as session:
            return session.query(AlertRecord).count()

    async def count(self) -> int:
        return await asyncio.to_thread(self._sync_count_alerts)

    @staticmethod
    def _to_dict(record: AlertRecord) -> dict:
        return {
            "id": record.id,
            "title": record.title,
            "description": record.description,
            "severity": record.severity,
            "category": record.category,
            "source_type": record.source_type,
            "source_system": record.source_system,
            "source_namespace": record.source_namespace,
            "source_pod": record.source_pod,
            "source_instance": record.source_instance,
            "metric_data": json.loads(record.metric_data or "{}"),
            "created_at": record.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Analysis Repository
# ---------------------------------------------------------------------------


class SqlAnalysisRepository(AnalysisRepository):

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _sync_save(self, result: "AnalysisResult"):
        with self._session_factory() as session:
            record = AnalysisRecord(
                alert_id=result.alert_id,
                trace_id=result.trace_id,
                root_cause=json.dumps(result.root_cause.model_dump(), ensure_ascii=False),
                suggestion=json.dumps(result.suggestion.model_dump(), ensure_ascii=False),
                similar_cases=json.dumps(
                    [c.model_dump() for c in result.similar_cases], ensure_ascii=False
                ),
                impact_prediction=json.dumps(result.impact_prediction, ensure_ascii=False),
                processing_time=result.processing_time_seconds,
                created_at=result.timestamp,
            )
            session.add(record)
            session.commit()

    async def save(self, result: "AnalysisResult") -> None:
        await asyncio.to_thread(self._sync_save, result)

    def _sync_list_recent(self, limit, offset):
        with self._session_factory() as session:
            stmt = (
                select(AnalysisRecord)
                .order_by(desc(AnalysisRecord.created_at))
                .offset(offset)
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [self._to_dict(r) for r in rows]

    @staticmethod
    def _to_dict(record: AnalysisRecord) -> dict:
        return {
            "id": record.id,
            "alert_id": record.alert_id,
            "trace_id": record.trace_id,
            "root_cause": json.loads(record.root_cause),
            "suggestion": json.loads(record.suggestion),
            "similar_cases": json.loads(record.similar_cases),
            "impact_prediction": json.loads(record.impact_prediction),
            "processing_time": record.processing_time,
            "created_at": record.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Dedup Repository
# ---------------------------------------------------------------------------


class SqlDedupRepository(DedupRepository):

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _sync_get(self, fingerprint):
        with self._session_factory() as session:
            record = session.get(DedupRecord, fingerprint)
            if record is None:
                return None
            return {
                "fingerprint": record.fingerprint,
                "first_seen": record.first_seen.isoformat(),
                "last_seen": record.last_seen.isoformat(),
                "count": record.count,
            }

    async def get(self, fingerprint: str) -> dict | None:
        return await asyncio.to_thread(self._sync_get, fingerprint)

    def _sync_upsert(self, fingerprint, first_seen, last_seen, count):
        with self._session_factory() as session:
            existing = session.get(DedupRecord, fingerprint)
            if existing:
                existing.last_seen = last_seen
                existing.count = count
            else:
                record = DedupRecord(
                    fingerprint=fingerprint,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    count=count,
                )
                session.add(record)
            session.commit()

    async def upsert(
        self, fingerprint: str, first_seen: datetime, last_seen: datetime, count: int
    ) -> None:
        await asyncio.to_thread(self._sync_upsert, fingerprint, first_seen, last_seen, count)

    def _sync_purge(self, cutoff):
        with self._session_factory() as session:
            stmt = delete(DedupRecord).where(DedupRecord.last_seen < cutoff)
            result = session.execute(stmt)
            session.commit()
            return result.rowcount

    async def purge_expired(self, cutoff: datetime) -> int:
        return await asyncio.to_thread(self._sync_purge, cutoff)

    def _sync_count(self):
        with self._session_factory() as session:
            return session.query(DedupRecord).count()

    async def count(self) -> int:
        return await asyncio.to_thread(self._sync_count)


# ---------------------------------------------------------------------------
# Remediation Repository
# ---------------------------------------------------------------------------


class SqlRemediationRepository(RemediationRepository):

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _sync_save(self, plan: "RemediationPlan"):
        with self._session_factory() as session:
            record = RemediationRecord(
                plan_id=plan.plan_id,
                alert_id=plan.alert_id,
                trace_id=plan.trace_id,
                summary=plan.summary,
                commands=json.dumps(plan.commands, ensure_ascii=False),
                risks=json.dumps(plan.risks, ensure_ascii=False),
                rollback_plan=plan.rollback_plan,
                risk_level=plan.risk_level,
                status=plan.status.value,
                jira_issue_key=plan.jira_issue_key,
                approved_by=plan.approved_by,
                execution_output=plan.execution_output,
                created_at=plan.created_at,
            )
            session.merge(record)
            session.commit()

    async def save(self, plan: "RemediationPlan") -> None:
        await asyncio.to_thread(self._sync_save, plan)

    def _sync_get(self, plan_id):
        with self._session_factory() as session:
            record = session.get(RemediationRecord, plan_id)
            if record is None:
                return None
            return self._to_dict(record)

    async def get(self, plan_id: str) -> dict | None:
        return await asyncio.to_thread(self._sync_get, plan_id)

    def _sync_update_status(self, plan_id, status, approved_by, execution_output, jira_issue_key):
        with self._session_factory() as session:
            record = session.get(RemediationRecord, plan_id)
            if record is None:
                return
            record.status = status
            if approved_by is not None:
                record.approved_by = approved_by
            if execution_output is not None:
                record.execution_output = execution_output
            if jira_issue_key is not None:
                record.jira_issue_key = jira_issue_key
            session.commit()

    async def update_status(
        self,
        plan_id: str,
        status: str,
        approved_by: str | None = None,
        execution_output: str | None = None,
        jira_issue_key: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._sync_update_status, plan_id, status, approved_by, execution_output, jira_issue_key
        )

    def _sync_list_pending(self):
        with self._session_factory() as session:
            stmt = (
                select(RemediationRecord)
                .where(RemediationRecord.status == "pending_approval")
                .order_by(desc(RemediationRecord.created_at))
            )
            rows = session.execute(stmt).scalars().all()
            return [self._to_dict(r) for r in rows]

    async def list_pending(self) -> list[dict]:
        return await asyncio.to_thread(self._sync_list_pending)

    @staticmethod
    def _to_dict(record: RemediationRecord) -> dict:
        return {
            "plan_id": record.plan_id,
            "alert_id": record.alert_id,
            "trace_id": record.trace_id,
            "summary": record.summary,
            "commands": json.loads(record.commands),
            "risks": json.loads(record.risks),
            "rollback_plan": record.rollback_plan,
            "risk_level": record.risk_level,
            "status": record.status,
            "jira_issue_key": record.jira_issue_key,
            "approved_by": record.approved_by,
            "execution_output": record.execution_output,
            "created_at": record.created_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Storage facade
# ---------------------------------------------------------------------------


class SqlStorage(Storage):
    """Unified SQL storage supporting both SQLite and PostgreSQL."""

    def __init__(self, url: str, echo: bool = False) -> None:
        from sqlalchemy.pool import StaticPool

        self._url = url
        connect_kwargs: dict = {}
        pool_kwargs: dict = {}
        if url == "sqlite://" or url.startswith("sqlite:///:memory:"):
            pool_kwargs["poolclass"] = StaticPool
            connect_kwargs["check_same_thread"] = False
        self._engine = create_engine(
            url,
            echo=echo,
            future=True,
            connect_args=connect_kwargs,
            **pool_kwargs,
        )
        self._session_factory = sessionmaker(bind=self._engine, class_=Session)
        self._alerts = SqlAlertRepository(self._session_factory)
        self._analyses = SqlAnalysisRepository(self._session_factory)
        self._dedup = SqlDedupRepository(self._session_factory)
        self._remediations = SqlRemediationRepository(self._session_factory)

    async def initialize(self) -> None:
        await asyncio.to_thread(Base.metadata.create_all, self._engine)
        logger.info(
            "Storage initialized", url=self._url.split("@")[-1] if "@" in self._url else self._url
        )

    async def close(self) -> None:
        await asyncio.to_thread(self._engine.dispose)

    @property
    def alerts(self) -> SqlAlertRepository:
        return self._alerts

    @property
    def analyses(self) -> SqlAnalysisRepository:
        return self._analyses

    @property
    def dedup(self) -> SqlDedupRepository:
        return self._dedup

    @property
    def remediations(self) -> SqlRemediationRepository:
        return self._remediations
