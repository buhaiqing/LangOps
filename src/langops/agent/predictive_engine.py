"""Predictive operations engine — trend analysis and capacity forecasting."""

import json
from typing import Any

import numpy as np
import openai

from langops.agent.prompts import build_impact_prediction_prompt
from langops.core import get_logger
from langops.models import Alert, AlertContext, ImpactPrediction, MetricForecast, RootCause

logger = get_logger(__name__)

RISK_ORDER = ("low", "medium", "high", "critical")


class PredictiveEngine:
    """Analyze metric trends and forecast resource exhaustion risk."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4",
        step_hours: float = 0.25,
    ) -> None:
        self.model = model
        self.step_hours = step_hours
        self.client = openai.AsyncOpenAI(api_key=api_key) if api_key else None

    async def predict_impact(
        self,
        alert: Alert,
        context: AlertContext,
        root_cause: RootCause,
        horizon_hours: int = 24,
    ) -> ImpactPrediction:
        """Predict impact during alert processing."""
        prediction = self.analyze_metrics(
            context.metrics,
            horizon_hours=horizon_hours,
            service=alert.source.service,
            resource_label=alert.source.pod_name or alert.source.instance_id,
        )
        prediction.metadata["alert_id"] = alert.id
        prediction.metadata["root_cause_category"] = root_cause.category

        if self.client and prediction.forecasts:
            prediction.recommendation = await self._llm_recommendation(
                alert.title,
                root_cause.description,
                prediction,
            )
        return prediction

    async def predict_from_metrics(
        self,
        metrics: dict[str, Any],
        *,
        horizon_hours: int = 24,
        service: str | None = None,
        resource_label: str | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> ImpactPrediction:
        """Run proactive prediction on collected metrics."""
        prediction = self.analyze_metrics(
            metrics,
            horizon_hours=horizon_hours,
            service=service,
            resource_label=resource_label,
            thresholds=thresholds,
        )
        if self.client and prediction.forecasts:
            prediction.recommendation = await self._llm_recommendation(
                "容量预测",
                prediction.recommendation,
                prediction,
            )
        return prediction

    def analyze_metrics(
        self,
        metrics: dict[str, Any],
        *,
        horizon_hours: int = 24,
        service: str | None = None,
        resource_label: str | None = None,
        thresholds: dict[str, float] | None = None,
    ) -> ImpactPrediction:
        """Analyze metric time series and produce forecasts."""
        thresholds = thresholds or {"cpu": 0.9, "memory": 0.9}
        series_map = self._extract_series(metrics)
        forecasts: list[MetricForecast] = []

        for name, values in series_map.items():
            forecast = self._forecast_series(
                name,
                values,
                horizon_hours=horizon_hours,
                thresholds=thresholds,
            )
            if forecast:
                forecasts.append(forecast)

        overall = self._aggregate_risk(forecasts)
        recommendation = self._rule_recommendation(overall, forecasts, resource_label, horizon_hours)

        longest = self._longest_series(series_map)
        confidence = 0.85 if len(longest) >= 5 else 0.55
        if not forecasts:
            confidence = 0.3

        return ImpactPrediction(
            affected_service=service,
            horizon_hours=horizon_hours,
            overall_risk=overall,
            forecasts=forecasts,
            recommendation=recommendation,
            confidence=confidence,
            metadata={"resource": resource_label, "series_count": len(series_map)},
        )

    def _extract_series(self, metrics: dict[str, Any]) -> dict[str, list[float]]:
        """Pull numeric series from collector metric payloads."""
        series_map: dict[str, list[float]] = {}

        for key, data in metrics.items():
            if not isinstance(data, dict):
                continue
            if "series" in data:
                for idx, series in enumerate(data.get("series", [])):
                    values: list[float] = []
                    for point in series.get("values", []):
                        try:
                            values.append(float(point["value"]))
                        except (KeyError, TypeError, ValueError):
                            continue
                    if values:
                        series_map[f"{key}_{idx}"] = values
            elif "current_value" in data:
                try:
                    series_map[key] = [float(data["current_value"])]
                except (TypeError, ValueError):
                    continue

        return series_map

    def _forecast_series(
        self,
        metric_name: str,
        values: list[float],
        *,
        horizon_hours: int,
        thresholds: dict[str, float],
    ) -> MetricForecast | None:
        if not values:
            return None

        current = values[-1]
        threshold = self._threshold_for_metric(metric_name, thresholds)

        if len(values) < 2:
            risk = self._risk_from_value(current, threshold)
            return MetricForecast(
                metric=metric_name,
                current=current,
                trend="stable",
                slope_per_hour=0.0,
                forecast_value=current,
                risk_level=risk,
                summary=f"{metric_name} 当前值 {current:.3f}，数据点不足无法判断趋势",
            )

        slope, forecast = self._linear_forecast(values, horizon_hours)
        trend = "stable"
        if slope > 0.01:
            trend = "rising"
        elif slope < -0.01:
            trend = "falling"

        risk = self._risk_from_value(max(current, forecast), threshold)
        if trend == "rising" and forecast >= threshold * 0.85:
            risk = self._max_risk(risk, "high")

        return MetricForecast(
            metric=metric_name,
            current=round(current, 4),
            trend=trend,
            slope_per_hour=round(slope, 4),
            forecast_value=round(forecast, 4),
            risk_level=risk,
            summary=(
                f"{metric_name} 当前 {current:.3f}，趋势 {trend}，"
                f"预计 {horizon_hours}h 后约 {forecast:.3f}"
            ),
        )

    def _linear_forecast(self, values: list[float], horizon_hours: int) -> tuple[float, float]:
        """ponytail: OLS linear trend; upgrade path = Prophet/ARIMA per metric."""
        y = np.array(values, dtype=float)
        x = np.arange(len(y), dtype=float) * self.step_hours
        slope, intercept = np.polyfit(x, y, 1)
        future_x = x[-1] + horizon_hours
        forecast = float(slope * future_x + intercept)
        return float(slope), forecast

    def _threshold_for_metric(self, metric_name: str, thresholds: dict[str, float]) -> float:
        name = metric_name.lower()
        for key, value in thresholds.items():
            if key.lower() in name:
                return value
        return 0.9

    def _risk_from_value(self, value: float, threshold: float) -> str:
        if value >= threshold:
            return "critical"
        if value >= threshold * 0.9:
            return "high"
        if value >= threshold * 0.7:
            return "medium"
        return "low"

    def _max_risk(self, a: str, b: str) -> str:
        return a if RISK_ORDER.index(a) >= RISK_ORDER.index(b) else b

    def _aggregate_risk(self, forecasts: list[MetricForecast]) -> str:
        if not forecasts:
            return "low"
        worst = "low"
        for item in forecasts:
            worst = self._max_risk(worst, item.risk_level)
        return worst

    def _rule_recommendation(
        self,
        overall_risk: str,
        forecasts: list[MetricForecast],
        resource_label: str | None,
        horizon_hours: int,
    ) -> str:
        target = resource_label or "目标资源"
        if not forecasts:
            return f"未获取到足够时序数据，建议检查 {target} 的监控采集配置。"

        rising = [f for f in forecasts if f.trend == "rising" and f.risk_level in ("high", "critical")]
        if overall_risk == "critical":
            return f"{target} 存在资源耗尽风险，建议立即扩容或限流，并检查近期变更。"
        if rising:
            names = ", ".join(f.metric for f in rising[:3])
            return (
                f"{target} 的 {names} 呈上升趋势，"
                f"建议在未来 {horizon_hours} 小时内提前扩容或优化负载。"
            )
        if overall_risk == "high":
            return f"{target} 资源使用率偏高，建议安排容量复盘并设置更早的告警阈值。"
        return f"{target} 资源趋势平稳，维持现有容量策略并持续观察。"

    def _longest_series(self, series_map: dict[str, list[float]]) -> list[float]:
        if not series_map:
            return []
        return max(series_map.values(), key=len)

    async def _llm_recommendation(
        self,
        title: str,
        context: str,
        prediction: ImpactPrediction,
    ) -> str:
        if not self.client:
            return prediction.recommendation

        prompt = build_impact_prediction_prompt(
            title=title,
            context=context,
            prediction=prediction.model_dump(),
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是容量规划专家。输出严格 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                return prediction.recommendation
            result = json.loads(content)
            return str(result.get("recommendation", prediction.recommendation))
        except Exception as exc:
            logger.warning("LLM impact recommendation failed", error=str(exc))
            return prediction.recommendation
