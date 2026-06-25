"""Predictive engine tests."""

import pytest

from langops.agent.predictive_engine import PredictiveEngine


@pytest.fixture
def engine() -> PredictiveEngine:
    return PredictiveEngine(api_key=None)


def _rising_cpu_metrics() -> dict:
    values = [{"timestamp": float(i), "value": str(0.5 + i * 0.05)} for i in range(10)]
    return {
        "cpu_usage": {
            "status": "success",
            "series": [{"metric": {"container": "app"}, "values": values}],
        }
    }


def test_analyze_metrics_detects_rising_cpu(engine: PredictiveEngine) -> None:
    result = engine.analyze_metrics(
        _rising_cpu_metrics(),
        horizon_hours=24,
        service="order-service",
        resource_label="order-pod",
    )

    assert result.overall_risk in ("medium", "high", "critical")
    assert len(result.forecasts) >= 1
    assert result.forecasts[0].trend == "rising"
    assert "order-pod" in result.recommendation or "order" in result.recommendation.lower()


def test_analyze_metrics_handles_empty_metrics(engine: PredictiveEngine) -> None:
    result = engine.analyze_metrics({}, horizon_hours=12)

    assert result.overall_risk == "low"
    assert result.forecasts == []
    assert result.confidence == 0.3


def test_forecast_series_stable_with_single_point(engine: PredictiveEngine) -> None:
    forecast = engine._forecast_series(
        "memory_usage", [0.6], horizon_hours=24, thresholds={"memory": 0.9}
    )
    assert forecast is not None
    assert forecast.trend == "stable"
    assert forecast.risk_level == "low"


def test_extract_series_from_prometheus_payload(engine: PredictiveEngine) -> None:
    series = engine._extract_series(_rising_cpu_metrics())
    assert "cpu_usage_0" in series
    assert len(series["cpu_usage_0"]) == 10
