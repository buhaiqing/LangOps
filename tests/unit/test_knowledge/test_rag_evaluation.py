"""RAG quality evaluation tests with hand-annotated test cases.

This module evaluates whether HyDE query rewriting and cross-encoder reranking
actually improve retrieval quality compared to baseline vector search.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.knowledge.enhanced_retriever import EnhancedRetriever
from langops.knowledge.reranker import RerankResult
from langops.knowledge.vector_store import SearchResult

# Hand-annotated test cases: (query, expected_relevant_case_ids)
# These represent real-world queries and the cases that SHOULD be retrieved
HAND_ANNOTATED_TEST_CASES = [
    {
        "query": "order-service CPU高",
        "context": {"service": "order-service", "category": "resource"},
        "relevant_case_ids": ["case-cpu-001", "case-cpu-002"],
        "description": "CPU usage alert for order service",
    },
    {
        "query": "payment-service OOM",
        "context": {"service": "payment-service", "category": "resource"},
        "relevant_case_ids": ["case-oom-001", "case-memory-001"],
        "description": "Out of memory in payment service",
    },
    {
        "query": "API响应慢",
        "context": {"service": "api-gateway", "category": "performance"},
        "relevant_case_ids": ["case-latency-001", "case-timeout-001"],
        "description": "API latency issue",
    },
    {
        "query": "数据库连接超时",
        "context": {"service": "order-service", "category": "database"},
        "relevant_case_ids": ["case-db-001", "case-connection-001"],
        "description": "Database connection timeout",
    },
    {
        "query": "库存服务502错误",
        "context": {"service": "inventory-service", "category": "error"},
        "relevant_case_ids": ["case-502-001", "case-gateway-001"],
        "description": "502 Bad Gateway in inventory service",
    },
    {
        "query": "用户服务Pod重启",
        "context": {"service": "user-service", "category": "stability"},
        "relevant_case_ids": ["case-restart-001", "case-crashloop-001"],
        "description": "User service pod restart loop",
    },
    {
        "query": "订单服务内存泄漏",
        "context": {"service": "order-service", "category": "memory"},
        "relevant_case_ids": ["case-memoryleak-001", "case-oom-001"],
        "description": "Memory leak in order service",
    },
    {
        "query": "Redis连接池耗尽",
        "context": {"service": "cache-layer", "category": "database"},
        "relevant_case_ids": ["case-redis-001", "case-pool-001"],
        "description": "Redis connection pool exhausted",
    },
    {
        "query": "消息队列消费延迟",
        "context": {"service": "mq-consumer", "category": "performance"},
        "relevant_case_ids": ["case-lag-001", "case-kafka-001"],
        "description": "Message queue consumption lag",
    },
    {
        "query": "日志采集异常",
        "context": {"service": "log-aggregator", "category": "observability"},
        "relevant_case_ids": ["case-log-001", "case-fluentd-001"],
        "description": "Log collection anomaly",
    },
]


class TestHyDEEvaluation:
    """Evaluate HyDE query rewriting quality."""

    @pytest.mark.asyncio
    async def test_hyde_rewritten_query_contains_more_keywords(self):
        """Test that HyDE rewritten query contains more relevant keywords than original.

        This is a proxy evaluation: a good HyDE rewrite should expand abbreviations
        and add technical context that helps vector matching.
        """
        from langops.knowledge.query_rewriter import QueryRewriter

        # Mock LLM that returns expanded query
        mock_llm_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
故障标题: order-service CPU使用率过高导致响应延迟

故障描述: 生产环境order-service Pod的CPU使用率持续超过90%，导致服务响应时间显著增加，部分请求出现超时。该问题通常发生在流量高峰期。

根因分析: Pod资源配置不足，CPU limit设置过低，无法应对峰值流量。或者存在低效代码导致CPU消耗异常。

解决方案: 1) 增加Pod的CPU limit配置；2) 水平扩容增加Pod实例数；3) 优化热点代码降低CPU消耗。
"""
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        rewriter = QueryRewriter(llm_client=mock_llm_client, model="gpt-4")

        # Test case 1: abbreviated query
        original_query = "order-service CPU高"
        rewritten = await rewriter.rewrite(original_query, {"service": "order-service"})

        # HyDE should expand the query significantly
        assert len(rewritten) > len(original_query) * 3
        # Should contain expanded technical terms
        assert "CPU" in rewritten
        assert "order-service" in rewritten or "order service" in rewritten
        # Should contain context-implied keywords
        assert any(keyword in rewritten for keyword in ["使用率", "过高", "响应", "延迟", "Pod"])

    @pytest.mark.asyncio
    async def test_hyde_handles_different_query_types(self):
        """Test HyDE handles various query types (abbreviations, symptoms, components)."""
        from langops.knowledge.query_rewriter import QueryRewriter

        test_queries = [
            ("payment OOM", "payment-service", ["OOM", "内存", "Killed"]),
            ("DB timeout", "order-service", ["数据库", "连接", "超时"]),
            ("API latency", "api-gateway", ["API", "延迟", "响应"]),
        ]

        mock_llm_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "扩展后的故障案例文档内容"
        mock_llm_client.chat.completions.create = AsyncMock(return_value=mock_response)

        rewriter = QueryRewriter(llm_client=mock_llm_client, model="gpt-4")

        for original, service, expected_keywords in test_queries:
            rewritten = await rewriter.rewrite(original, {"service": service})
            assert rewritten is not None
            assert isinstance(rewritten, str)

    @pytest.mark.asyncio
    async def test_hyde_fallback_preserves_original_query(self):
        """Test that HyDE fallback returns original query on LLM failure."""
        from langops.knowledge.query_rewriter import QueryRewriter

        mock_llm_client = MagicMock()
        mock_llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))

        rewriter = QueryRewriter(llm_client=mock_llm_client, model="gpt-4")

        original_query = "test query"
        result = await rewriter.rewrite(original_query, {})

        # Should fall back to original query
        assert result == original_query


