"""Natural language to PromQL query engine."""

import json
from typing import Any

import openai

from langops.agent.prompts import build_nl_query_prompt, build_nl_result_prompt
from langops.collectors import PrometheusCollector
from langops.core import get_logger
from langops.core.exceptions import LLMError
from langops.models import NLQueryResult

logger = get_logger(__name__)

DEFAULT_METRICS = [
    "container_cpu_usage_seconds_total",
    "container_memory_usage_bytes",
    "container_spec_memory_limit_bytes",
    "kube_pod_container_status_restarts_total",
    "container_network_receive_errors_total",
    "container_network_transmit_errors_total",
    "kube_pod_status_phase",
    "kube_deployment_status_replicas_available",
]


class NLQueryEngine:
    """Convert natural language to PromQL and interpret results."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4",
        temperature: float = 0.2,
        prometheus_collector: PrometheusCollector | None = None,
        available_metrics: list[str] | None = None,
    ) -> None:
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.prometheus_collector = prometheus_collector
        self.available_metrics = available_metrics or DEFAULT_METRICS

    async def process(self, user_query: str) -> NLQueryResult:
        """Run NL2PromQL conversion, execute query, and interpret results."""
        conversion = await self._convert_to_promql(user_query)
        promql = conversion.get("promql")
        explanation = conversion.get("explanation")
        time_range = str(conversion.get("time_range") or "1h")

        if not promql:
            return NLQueryResult(
                answer=explanation or "无法将问题转换为 PromQL，请尝试更具体的指标描述。",
                promql=None,
                explanation=explanation,
                time_range=time_range,
                data=[],
            )

        data: list[dict[str, Any]] = []
        if self.prometheus_collector:
            try:
                data = await self.prometheus_collector.query_instant(promql)
            except Exception as exc:
                logger.warning("Prometheus query failed", promql=promql, error=str(exc))
                return NLQueryResult(
                    answer=f"PromQL 已生成但查询失败: {exc}",
                    promql=promql,
                    explanation=explanation,
                    time_range=time_range,
                    data=[],
                )

        answer = await self._interpret_results(user_query, promql, data)
        return NLQueryResult(
            answer=answer,
            promql=promql,
            explanation=explanation,
            time_range=time_range,
            data=data,
        )

    async def _convert_to_promql(self, user_query: str) -> dict[str, Any]:
        """Convert natural language to PromQL via LLM."""
        prompt = build_nl_query_prompt(user_query, self.available_metrics)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是 PromQL 专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if content is None:
                raise LLMError("Empty response from LLM")
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Invalid JSON response from LLM: {exc}") from exc
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"NL2PromQL conversion failed: {exc}") from exc

    async def _interpret_results(
        self,
        user_query: str,
        promql: str,
        query_data: list[dict[str, Any]],
    ) -> str:
        """Interpret PromQL results into a human-readable answer."""
        if not query_data:
            return "查询已执行，但未返回数据。请检查 PromQL、时间范围或指标是否存在。"

        prompt = build_nl_result_prompt(user_query, promql, query_data)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是运维数据分析专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if content is None:
                return "查询完成，但无法生成解读。"
            result = json.loads(content)
            return str(result.get("answer", "查询完成。"))
        except Exception as exc:
            logger.warning("Failed to interpret query results", error=str(exc))
            return f"查询完成，共 {len(query_data)} 条结果。PromQL: {promql}"
