"""System-level integration test fixtures.

Real FastAPI app + mocked external dependencies (LLM, Prometheus, ChromaDB).
Validates the full alert pipeline from HTTP request to response.
"""

import os

# ── Env vars before any langops import ──────────────────────────────
os.environ.setdefault("LLM_API_KEY", "sk-test-system")
os.environ.setdefault("LLM_MODEL", "gpt-4")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test-system")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test-system")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from collections.abc import Generator  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

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


@pytest.fixture
def mock_processor() -> MagicMock:
    """Mock AlertProcessor that returns a realistic analysis result."""
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


@pytest.fixture
def client(mock_processor: MagicMock) -> Generator[TestClient, None, None]:
    """TestClient with mocked processor and real SQLite storage."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sf = sessionmaker(bind=engine)

    dedup_repo = SqlDedupRepository(sf)
    remediation_repo = SqlRemediationRepository(sf)
    dedup = AlertNoiseReducer(repo=dedup_repo, window_seconds=900, enabled=True)
    remediation_registry = RemediationRegistry(repo=remediation_repo)

    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.clear()


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
