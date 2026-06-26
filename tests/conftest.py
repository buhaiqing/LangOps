"""pytest configuration and fixtures."""

import os

from dotenv import load_dotenv

# Load .env FIRST so real credentials (if present) are available.
# setdefault below only fills in vars that .env didn't provide.
load_dotenv(override=False)

# ── MUST be set BEFORE any langops imports ──────────────────────────
# langops.core.config is evaluated at module scope: `settings = get_settings()`
# which validates LLMSettings.api_key (required). Without these env vars,
# every test collection that touches langops fails with ValidationError.
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("LLM_MODEL", "gpt-4")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

from collections.abc import Generator  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from langops.agent.alert_processor import AlertProcessor  # noqa: E402
from langops.models import AnalysisResult, RemediationSuggestion, RootCause  # noqa: E402
from langops.services import AlertNoiseReducer, RemediationRegistry  # noqa: E402
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository  # noqa: E402
from langops.web.dependencies import (  # noqa: E402
    get_alert_dedup,
    get_alert_processor,
    get_remediation_registry,
)
from langops.web.main import app  # noqa: E402


@pytest.fixture
def mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-123",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(
                summary="调高 limit",
                steps=["step1"],
                commands=["kubectl scale deployment/order --replicas=3"],
            ),
            processing_time_seconds=1.2,
        )
    )
    return processor


@pytest.fixture
def client(mock_processor: MagicMock) -> Generator[TestClient, None, None]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from langops.storage.models import Base

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
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def sample_alert_data() -> dict:
    """Sample alert data for testing."""
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
