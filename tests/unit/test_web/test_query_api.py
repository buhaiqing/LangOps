"""Natural language query API tests."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from langops.agent.nl_query_engine import NLQueryEngine
from langops.models import NLQueryResult
from langops.web.dependencies import get_nl_query_engine
from langops.web.main import create_app


def test_nl_query_endpoint_returns_result() -> None:
    mock_engine = MagicMock(spec=NLQueryEngine)
    mock_engine.process = AsyncMock(
        return_value=NLQueryResult(
            answer="order-service CPU 较高",
            promql="sum(rate(container_cpu_usage_seconds_total[5m]))",
            explanation="查询 CPU",
            time_range="1h",
            data=[{"metric": {"pod": "order"}, "value": "0.9"}],
        )
    )

    app = create_app()
    app.dependency_overrides[get_nl_query_engine] = lambda: mock_engine
    client = TestClient(app)

    response = client.post("/api/v1/query", json={"query": "哪些服务 CPU 高"})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["promql"] is not None
    assert "CPU" in body["data"]["answer"]
    mock_engine.process.assert_awaited_once_with("哪些服务 CPU 高")


def test_nl_query_endpoint_validation_error() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/v1/query", json={"query": ""})
    assert response.status_code == 422
