"""RCA engine tests."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langops.agent.rca_engine import RCAEngine
from langops.core.exceptions import LLMError
from langops.models import RemediationSuggestion, RootCause, SimilarCase


@pytest.fixture
def rca_engine() -> RCAEngine:
    with patch("langops.agent.rca_engine.openai.AsyncOpenAI"):
        return RCAEngine(api_key="sk-test", model="gpt-4o-mini")


def _mock_completion(payload: dict[str, object]) -> MagicMock:
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_analyze_returns_root_cause(rca_engine: RCAEngine) -> None:
    rca_engine.client = MagicMock()
    rca_engine.client.chat.completions.create = AsyncMock(
        return_value=_mock_completion(
            {
                "root_cause_category": "资源不足",
                "description": "CPU limit 过低",
                "confidence": 0.9,
                "key_evidence": ["CPU 95%"],
                "related_metrics": ["cpu_usage"],
                "impact_analysis": "影响订单服务",
            }
        )
    )

    result = await rca_engine.analyze(
        alert_title="CPU高",
        alert_description="CPU > 90%",
        severity="critical",
        category="resource",
        source={"type": "kubernetes"},
        metrics={"cpu": 95},
        logs=["oom"],
        events=[{"type": "warning"}],
    )

    assert isinstance(result, RootCause)
    assert result.category == "资源不足"
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_analyze_raises_llm_error_on_invalid_json(rca_engine: RCAEngine) -> None:
    rca_engine.client = MagicMock()
    message = MagicMock()
    message.content = "not-json"
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    rca_engine.client.chat.completions.create = AsyncMock(return_value=response)

    with pytest.raises(LLMError, match="Invalid JSON"):
        await rca_engine.analyze(
            alert_title="t",
            alert_description="d",
            severity="high",
            category="resource",
            source={},
            metrics={},
            logs=[],
            events=[],
        )


@pytest.mark.asyncio
async def test_generate_remediation_returns_suggestion(rca_engine: RCAEngine) -> None:
    rca_engine.client = MagicMock()
    rca_engine.client.chat.completions.create = AsyncMock(
        return_value=_mock_completion(
            {
                "summary": "调高 CPU limit",
                "steps": ["检查 deployment", "修改 limit"],
                "commands": ["kubectl apply -f patch.yaml"],
                "risks": ["短暂重启"],
                "rollback_plan": "回滚 deployment",
                "estimated_time": "10分钟",
            }
        )
    )

    root_cause = RootCause(category="资源", description="desc", confidence=0.8)
    suggestion = await rca_engine.generate_remediation(
        root_cause=root_cause,
        similar_cases=[],
        alert_context={"service": "order"},
    )

    assert isinstance(suggestion, RemediationSuggestion)
    assert suggestion.summary == "调高 CPU limit"


@pytest.mark.asyncio
async def test_generate_remediation_falls_back_on_error(rca_engine: RCAEngine) -> None:
    rca_engine.client = MagicMock()
    rca_engine.client.chat.completions.create = AsyncMock(side_effect=RuntimeError("timeout"))

    root_cause = RootCause(category="资源", description="desc", confidence=0.8)
    suggestion = await rca_engine.generate_remediation(
        root_cause=root_cause,
        similar_cases=[
            SimilarCase(
                case_id="1",
                similarity_score=0.8,
                title="t",
                root_cause="r",
                solution="s",
            )
        ],
        alert_context={},
    )

    assert "无法生成具体修复建议" in suggestion.summary