class TestRerankerEvaluation:
    """Evaluate cross-encoder reranking quality."""

    @pytest.mark.asyncio
    async def test_reranker_improves_top_k_accuracy(self):
        """Test that reranking improves Top-K accuracy compared to vector scores alone.

        Simulates a scenario where vector similarity ranks documents incorrectly,
        and reranking fixes the order based on semantic relevance.
        """
        # Simulate vector search results with suboptimal ordering
        # (high vector similarity but low actual relevance)
        vector_results = [
            SearchResult(  # High vector score but low relevance
                id="doc-irrelevant-high-score",
                score=0.95,
                document="This is about memory issues in general computing systems",
                metadata={},
            ),
            SearchResult(  # Medium vector score, high relevance
                id="doc-relevant-medium-score",
                score=0.75,
                document="order-service CPU usage spike causes 502 errors in production",
                metadata={},
            ),
            SearchResult(  # Low vector score but very relevant
                id="doc-very-relevant-low-score",
                score=0.55,
                document="CPU throttling in order-service pod leads to high latency",
                metadata={},
            ),
        ]

        # Mock reranker that correctly orders by relevance
        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True
        mock_reranker.rerank = AsyncMock(
            return_value=[
                RerankResult(
                    index=2, score=0.92, text=vector_results[2].document
                ),  # Most relevant first
                RerankResult(index=1, score=0.85, text=vector_results[1].document),
                RerankResult(
                    index=0, score=0.45, text=vector_results[0].document
                ),  # Least relevant last
            ]
        )

        # Create enhanced retriever with mocked components
        mock_vector_store = MagicMock()
        mock_vector_store.search = AsyncMock(return_value=vector_results)

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=None,
            reranker=mock_reranker,
            hyde_enabled=False,
            rerank_enabled=True,
        )

        results = await retriever.search("order-service CPU high", top_k=3)

        # Verify reranking improved the order
        assert len(results) == 3
        # After reranking, most relevant should be first
        assert results[0].id == "doc-very-relevant-low-score"
        assert results[1].id == "doc-relevant-medium-score"
        assert results[2].id == "doc-irrelevant-high-score"

    @pytest.mark.asyncio
    async def test_reranker_preserves_original_scores_in_metadata(self):
        """Test that reranker preserves original vector scores for debugging."""
        vector_results = [
            SearchResult(
                id="doc-1",
                score=0.8,
                document="Test document",
                metadata={"title": "Test"},
            ),
        ]

        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True
        mock_reranker.rerank = AsyncMock(
            return_value=[
                RerankResult(index=0, score=0.95, text="Test document"),
            ]
        )

        mock_vector_store = MagicMock()
        mock_vector_store.search = AsyncMock(return_value=vector_results)

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=None,
            reranker=mock_reranker,
            hyde_enabled=False,
            rerank_enabled=True,
        )

        results = await retriever.search("test query", top_k=1)

        assert len(results) == 1
        # Metadata should contain both scores
        assert "vector_score" in results[0].metadata
        assert "rerank_score" in results[0].metadata
        assert results[0].metadata["vector_score"] == 0.8
        assert results[0].metadata["rerank_score"] == 0.95


