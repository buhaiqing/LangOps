"""Analysis model tests."""

import pytest
from pydantic import ValidationError

from langops.models import (
    AnalysisResponse,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
    SimilarCase,
)


def test_root_cause_validates_confidence_bounds() -> None:
    root = RootCause(category="资源不足", description="CPU limit 过低", confidence=0.92)
    assert root.confidence == 0.92

    with pytest.raises(ValidationError):
        RootCause(category="资源", description="desc", confidence=1.5)


def test_similar_case_model() -> None:
    case = SimilarCase(
        case_id="case-001",
        similarity_score=0.88,
        title="历史 CPU 告警",
        root_cause="limit 过低",
        solution="调高 limit",
        resolution_time=30,
    )
    assert case.case_id == "case-001"
    assert case.similarity_score == 0.88


def test_analysis_result_requires_trace_id() -> None:
    result = AnalysisResult(
        alert_id="alert-001",
        trace_id="trace-abc",
        root_cause=RootCause(category="资源", description="desc", confidence=0.8),
        suggestion=RemediationSuggestion(summary="扩容", steps=["step1"]),
        processing_time_seconds=12.5,
    )
    assert result.trace_id == "trace-abc"
    assert result.processing_time_seconds == 12.5
    assert result.similar_cases == []


def test_analysis_response_success_and_failure() -> None:
    ok = AnalysisResponse(success=True, data=None, error=None)
    fail = AnalysisResponse(success=False, error="LLM timeout")
    assert ok.success is True
    assert fail.error == "LLM timeout"
