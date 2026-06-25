"""Vector store tests."""

from unittest.mock import MagicMock, patch

import pytest

from langops.core.exceptions import VectorStoreError
from langops.knowledge import SearchResult, VectorStore


def test_search_result_repr() -> None:
    result = SearchResult(id="case-1", score=0.85, document="doc", metadata={"title": "t"})
    assert "case-1" in repr(result)
    assert "0.850" in repr(result)


@pytest.fixture
def mock_collection() -> MagicMock:
    collection = MagicMock()
    collection.count.return_value = 2
    return collection


@pytest.fixture
def vector_store(mock_collection: MagicMock) -> VectorStore:
    with patch("langops.knowledge.vector_store.chromadb.HttpClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_client_cls.return_value = mock_client
        store = VectorStore(collection_name="ops_knowledge", host="localhost", port=8001)
    return store


@pytest.mark.asyncio
async def test_add_case_returns_id_and_calls_chroma(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    case_id = await vector_store.add_case(
        title="CPU 过高",
        description="Pod CPU 超限",
        category="resource",
        service="order",
        root_cause="limit 过低",
        solution="调高 limit",
        resolution_time=15,
        case_id="custom-id",
    )

    assert case_id == "custom-id"
    mock_collection.add.assert_called_once()
    args = mock_collection.add.call_args.kwargs
    assert args["ids"] == ["custom-id"]
    assert "CPU 过高" in args["documents"][0]


@pytest.mark.asyncio
async def test_add_case_generates_deterministic_id(vector_store: VectorStore) -> None:
    case_id = await vector_store.add_case(
        title="磁盘满",
        description="磁盘使用率 100%",
        category="resource",
        service="db",
        root_cause="日志未清理",
        solution="清理日志",
    )

    assert len(case_id) == 32


@pytest.mark.asyncio
async def test_add_case_raises_vector_store_error(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    mock_collection.add.side_effect = RuntimeError("chroma down")

    with pytest.raises(VectorStoreError, match="Failed to add case"):
        await vector_store.add_case(
            title="t",
            description="d",
            category="c",
            service="s",
            root_cause="r",
            solution="sol",
        )


@pytest.mark.asyncio
async def test_search_returns_similarity_scores(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    mock_collection.query.return_value = {
        "ids": [["case-1"]],
        "documents": [["故障: CPU"]],
        "metadatas": [[{"title": "CPU", "resolved": True}]],
        "distances": [[0.25]],
    }

    results = await vector_store.search("CPU 告警", top_k=3)

    assert len(results) == 1
    assert results[0].id == "case-1"
    assert results[0].score == pytest.approx(0.8)
    mock_collection.query.assert_called_once()


@pytest.mark.asyncio
async def test_search_applies_category_filter(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    mock_collection.query.return_value = {
        "ids": [[]],
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
    }

    await vector_store.search("query", filter_category="resource")

    assert mock_collection.query.call_args.kwargs["where"] == {
        "resolved": True,
        "category": "resource",
    }


@pytest.mark.asyncio
async def test_get_case_returns_metadata(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    mock_collection.get.return_value = {
        "ids": ["case-1"],
        "documents": ["doc"],
        "metadatas": [{"title": "CPU"}],
    }

    case = await vector_store.get_case("case-1")

    assert case is not None
    assert case["id"] == "case-1"
    assert case["metadata"]["title"] == "CPU"


@pytest.mark.asyncio
async def test_get_case_returns_none_when_missing(
    vector_store: VectorStore, mock_collection: MagicMock
) -> None:
    mock_collection.get.return_value = {"ids": [], "documents": [], "metadatas": []}

    assert await vector_store.get_case("missing") is None


@pytest.mark.asyncio
async def test_delete_case(vector_store: VectorStore, mock_collection: MagicMock) -> None:
    assert await vector_store.delete_case("case-1") is True
    mock_collection.delete.assert_called_once_with(ids=["case-1"])


@pytest.mark.asyncio
async def test_count(vector_store: VectorStore, mock_collection: MagicMock) -> None:
    assert await vector_store.count() == 2
