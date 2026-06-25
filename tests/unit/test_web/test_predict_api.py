"""Predict API tests."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from langops.agent.predictive_engine import PredictiveEngine
from langops.models import ImpactPrediction, MetricForecast
from langops.web.dependencies import get_predictive_engine, get_prometheus_collector
from langops.web.main import create_app


def test_predict_endpoint_returns_forecast() -> None:
    mock_engine = MagicMock(spec=PredictiveEngine)
    mock_engine.predict_from_metrics = AsyncMock(
        return_value=ImpactPrediction(
            affected_service="order",
            horizon_hours=24,
            overall_risk="high",
            forecasts=[
                MetricForecast(
                    metric="cpu_usage_0",
                    current=0.9,
                    trend="rising",
                    slope_per_hour=0.1,
                    forecast_value=0.95,
                    risk_level="high",
                    summary="CPU rising",
                )
            ],
            recommendation="建议扩容",
            confidence=0.8,
        )
    )

    mock_prom = MagicMock()
    mock_prom.collect = AsyncMock(return_value={"cpu_usage": {"status": "success", "series": []}})

    app = create_app()
    app.dependency_overrides[get_predictive_engine] = lambda: mock_engine
    app.dependency_overrides[get_prometheus_collector] = lambda: mock_prom
    client = TestClient(app)

    response = client.post(
        "/api/v1/predict",
        json={
            "resource_type": "kubernetes",
            "namespace": "production",
            "pod_name": "order-pod",
            "horizon_hours": 24,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["overall_risk"] == "high"
    mock_prom.collect.assert_awaited_once()
