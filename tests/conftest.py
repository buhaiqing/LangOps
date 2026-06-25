"""pytest configuration and fixtures."""

import os
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from langops.agent.alert_processor import AlertProcessor
from langops.models import AnalysisResult, RemediationSuggestion, RootCause
from langops.services import AlertNoiseReducer
from langops.web.dependencies import get_alert_dedup, get_alert_processor
from langops.web.main import app

# Required before langops.core imports (Settings validates nested secrets at load time).
os.environ.setdefault("LLM_API_KEY", "sk-test")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-test")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture
def mock_processor() -> MagicMock:
    """Mock AlertProcessor for API tests without external services."""
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-123",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(summary="调高 limit", steps=["step1"]),
            processing_time_seconds=1.2,
        )
    )
    return processor


@pytest.fixture
def client(mock_processor: MagicMock) -> Generator[TestClient, None, None]:
    """Create test client with mocked alert processor."""
    dedup = AlertNoiseReducer(window_seconds=900, enabled=True)
    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
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
