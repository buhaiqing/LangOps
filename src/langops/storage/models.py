"""SQLAlchemy ORM models for LangOps storage layer."""

from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    pass


class AlertRecord(Base):
    """Stores raw alert data received via API."""

    __tablename__ = "alerts"

    id = Column(String(64), primary_key=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)
    source_type = Column(String(50), nullable=False)
    source_system = Column(String(200), nullable=False)
    source_namespace = Column(String(200), nullable=True)
    source_pod = Column(String(300), nullable=True)
    source_instance = Column(String(300), nullable=True)
    metric_data = Column(Text, nullable=False, default="{}")
    created_at = Column(
        DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(UTC)
    )


class AnalysisRecord(Base):
    """Stores LLM analysis results."""

    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(100), nullable=False)
    root_cause = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=False)
    similar_cases = Column(Text, nullable=False, default="[]")
    impact_prediction = Column(Text, nullable=False, default="{}")
    processing_time = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class DedupRecord(Base):
    """Stores alert deduplication state."""

    __tablename__ = "dedup"

    fingerprint = Column(String(64), primary_key=True)
    first_seen = Column(DateTime(timezone=True), nullable=False)
    last_seen = Column(DateTime(timezone=True), nullable=False, index=True)
    count = Column(Integer, nullable=False, default=1)


class RemediationRecord(Base):
    """Stores remediation plans."""

    __tablename__ = "remediations"

    plan_id = Column(String(64), primary_key=True)
    alert_id = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(100), nullable=False)
    summary = Column(Text, nullable=False)
    commands = Column(Text, nullable=False, default="[]")
    risks = Column(Text, nullable=False, default="[]")
    rollback_plan = Column(Text, nullable=True)
    risk_level = Column(String(20), nullable=False)
    status = Column(String(30), nullable=False, default="pending_approval", index=True)
    jira_issue_key = Column(String(50), nullable=True)
    approved_by = Column(String(100), nullable=True)
    execution_output = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, index=True, default=lambda: datetime.now(UTC)
    )
