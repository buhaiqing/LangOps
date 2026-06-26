"""System-level integration test fixtures.

Real FastAPI app + conditional real/mock external dependencies.
When real credentials are configured (LLM, Langfuse), uses real services.
Otherwise falls back to mocked processor for fast, isolated tests.
"""

import os
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── Service detection (before any langops import) ───────────────────


def _env_is_real(key: str, test_prefix: str) -> bool:
    """Check if env var is set to a real (non-test) value."""
    value = os.environ.get(key, "")
    if not value:
        return False
    return not value.startswith(test_prefix)


# Provide test defaults only for unconfigured vars.
# Uses setdefault so real env vars / .env values take precedence.
_ENV_DEFAULTS = {
    "LLM_API_KEY": "sk-test-system",
    "LLM_MODEL": "gpt-4",
    "LANGFUSE_PUBLIC_KEY": "pk-test-system",
    "LANGFUSE_SECRET_KEY": "sk-lf-test-system",
    "DEBUG": "true",
    "LOG_LEVEL": "DEBUG",
}

for _key, _default in _ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _default)

# Detect available services
USE_REAL_LLM = _env_is_real("LLM_API_KEY", "sk-test")
USE_REAL_LANGFUSE = _env_is_real("LANGFUSE_PUBLIC_KEY", "pk-test")

# ── Import langops modules (Settings initializes here) ──────────────

from langops.agent.alert_processor import AlertProcessor  # noqa: E402
from langops.models import (  # noqa: E402
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
    SimilarCase,
)
from langops.services import AlertNoiseReducer, RemediationRegistry  # noqa: E402
from langops.storage.models import Base  # noqa: E402
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository  # noqa: E402
from langops.web.dependencies import (  # noqa: E402
    get_alert_dedup,
    get_alert_processor,
    get_remediation_registry,
)
from langops.web.main import app  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────


def create_sqlite_session() -> sessionmaker:
    """Create an in-memory SQLite session with all tables."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _make_mock_processor() -> MagicMock:
    """Create a mock AlertProcessor with realistic return value."""
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-sys-test",
            trace_id="trace-sys-test",
            root_cause=RootCause(
                category="资源不足",
                description="Pod CPU limit 设置过低，导致频繁被 cgroup 限流",
                confidence=0.92,
                evidence=["CPU 使用率持续 > 90%", "CPU limit 仅 200m"],
                related_metrics=["container_cpu_usage_seconds_total"],
            ),
            similar_cases=[
                SimilarCase(
                    case_id="case-001",
                    similarity_score=0.87,
                    title="MySQL 连接数耗尽",
                    root_cause="连接池配置不当",
                    solution="调整 max_connections",
                    resolution_time=15,
                )
            ],
            suggestion=RemediationSuggestion(
                summary="调高 Pod CPU limit 至 1000m",
                steps=["检查当前资源配置", "修改 deployment CPU limit"],
                commands=["kubectl set resources deployment/order-service --limits=cpu=1000m"],
                risks=["扩容可能导致节点资源紧张"],
                rollback_plan="恢复原 CPU limit",
                estimated_time="5分钟",
            ),
            impact_prediction={
                "affected_service": "order-service",
                "overall_risk": "high",
            },
            processing_time_seconds=2.5,
        )
    )
    return processor


def _create_real_processor() -> AlertProcessor:
    """Create a real AlertProcessor using configured credentials."""
    from langops.web.dependencies import get_langfuse, get_rca_engine, get_vector_store

    return AlertProcessor(
        langfuse=get_langfuse(),
        rca_engine=get_rca_engine(),
        vector_store=get_vector_store(),
    )


def _build_client(processor) -> Generator[TestClient, None, None]:
    """Build a TestClient with the given processor and SQLite storage."""
    sf = create_sqlite_session()
    dedup_repo = SqlDedupRepository(sf)
    remediation_repo = SqlRemediationRepository(sf)
    dedup = AlertNoiseReducer(repo=dedup_repo, window_seconds=900, enabled=True)
    remediation_registry = RemediationRegistry(repo=remediation_repo)

    app.dependency_overrides[get_alert_processor] = lambda: processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def mock_processor() -> MagicMock:
    """Mock AlertProcessor — for tests that explicitly need mock behavior."""
    return _make_mock_processor()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """TestClient with conditional real/mock processor.

    Uses real processor when LLM and Langfuse credentials are configured
    (non-test values) AND external services (ChromaDB) are reachable.
    Falls back to mock processor otherwise.
    """
    if USE_REAL_LLM and USE_REAL_LANGFUSE:
        try:
            processor = _create_real_processor()
        except Exception:
            processor = _make_mock_processor()
    else:
        processor = _make_mock_processor()

    yield from _build_client(processor)


# ── Sample alert payloads ───────────────────────────────────────────


@pytest.fixture
def k8s_alert_payload() -> dict:
    """Valid Kubernetes alert payload."""
    return {
        "title": "CPU使用率过高",
        "description": "order-service Pod CPU使用率超过90%，持续5分钟",
        "severity": "critical",
        "category": "resource",
        "source": {
            "type": "kubernetes",
            "system": "prod-cluster",
            "namespace": "production",
            "pod_name": "order-service-abc123",
        },
        "metric_data": {
            "cpu_usage_percent": 95.5,
            "memory_usage_percent": 78.2,
        },
    }


@pytest.fixture
def aliyun_ecs_alert_payload() -> dict:
    """Valid Aliyun ECS alert payload."""
    return {
        "title": "ECS CPU使用率过高",
        "description": "ecs-cn-hangzhou-xxx CPU使用率超过90%",
        "severity": "high",
        "category": "resource",
        "source": {
            "type": "aliyun",
            "system": "aliyun-prod",
            "instance_id": "i-cn-hangzhou-xxx",
            "resource_type": "ecs",
        },
    }


@pytest.fixture
def aliyun_rds_alert_payload() -> dict:
    """Valid Aliyun RDS alert payload."""
    return {
        "title": "RDS连接数过高",
        "description": "rm-cn-hangzhou-xxx 连接数超过80%",
        "severity": "high",
        "category": "availability",
        "source": {
            "type": "aliyun",
            "system": "aliyun-prod",
            "instance_id": "rm-cn-hangzhou-xxx",
            "resource_type": "rds",
        },
    }