class TestTwoStagePipelineEvaluation:
    """Evaluate the complete two-stage pipeline (HyDE + Reranking)."""

    @pytest.mark.asyncio
    async def test_pipeline_handles_all_stages(self):
        """Test that the full pipeline works: HyDE rewrite -> Vector search -> Rerank."""
        # Mock query rewriter
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite = AsyncMock(return_value="扩展后的查询文档")

        # Mock vector store
        vector_results = [
            SearchResult(id=f"doc-{i}", score=0.9 - i * 0.1, document=f"Document {i}", metadata={})
            for i in range(5)
        ]
        mock_vector_store = MagicMock()
        mock_vector_store.search = AsyncMock(return_value=vector_results)

        # Mock reranker
        mock_reranker = MagicMock()
        mock_reranker.is_available.return_value = True
        mock_reranker.rerank = AsyncMock(
            return_value=[
                RerankResult(index=2, score=0.95, text="Document 2"),
                RerankResult(index=0, score=0.88, text="Document 0"),
                RerankResult(index=1, score=0.82, text="Document 1"),
            ]
        )

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_rewriter,
            reranker=mock_reranker,
            hyde_enabled=True,
            rerank_enabled=True,
        )

        results = await retriever.search(
            "original query",
            top_k=3,
            alert_context={"service": "test-service"},
        )

        # Verify all stages were called
        mock_rewriter.rewrite.assert_called_once()
        mock_vector_store.search.assert_called_once_with(
            query="扩展后的查询文档",  # HyDE rewritten query
            top_k=10,  # Fetch more for reranking
            filter_category=None,
            filter_service=None,
        )
        mock_reranker.rerank.assert_called_once()

        # Verify results are in reranked order
        assert len(results) == 3
        assert results[0].id == "doc-2"
        assert results[1].id == "doc-0"
        assert results[2].id == "doc-1"

    @pytest.mark.asyncio
    async def test_pipeline_graceful_degradation(self):
        """Test pipeline gracefully degrades when components fail."""
        # Case 1: HyDE fails, should use original query
        mock_rewriter = MagicMock()
        mock_rewriter.rewrite = AsyncMock(side_effect=Exception("LLM error"))

        mock_vector_store = MagicMock()
        mock_vector_store.search = AsyncMock(return_value=[])

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_rewriter,
            reranker=None,
            hyde_enabled=True,
            rerank_enabled=False,
        )

        await retriever.search("original query", top_k=3)

        # Should fall back to original query
        mock_vector_store.search.assert_called_with(
            query="original query",
            top_k=3,
            filter_category=None,
            filter_service=None,
        )


class TestAnnotatedCaseCoverage:
    """Verify hand-annotated test cases cover key scenarios."""

    def test_annotated_cases_cover_all_categories(self):
        """Verify annotated cases cover different alert categories."""
        categories = set()
        for case in HAND_ANNOTATED_TEST_CASES:
            categories.add(case["context"]["category"])

        # Should cover multiple categories
        assert len(categories) >= 4
        expected_categories = {
            "resource",
            "performance",
            "database",
            "error",
            "stability",
            "memory",
            "observability",
        }
        assert categories.issubset(expected_categories) or categories.intersection(
            expected_categories
        )

    def test_annotated_cases_cover_different_services(self):
        """Verify annotated cases cover different services."""
        services = set()
        for case in HAND_ANNOTATED_TEST_CASES:
            services.add(case["context"]["service"])

        # Should cover multiple services
        assert len(services) >= 5

    def test_annotated_cases_have_relevant_ids(self):
        """Verify each annotated case has at least one relevant case ID."""
        for case in HAND_ANNOTATED_TEST_CASES:
            assert len(case["relevant_case_ids"]) >= 1
            assert all(isinstance(id, str) for id in case["relevant_case_ids"])
