"""Agent prompt template tests."""

import json

import pytest

from langops.agent.prompts import (
    SYSTEM_PROMPT_RCA,
    SYSTEM_PROMPT_REMEDIATION,
    build_nl_query_prompt,
    build_rca_prompt,
    build_remediation_prompt,
)


def test_system_prompts_are_defined() -> None:
    assert "JSON" in SYSTEM_PROMPT_RCA
    assert "JSON" in SYSTEM_PROMPT_REMEDIATION


def test_build_rca_prompt_includes_alert_fields() -> None:
    prompt = build_rca_prompt(
        alert_title="CPU使用率过高",
        alert_description="order-service CPU > 90%",
        severity="critical",
        category="resource",
        source={"type": "kubernetes", "namespace": "prod"},
        metrics={"cpu_usage": {"status": "success"}},
        logs=["line-1", "line-2"],
        events=[{"type": "warning", "message": "oom"}],
    )

    assert "CPU使用率过高" in prompt
    assert "critical" in prompt
    assert "order-service CPU > 90%" in prompt
    assert '"cpu_usage"' in prompt
    assert "line-1" in prompt
    assert "oom" in prompt
    assert "root_cause_category" in prompt


def test_build_rca_prompt_truncates_logs_and_events() -> None:
    logs = [f"log-{i}" for i in range(15)]
    events = [{"id": i} for i in range(8)]

    prompt = build_rca_prompt(
        alert_title="t",
        alert_description="d",
        severity="high",
        category="resource",
        source={"type": "k8s"},
        metrics={},
        logs=logs,
        events=events,
    )

    assert "log-9" in prompt
    assert "log-10" not in prompt
    # only first 10 logs
    assert '"id": 4' in prompt
    assert '"id": 5' not in prompt  # only first 5 events


def test_build_rca_prompt_handles_empty_logs_and_events() -> None:
    prompt = build_rca_prompt(
        alert_title="t",
        alert_description="d",
        severity="low",
        category="availability",
        source={},
        metrics={},
        logs=[],
        events=[],
    )

    assert "无相关日志" in prompt
    assert "无相关事件" in prompt
    assert "无指标数据" in prompt


def test_build_remediation_prompt_includes_root_cause_and_cases() -> None:
    prompt = build_remediation_prompt(
        root_cause={
            "category": "资源不足",
            "description": "CPU limit 过低",
            "confidence": 0.9,
            "evidence": ["CPU 95%"],
        },
        similar_cases=[
            {
                "title": "历史案例",
                "root_cause": "limit 过低",
                "solution": "调高 limit",
                "resolution_time": 20,
            }
        ],
        alert_context={"service": "order", "namespace": "prod", "resource_type": "pod"},
    )

    assert "资源不足" in prompt
    assert "历史案例" in prompt
    assert "order" in prompt
    assert '"summary"' in prompt


def test_build_remediation_prompt_without_similar_cases() -> None:
    prompt = build_remediation_prompt(
        root_cause={"category": "未知", "description": "desc", "confidence": 0.5, "evidence": []},
        similar_cases=[],
        alert_context={},
    )

    assert "无历史相似案例" in prompt


def test_build_nl_query_prompt_limits_metrics() -> None:
    metrics = [f"metric_{i}" for i in range(30)]
    prompt = build_nl_query_prompt("昨天 CPU 怎么样", metrics)

    assert "昨天 CPU 怎么样" in prompt
    assert "metric_19" in prompt
    assert "metric_20" not in prompt
    assert '"promql"' in prompt


def test_build_nl_result_prompt_includes_query_and_data() -> None:
    from langops.agent.prompts import build_nl_result_prompt

    prompt = build_nl_result_prompt(
        "CPU 高的服务",
        "sum(rate(container_cpu_usage_seconds_total[5m]))",
        [{"metric": {"pod": "order"}, "value": "0.9"}],
    )

    assert "CPU 高的服务" in prompt
    assert "container_cpu_usage_seconds_total" in prompt
    assert '"answer"' in prompt
