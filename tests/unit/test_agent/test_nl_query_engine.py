"""NL query engine tests."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from langops.agent.nl_query_engine import NLQueryEngine
from langops.core.exceptions import LLMError


@pytest.fixture
def prometheus() -> MagicMock:
    collector = MagicMock()
    collector.query_instant = AsyncMock(
        return_value=[{"metric": {"pod": "order"}, "value": "0.92", "timestamp": 1.0}]
    )
    return collector


@pytest.fixture
def engine(prometheus: MagicMock) -> NLQueryEngine:
    with patch("langops.agent.nl_query_engine.openai.AsyncOpenAI"):
        return NLQueryEngine(
            api_key="sk-test",
            model="gpt-4",
            prometheus_collector=prometheus,
        )


@pytest.mark.asyncio
async def test_process_returns_answer_when_promql_generated(engine: NLQueryEngine) -> None:
    conversion = {
        "promql": "sum(rate(container_cpu_usage_seconds_total[5m]))",
        "time_range": "1h",
        "explanation": "CPU 使用率",
    }
    interpretation = {"answer": "order-service CPU 较高"}

    engine._convert_to_promql = AsyncMock(return_value=conversion)
    engine._interpret_results = AsyncMock(return_value=interpretation["answer"])

    result = await engine.process("哪些服务 CPU 高")

    assert result.promql == conversion["promql"]
    assert result.answer == interpretation["answer"]
    assert len(result.data) == 1


@pytest.mark.asyncio
async def test_process_returns_explanation_when_promql_is_null(engine: NLQueryEngine) -> None:
    engine._convert_to_promql = AsyncMock(
        return_value={"promql": None, "explanation": "问题过于模糊", "time_range": "1h"}
    )

    result = await engine.process("帮我看看")

    assert result.promql is None
    assert "模糊" in result.answer


@pytest.mark.asyncio
async def test_convert_to_promql_raises_llm_error_on_invalid_json(engine: NLQueryEngine) -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="not-json"))]
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    engine.client = mock_client

    with pytest.raises(LLMError, match="Invalid JSON"):
        await engine._convert_to_promql("CPU 情况")


@pytest.mark.asyncio
async def test_interpret_results_handles_empty_data(engine: NLQueryEngine) -> None:
    answer = await engine._interpret_results("CPU?", "up", [])
    assert "未返回数据" in answer
