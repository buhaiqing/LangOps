"""Tests for Reranker - Cross-Encoder re-ranking."""

from unittest.mock import MagicMock, patch

import pytest

from langops.knowledge.reranker import RerankResult


# Import Reranker after patching
@pytest.fixture
def reranker_class():
    with patch("sentence_transformers.CrossEncoder") as mock_ce:
        mock_ce.return_value = MagicMock()
        from langops.knowledge.reranker import Reranker

        yield Reranker, mock_ce


class TestRerankResult:
    """Test suite for RerankResult dataclass."""

    def test_rerank_result_creation(self):
        """Test creating a RerankResult."""
        result = RerankResult(index=0, score=0.95, text="document text")
        assert result.index == 0
        assert result.score == 0.95
        assert result.text == "document text"


class TestReranker:
    """Test suite for Reranker."""

    def test_init_with_default_model(self):
        """Test initialization with default model."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            mock_ce.return_value = MagicMock()
            from langops.knowledge.reranker import Reranker

            reranker = Reranker()
            assert reranker.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_ce.assert_called_once_with("cross-encoder/ms-marco-MiniLM-L-6-v2")

    def test_init_with_custom_model(self):
        """Test initialization with custom model."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            mock_ce.return_value = MagicMock()
            from langops.knowledge.reranker import Reranker

            reranker = Reranker(model_name="custom-model")
            assert reranker.model_name == "custom-model"

    @pytest.mark.asyncio
    async def test_rerank_returns_sorted_results(self):
        """Test that rerank returns sorted results by score."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_model = MagicMock()
            # Simulate scores for 3 documents
            mock_model.predict = MagicMock(return_value=[0.5, 0.9, 0.3])
            mock_ce.return_value = mock_model

            reranker = Reranker()
            query = "CPU high usage"
            documents = [
                "Memory issue in service",
                "CPU usage spike detected in pod",
                "Network timeout error",
            ]

            results = await reranker.rerank(query, documents, top_k=2)

            assert len(results) == 2
            # Highest score should be first (index 1 with raw score 0.9)
            assert results[0].index == 1  # Index 1 had highest raw score
            assert results[0].score > results[1].score  # Descending order
            assert results[1].index == 0

    @pytest.mark.asyncio
    async def test_rerank_respects_top_k(self):
        """Test that rerank respects top_k parameter."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_model = MagicMock()
            mock_model.predict = MagicMock(return_value=[0.1, 0.2, 0.3, 0.4, 0.5])
            mock_ce.return_value = mock_model

            reranker = Reranker()
            query = "test query"
            documents = ["doc1", "doc2", "doc3", "doc4", "doc5"]

            results = await reranker.rerank(query, documents, top_k=3)

            assert len(results) == 3

    @pytest.mark.asyncio
    async def test_rerank_handles_empty_documents(self):
        """Test that rerank handles empty document list."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_ce.return_value = MagicMock()

            reranker = Reranker()
            results = await reranker.rerank("query", [], top_k=3)

            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_rerank_includes_document_text(self):
        """Test that rerank results include document text."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_model = MagicMock()
            mock_model.predict = MagicMock(return_value=[0.8])
            mock_ce.return_value = mock_model

            reranker = Reranker()
            query = "test"
            documents = ["single document"]

            results = await reranker.rerank(query, documents, top_k=1)

            assert len(results) == 1
            assert results[0].text == "single document"

    @pytest.mark.asyncio
    async def test_rerank_normalizes_scores_to_0_1(self):
        """Test that scores are normalized to 0-1 range."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_model = MagicMock()
            # Raw logits that need sigmoid normalization
            mock_model.predict = MagicMock(return_value=[-2.0, 0.0, 2.0])
            mock_ce.return_value = mock_model

            reranker = Reranker()
            query = "test"
            documents = ["doc1", "doc2", "doc3"]

            results = await reranker.rerank(query, documents, top_k=3)

            # All scores should be between 0 and 1 after sigmoid
            for result in results:
                assert 0 <= result.score <= 1

    def test_is_available_true(self):
        """Test is_available returns True when model loads."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_ce.return_value = MagicMock()
            reranker = Reranker()
            assert reranker.is_available() is True

    def test_is_available_false(self):
        """Test is_available returns False when model fails to load."""
        with patch("sentence_transformers.CrossEncoder") as mock_ce:
            from langops.knowledge.reranker import Reranker

            mock_ce.side_effect = Exception("Model not found")
            reranker = Reranker()
            assert reranker.is_available() is False
