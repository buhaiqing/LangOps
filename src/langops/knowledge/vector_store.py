"""Vector store implementation using ChromaDB."""

import hashlib
from typing import Any

import chromadb

from langops.core import get_logger
from langops.core.exceptions import VectorStoreError

logger = get_logger(__name__)


class SearchResult:
    """Vector search result."""

    def __init__(self, id: str, score: float, document: str, metadata: dict[str, Any]) -> None:
        self.id = id
        self.score = score
        self.document = document
        self.metadata = metadata

    def __repr__(self) -> str:
        return f"SearchResult(id={self.id}, score={self.score:.3f})"


class VectorStore:
    """Vector store for knowledge base using ChromaDB."""

    def __init__(
        self,
        collection_name: str = "ops_knowledge",
        host: str = "localhost",
        port: int = 8001,
        persist_directory: str | None = None,
    ) -> None:
        self.collection_name = collection_name
        self.host = host
        self.port = port

        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.client = chromadb.HttpClient(host=host, port=port)

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Operations knowledge base"},
        )

        logger.info("Vector store initialized", collection=collection_name, host=host, port=port)

    async def add_case(
        self,
        title: str,
        description: str,
        category: str,
        service: str,
        root_cause: str,
        solution: str,
        resolution_time: int | None = None,
        timestamp: str | None = None,
        case_id: str | None = None,
    ) -> str:
        """Add a failure case to the knowledge base."""
        if case_id is None:
            content = f"{title}{description}{timestamp or ''}"
            case_id = hashlib.md5(content.encode()).hexdigest()

        document = f"""
故障: {title}
描述: {description}
根因: {root_cause}
解决方案: {solution}
        """.strip()

        metadata: dict[str, Any] = {
            "title": title,
            "category": category,
            "service": service,
            "root_cause": root_cause,
            "solution": solution,
            "resolved": True,
        }
        if resolution_time is not None:
            metadata["resolution_time"] = resolution_time
        if timestamp is not None:
            metadata["timestamp"] = timestamp

        try:
            self.collection.add(
                ids=[case_id],
                documents=[document],
                metadatas=[metadata],
            )
            logger.info("Case added to knowledge base", case_id=case_id, title=title)
            return case_id
        except Exception as exc:
            logger.error("Failed to add case", error=str(exc))
            raise VectorStoreError(f"Failed to add case: {exc}") from exc

    async def search(
        self,
        query: str,
        top_k: int = 3,
        filter_category: str | None = None,
        filter_service: str | None = None,
    ) -> list[SearchResult]:
        """Search for similar cases."""
        where_filter: dict[str, Any] = {"resolved": True}
        if filter_category:
            where_filter["category"] = filter_category
        if filter_service:
            where_filter["service"] = filter_service

        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if len(where_filter) > 1 else None,
            )

            search_results: list[SearchResult] = []
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i]
                similarity = 1 / (1 + distance)
                search_results.append(
                    SearchResult(
                        id=results["ids"][0][i],
                        score=similarity,
                        document=results["documents"][0][i],
                        metadata=results["metadatas"][0][i],
                    )
                )

            logger.info("Knowledge search completed", query=query[:50], results=len(search_results))
            return search_results
        except Exception as exc:
            logger.error("Search failed", error=str(exc))
            raise VectorStoreError(f"Search failed: {exc}") from exc

    async def get_case(self, case_id: str) -> dict[str, Any] | None:
        """Get a specific case by ID."""
        try:
            result = self.collection.get(ids=[case_id])
            if result and result["ids"]:
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0],
                    "metadata": result["metadatas"][0],
                }
            return None
        except Exception as exc:
            logger.error("Failed to get case", case_id=case_id, error=str(exc))
            return None

    async def delete_case(self, case_id: str) -> bool:
        """Delete a case from the knowledge base."""
        try:
            self.collection.delete(ids=[case_id])
            logger.info("Case deleted", case_id=case_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete case", case_id=case_id, error=str(exc))
            return False

    async def count(self) -> int:
        """Get total number of cases in the knowledge base."""
        try:
            return int(self.collection.count())
        except Exception as exc:
            logger.error("Failed to count cases", error=str(exc))
            return 0
