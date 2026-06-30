"""Alert processor tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.agent.alert_processor import AlertProcessor
from langops.agent.rca_engine import RCAEngine
from langops.core.exceptions import AnalysisError
from langops.knowledge import SearchResult
from langops.models import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertSource,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)


def _alert() -> Alert:
    return Alert(
        id="alert-001",
        title="CPU使用率过高",
        description="CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="prod-cluster",
            namespace="production",
            pod_name="order-pod",
            service="order",
        ),
    )


@pytest.fixture
def processor() -> AlertProcessor:
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-abc123"

    rca_engine = MagicMock(spec=RCAEngine)
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="调高 limit", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(
        return_value=[
            SearchResult(
                id="case-1",
                score=0.85,
                document="doc",
                metadata={
                    "title": "历史 CPU",
                    "root_cause": "limit",
                    "solution": "patch",
                    "resolution_time": 20,
                },
            )
        ]
    )

    prometheus = MagicMock()
    prometheus.collect = AsyncMock(return_value={"cpu_usage": {"status": "success"}})

    return AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        prometheus_collector=prometheus,
    )


@pytest.mark.asyncio
async def test_process_collects_aliyun_metrics_for_aliyun_source() -> None:
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-aliyun"

    rca_engine = MagicMock()
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="ECS 规格过小", confidence=0.85)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="升配", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(return_value=[])

    aliyun = MagicMock()
    aliyun.collect = AsyncMock(return_value={"CPUUtilization": {"status": "success"}})

    processor = AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        aliyun_collector=aliyun,
    )

    alert = Alert(
        id="alert-ecs",
        title="ECS CPU过高",
        description="CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="aliyun",
            system="cn-hangzhou",
            instance_id="i-abc123",
            resource_type="ecs",
        ),
    )

    await processor.process(alert)
    aliyun.collect.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_sends_notification_when_configured() -> None:
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-notify"

    rca_engine = MagicMock()
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="CPU 过高", confidence=0.9)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="升配", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(return_value=[])

    notification = MagicMock()
    notification.notify_analysis = AsyncMock(return_value={"feishu": True})

    processor = AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        notification_service=notification,
    )

    await processor.process(_alert())
    notification.notify_analysis.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_includes_impact_prediction_when_engine_configured() -> None:
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-predict"

    rca_engine = MagicMock()
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="CPU 过高", confidence=0.9)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="扩容", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(return_value=[])

    predictive = MagicMock()
    predictive.predict_impact = AsyncMock(
        return_value=MagicMock(
            model_dump=lambda: {"overall_risk": "high", "recommendation": "提前扩容"}
        )
    )

    processor = AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        predictive_engine=predictive,
    )

    result = await processor.process(_alert())
    assert result.impact_prediction["overall_risk"] == "high"
    predictive.predict_impact.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_returns_analysis_result(processor: AlertProcessor) -> None:
    result = await processor.process(_alert())

    assert isinstance(result, AnalysisResult)
    assert result.alert_id == "alert-001"
    assert result.trace_id == "trace-abc123"
    assert result.root_cause.category == "资源不足"
    assert len(result.similar_cases) == 1
    assert result.suggestion.summary == "调高 limit"
    assert result.processing_time_seconds >= 0
    processor.prometheus_collector.collect.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_raises_analysis_error_when_rca_fails(processor: AlertProcessor) -> None:
    processor.rca_engine.analyze = AsyncMock(side_effect=RuntimeError("llm down"))

    with pytest.raises(AnalysisError, match="Failed to process alert"):
        await processor.process(_alert())


@pytest.mark.asyncio
async def test_retrieve_similar_cases_returns_empty_on_search_failure(
    processor: AlertProcessor,
) -> None:
    processor.vector_store.search = AsyncMock(side_effect=RuntimeError("chroma down"))

    cases = await processor._retrieve_similar_cases(_alert())

    assert cases == []


def _prometheus_alert() -> Alert:
    """Alert with source.type='prometheus' (as set by AlertmanagerAdapter)."""
    return Alert(
        id="alert-prom",
        title="CPU使用率过高",
        description="CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="prometheus",
            system="prom-prod",
            namespace="production",
            pod_name="order-pod",
            service="order",
        ),
    )


@pytest.mark.asyncio
async def test_process_collects_prometheus_metrics_for_prometheus_source() -> None:
    """source.type='prometheus' should trigger Prometheus metric collection."""
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-prom"

    rca_engine = MagicMock()
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="CPU 过高", confidence=0.9)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="扩容", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(return_value=[])

    prometheus = MagicMock()
    prometheus.collect = AsyncMock(return_value={"cpu_usage": {"status": "success"}})

    processor = AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        prometheus_collector=prometheus,
    )

    await processor.process(_prometheus_alert())
    prometheus.collect.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_collects_prometheus_but_not_aliyun_for_prometheus_source() -> None:
    """source.type='prometheus' should trigger Prometheus collector but NOT
    Aliyun CMS collector — both collectors are injected but only Prometheus
    one is expected to be called."""
    langfuse = MagicMock()
    langfuse.get_current_trace_id.return_value = "trace-prom-only"

    rca_engine = MagicMock()
    rca_engine.analyze = AsyncMock(
        return_value=RootCause(category="资源不足", description="CPU 过高", confidence=0.9)
    )
    rca_engine.generate_remediation = AsyncMock(
        return_value=RemediationSuggestion(summary="扩容", steps=["step1"])
    )

    vector_store = MagicMock()
    vector_store.search = AsyncMock(return_value=[])

    prometheus = MagicMock()
    prometheus.collect = AsyncMock(return_value={"cpu_usage": {"status": "success"}})

    aliyun = MagicMock()
    aliyun.collect = AsyncMock(return_value={"CPUUtilization": {"status": "success"}})

    processor = AlertProcessor(
        langfuse=langfuse,
        rca_engine=rca_engine,
        vector_store=vector_store,
        prometheus_collector=prometheus,
        aliyun_collector=aliyun,
    )

    await processor.process(_prometheus_alert())
    prometheus.collect.assert_awaited_once()
    aliyun.collect.assert_not_awaited()
