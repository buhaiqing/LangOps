"""Tests for EnhancedRetriever - Two-stage retrieval with HyDE and re-ranking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.knowledge.enhanced_retriever import EnhancedRetriever
from langops.knowledge.vector_store import SearchResult


@pytest.fixture
def mock_vector_store():
    """Create a mock VectorStore."""
    store = MagicMock()
    store.search = AsyncMock()
    return store


@pytest.fixture
def mock_query_rewriter():
    """Create a mock QueryRewriter."""
    rewriter = MagicMock()
    rewriter.rewrite = AsyncMock()
    return rewriter


@pytest.fixture
def mock_reranker():
    """Create a mock Reranker."""
    reranker = MagicMock()
    reranker.rerank = AsyncMock()
    reranker.is_available = MagicMock(return_value=True)
    return reranker


class TestEnhancedRetriever:
    """Test suite for EnhancedRetriever."""

    @pytest.mark.asyncio
    async def test_search_with_hyde_and_rerank(
        self, mock_vector_store, mock_query_rewriter, mock_reranker
    ):
        """Test full two-stage search with HyDE and re-ranking enabled."""
        # Arrange
        mock_query_rewriter.rewrite.return_value = "改写后的查询文档"

        # Mock vector store returns 5 results
        vector_results = [
            SearchResult(id="1", score=0.8, document="doc1", metadata={}),
            SearchResult(id="2", score=0.75, document="doc2", metadata={}),
            SearchResult(id="3", score=0.7, document="doc3", metadata={}),
            SearchResult(id="4", score=0.65, document="doc4", metadata={}),
            SearchResult(id="5", score=0.6, document="doc5", metadata={}),
        ]
        mock_vector_store.search.return_value = vector_results

        # Mock reranker returns reordered results
        from langops.knowledge.reranker import RerankResult

        mock_reranker.rerank.return_value = [
            RerankResult(index=2, score=0.95, text="doc3"),  # Originally index 2
            RerankResult(index=0, score=0.85, text="doc1"),  # Originally index 0
            RerankResult(index=1, score=0.75, text="doc2"),  # Originally index 1
        ]

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_query_rewriter,
            reranker=mock_reranker,
            hyde_enabled=True,
            rerank_enabled=True,
        )

        # Act
        results = await retriever.search("原始查询", top_k=3)

        # Assert
        assert len(results) == 3
        # Verify HyDE was applied
        mock_query_rewriter.rewrite.assert_called_once()
        # Verify vector search with expanded query
        mock_vector_store.search.assert_called_once_with(
            query="改写后的查询文档",
            top_k=10,  # Fetch more for re-ranking
            filter_category=None,
            filter_service=None,
        )
        # Verify re-ranking was applied
        mock_reranker.rerank.assert_called_once()
        # Results should be in re-ranked order
        assert results[0].id == "3"  # Best after re-ranking
        assert results[1].id == "1"
        assert results[2].id == "2"

    @pytest.mark.asyncio
    async def test_search_without_hyde(self, mock_vector_store, mock_reranker):
        """Test search with HyDE disabled."""
        mock_vector_store.search.return_value = [
            SearchResult(id="1", score=0.9, document="doc1", metadata={}),
        ]
        mock_reranker.rerank.return_value = []

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=None,
            reranker=mock_reranker,
            hyde_enabled=False,
            rerank_enabled=True,
        )

        await retriever.search("原始查询", top_k=3)

        # Verify original query was used
        mock_vector_store.search.assert_called_once_with(
            query="原始查询",  # Not rewritten
            top_k=10,
            filter_category=None,
            filter_service=None,
        )

    @pytest.mark.asyncio
    async def test_search_without_rerank(self, mock_vector_store, mock_query_rewriter):
        """Test search with re-ranking disabled."""
        mock_query_rewriter.rewrite.return_value = "改写查询"
        mock_vector_store.search.return_value = [
            SearchResult(id="1", score=0.9, document="doc1", metadata={}),
            SearchResult(id="2", score=0.8, document="doc2", metadata={}),
        ]

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_query_rewriter,
            reranker=None,
            hyde_enabled=True,
            rerank_enabled=False,
        )

        results = await retriever.search("查询", top_k=2)

        assert len(results) == 2
        # Results should be in original vector search order
        assert results[0].id == "1"
        assert results[1].id == "2"

    @pytest.mark.asyncio
    async def test_search_with_filters(self, mock_vector_store, mock_query_rewriter):
        """Test search with category and service filters."""
        mock_query_rewriter.rewrite.return_value = "改写"
        mock_vector_store.search.return_value = []

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_query_rewriter,
            reranker=None,
            hyde_enabled=True,
            rerank_enabled=False,
        )

        await retriever.search(
            "查询", top_k=3, filter_category="resource", filter_service="order-service"
        )

        mock_vector_store.search.assert_called_with(
            query="改写",
            top_k=3,  # No rerank, so use original top_k
            filter_category="resource",
            filter_service="order-service",
        )

    @pytest.mark.asyncio
    async def test_search_falls_back_when_reranker_unavailable(self, mock_vector_store):
        """Test fallback to vector results when reranker is unavailable."""
        mock_vector_store.search.return_value = [
            SearchResult(id="1", score=0.9, document="doc1", metadata={}),
            SearchResult(id="2", score=0.8, document="doc2", metadata={}),
        ]

        unavailable_reranker = MagicMock()
        unavailable_reranker.is_available.return_value = False

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=None,
            reranker=unavailable_reranker,
            hyde_enabled=False,
            rerank_enabled=True,  # Enabled but unavailable
        )

        results = await retriever.search("查询", top_k=2)

        # Should still return vector search results
        assert len(results) == 2
        unavailable_reranker.rerank.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_hyde_fallback_on_error(self, mock_vector_store, mock_query_rewriter):
        """Test fallback to original query when HyDE fails."""
        mock_query_rewriter.rewrite.side_effect = Exception("LLM error")
        mock_vector_store.search.return_value = []

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_query_rewriter,
            reranker=None,
            hyde_enabled=True,
            rerank_enabled=False,
        )

        await retriever.search("原始查询", top_k=3)

        # Should fall back to original query
        mock_vector_store.search.assert_called_with(
            query="原始查询",  # Fallback
            top_k=3,
            filter_category=None,
            filter_service=None,
        )

    @pytest.mark.asyncio
    async def test_search_passes_alert_context_to_rewriter(
        self, mock_vector_store, mock_query_rewriter
    ):
        """Test that alert context is passed to query rewriter."""
        mock_query_rewriter.rewrite.return_value = "改写"
        mock_vector_store.search.return_value = []

        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=mock_query_rewriter,
            reranker=None,
            hyde_enabled=True,
            rerank_enabled=False,
        )

        alert_context = {"service": "api-gateway", "severity": "critical"}
        await retriever.search("查询", top_k=3, alert_context=alert_context)

        mock_query_rewriter.rewrite.assert_called_with("查询", alert_context)

    def test_backward_compatibility_disabled(self, mock_vector_store):
        """Test backward compatibility - when disabled, behaves like original VectorStore."""
        retriever = EnhancedRetriever(
            vector_store=mock_vector_store,
            query_rewriter=None,
            reranker=None,
            hyde_enabled=False,
            rerank_enabled=False,
        )

        # When both disabled, should just pass through to vector store
        assert retriever.hyde_enabled is False
        assert retriever.rerank_enabled is False
