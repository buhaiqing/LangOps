"""Cross-Encoder Reranker for precise relevance scoring."""

import math
from dataclasses import dataclass
from typing import Any

from langops.core import get_logger

logger = get_logger(__name__)


@dataclass
class RerankResult:
    """Result of re-ranking a single document."""

    index: int  # Original index in the input list
    score: float  # Relevance score (0-1)
    text: str  # Document text


class Reranker:
    """
    Cross-encoder based reranker for precise relevance scoring.

    Uses a cross-encoder model to score query-document pairs more accurately
    than bi-encoder vector similarity alone.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize the reranker with a cross-encoder model.

        Args:
            model_name: HuggingFace model name for cross-encoder
                       Default is ms-marco-MiniLM-L-6-v2 (fast, good quality)
        """
        self.model_name = model_name
        self._model: Any | None = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the cross-encoder model."""
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            logger.info("Cross-encoder model loaded", model=self.model_name)
        except Exception as exc:
            logger.error(
                "Failed to load cross-encoder model",
                model=self.model_name,
                error=str(exc),
            )
            self._model = None

    def is_available(self) -> bool:
        """Check if the reranker is available (model loaded successfully)."""
        return self._model is not None

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 3,
    ) -> list[RerankResult]:
        """
        Rerank documents by relevance to the query.

        Args:
            query: Search query
            documents: List of document texts to rerank
            top_k: Number of top results to return

        Returns:
            List of RerankResult, sorted by score (highest first)
        """
        if not self.is_available():
            logger.warning("Reranker unavailable, returning empty results")
            return []

        if not documents:
            return []

        try:
            # Create query-document pairs for cross-encoder
            pairs = [(query, doc) for doc in documents]

            # Get scores from cross-encoder (runs in thread to avoid blocking)
            import asyncio

            model = self._model
            if model is None:
                return []
            scores = await asyncio.to_thread(model.predict, pairs)

            # Apply sigmoid to normalize scores to 0-1 range
            # Cross-encoder outputs logits, sigmoid converts to probabilities
            normalized_scores = [self._sigmoid(score) for score in scores]

            # Create results with original indices
            results = [
                RerankResult(index=i, score=score, text=documents[i])
                for i, score in enumerate(normalized_scores)
            ]

            # Sort by score descending
            results.sort(key=lambda x: x.score, reverse=True)

            logger.info(
                "Documents reranked",
                query=query[:50],
                num_docs=len(documents),
                top_score=results[0].score if results else 0,
            )

            return results[:top_k]

        except Exception as exc:
            logger.error(
                "Reranking failed",
                query=query[:50],
                error=str(exc),
            )
            return []

    def _sigmoid(self, x: float) -> float:
        """Apply sigmoid function to normalize score to 0-1 range."""
        return 1 / (1 + math.exp(-x))
