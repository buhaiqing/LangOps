"""Tests for QueryRewriter - HyDE query expansion."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.knowledge.query_rewriter import QueryRewriter


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    return client


@pytest.fixture
def query_rewriter(mock_llm_client):
    """Create a QueryRewriter instance with mock LLM."""
    return QueryRewriter(llm_client=mock_llm_client, model="gpt-4")


class TestQueryRewriter:
    """Test suite for QueryRewriter."""

    @pytest.mark.asyncio
    async def test_rewrite_returns_hypothetical_document(self, query_rewriter, mock_llm_client):
        """Test that rewrite returns a hypothetical document based on the query."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
故障标题: order-service CPU使用率过高

故障描述: 生产环境 order-service Pod CPU使用率持续超过90%，导致服务响应延迟增加，部分请求超时。

根因分析: Pod资源配置不足，CPU limit设置过低，无法应对峰值流量。

解决方案: 增加CPU limit配置，水平扩容Pod实例数。
"""
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        query = "order-service CPU高"
        alert_context = {"service": "order-service", "namespace": "production"}

        # Act
        result = await query_rewriter.rewrite(query, alert_context)

        # Assert
        assert result is not None
        assert len(result) > len(query)
        assert "CPU" in result
        assert "order-service" in result
        # Verify LLM was called with correct parameters
        mock_llm_client.chat.completions.create.assert_called_once()
        call_args = mock_llm_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4"
        assert call_args.kwargs["temperature"] == 0.3

    @pytest.mark.asyncio
    async def test_rewrite_handles_empty_context(self, query_rewriter, mock_llm_client):
        """Test that rewrite works with minimal context."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "假设故障案例文档内容"
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        query = "数据库连接超时"
        alert_context = {}

        result = await query_rewriter.rewrite(query, alert_context)

        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_rewrite_preserves_key_entities(self, query_rewriter, mock_llm_client):
        """Test that rewritten document preserves key entities from query."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
故障: payment-service 内存不足
描述: payment-service Pod 出现 OOMKilled，内存使用率持续100%
根因: 内存泄漏导致
解决: 重启服务，增加内存配置
"""
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        query = "payment-service OOM"
        alert_context = {"service": "payment-service"}

        result = await query_rewriter.rewrite(query, alert_context)

        # The result should be the hypothetical document
        assert "payment-service" in result or "内存" in result or "OOM" in result

    @pytest.mark.asyncio
    async def test_rewrite_handles_llm_error(self, query_rewriter, mock_llm_client):
        """Test that rewrite returns original query when LLM fails."""
        mock_llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM API error"))

        query = "测试查询"
        alert_context = {}

        # Should not raise, should return original query as fallback
        result = await query_rewriter.rewrite(query, alert_context)

        assert result == query  # Fallback to original query

    @pytest.mark.asyncio
    async def test_rewrite_prompt_contains_query_and_context(self, query_rewriter, mock_llm_client):
        """Test that the prompt includes query and alert context."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "假设文档"
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        query = "API响应慢"
        alert_context = {"service": "api-gateway", "severity": "high"}

        await query_rewriter.rewrite(query, alert_context)

        # Check that the prompt contains query and context
        call_args = mock_llm_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_message = messages[1]["content"]  # User message is second

        assert query in user_message
        assert "api-gateway" in user_message
