"""Enhanced retriever with HyDE and cross-encoder reranking."""

from typing import Any

from langops.core import get_logger
from langops.knowledge.reranker import Reranker, RerankResult
from langops.knowledge.vector_store import SearchResult, VectorStore

logger = get_logger(__name__)


class EnhancedRetriever:
    """
    Two-stage retriever combining HyDE query rewriting and cross-encoder reranking.

    Stage 1: Optional HyDE query expansion to bridge semantic gap
    Stage 2: Vector similarity search (ChromaDB)
    Stage 3: Optional cross-encoder reranking for precise relevance
    """

    def __init__(
        self,
        vector_store: VectorStore,
        query_rewriter: Any | None = None,
        reranker: Reranker | None = None,
        hyde_enabled: bool = True,
        rerank_enabled: bool = True,
        rerank_fetch_k: int = 10,
    ):
        """
        Initialize the enhanced retriever.

        Args:
            vector_store: Base vector store for initial retrieval
            query_rewriter: HyDE query rewriter (optional)
            reranker: Cross-encoder reranker (optional)
            hyde_enabled: Whether to enable HyDE query rewriting
            rerank_enabled: Whether to enable reranking
            rerank_fetch_k: Number of documents to fetch for reranking
        """
        self.vector_store = vector_store
        self.query_rewriter = query_rewriter
        self.reranker = reranker
        self.hyde_enabled = hyde_enabled and query_rewriter is not None
        self.rerank_enabled = rerank_enabled and reranker is not None
        self.rerank_fetch_k = rerank_fetch_k

    async def search(
        self,
        query: str,
        top_k: int = 3,
        filter_category: str | None = None,
        filter_service: str | None = None,
        alert_context: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Search with optional HyDE and reranking.

        Args:
            query: Search query
            top_k: Number of results to return
            filter_category: Filter by category
            filter_service: Filter by service
            alert_context: Additional context for HyDE rewriting

        Returns:
            List of SearchResult, reranked if enabled
        """
        # Stage 1: Optional HyDE query rewriting
        search_query = query
        if self.hyde_enabled and self.query_rewriter:
            try:
                search_query = await self.query_rewriter.rewrite(query, alert_context)
                if search_query != query:
                    logger.info(
                        "HyDE query rewriting applied",
                        original=query[:50],
                        rewritten=search_query[:50],
                    )
            except Exception as exc:
                logger.warning(
                    "HyDE rewriting failed, using original query",
                    error=str(exc),
                )
                search_query = query

        # Stage 2: Vector similarity search
        # If reranking is enabled, fetch more documents for reranking
        fetch_k = self.rerank_fetch_k if self.rerank_enabled else top_k

        try:
            vector_results = await self.vector_store.search(
                query=search_query,
                top_k=fetch_k,
                filter_category=filter_category,
                filter_service=filter_service,
            )
        except Exception as exc:
            logger.error("Vector search failed", error=str(exc))
            return []

        if not vector_results:
            return []

        # If no reranking, return vector results directly
        if not self.rerank_enabled or not self.reranker or not self.reranker.is_available():
            logger.debug("Reranking disabled or unavailable, returning vector results")
            return vector_results[:top_k]

        # Stage 3: Cross-encoder reranking
        try:
            # Extract document texts for reranking
            documents = [result.document for result in vector_results]

            # Use original query (not rewritten) for reranking
            # Reranker should score based on original user intent
            rerank_results = await self.reranker.rerank(
                query=query,  # Use original query for reranking
                documents=documents,
                top_k=top_k,
            )

            # Map rerank results back to SearchResult objects
            final_results = self._map_rerank_to_results(vector_results, rerank_results)

            logger.info(
                "Enhanced retrieval completed",
                query=query[:50],
                hyde=self.hyde_enabled,
                rerank=self.rerank_enabled,
                num_results=len(final_results),
            )

            return final_results

        except Exception as exc:
            logger.warning(
                "Reranking failed, falling back to vector results",
                error=str(exc),
            )
            return vector_results[:top_k]

    def _map_rerank_to_results(
        self,
        vector_results: list[SearchResult],
        rerank_results: list[RerankResult],
    ) -> list[SearchResult]:
        """
        Map rerank results back to SearchResult objects with updated scores.

        Args:
            vector_results: Original vector search results
            rerank_results: Reranked results with indices

        Returns:
            List of SearchResult ordered by rerank score
        """
        # Create a lookup map from index to vector result
        result_map = {i: result for i, result in enumerate(vector_results)}

        # Build final results in reranked order
        final_results = []
        for rr in rerank_results:
            if rr.index in result_map:
                original = result_map[rr.index]
                # Create new SearchResult with reranked score
                final_results.append(
                    SearchResult(
                        id=original.id,
                        score=rr.score,  # Use rerank score
                        document=original.document,
                        metadata={
                            **original.metadata,
                            "vector_score": original.score,  # Preserve original
                            "rerank_score": rr.score,
                        },
                    )
                )

        return final_results
