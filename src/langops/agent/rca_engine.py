"""Root Cause Analysis Engine."""

import json
from typing import Any

import openai

from langops.agent.prompts import build_rca_prompt, build_remediation_prompt
from langops.core import get_logger
from langops.core.exceptions import LLMError
from langops.models import RemediationSuggestion, RootCause, SimilarCase

logger = get_logger(__name__)


class RCAEngine:
    """Root Cause Analysis Engine using LLM."""

    def __init__(self, api_key: str, model: str = "gpt-4", temperature: float = 0.2, base_url: str | None = None) -> None:
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
        self.model = model
        self.temperature = temperature

    async def analyze(
        self,
        alert_title: str,
        alert_description: str,
        severity: str,
        category: str,
        source: dict[str, Any],
        metrics: dict[str, Any],
        logs: list[str],
        events: list[dict[str, Any]],
    ) -> RootCause:
        """Perform root cause analysis."""
        prompt = build_rca_prompt(
            alert_title=alert_title,
            alert_description=alert_description,
            severity=severity,
            category=category,
            source=source,
            metrics=metrics,
            logs=logs,
            events=events,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if content is None:
                raise LLMError("Empty response from LLM")
            result = json.loads(content)

            return RootCause(
                category=result.get("root_cause_category", "未知"),
                description=result.get("description", "无法分析根因"),
                confidence=float(result.get("confidence", 0.0)),
                evidence=result.get("key_evidence", []),
                related_metrics=result.get("related_metrics", []),
                impact_analysis=result.get("impact_analysis"),
            )

        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM response as JSON", error=str(exc))
            raise LLMError(f"Invalid JSON response from LLM: {exc}") from exc
        except LLMError:
            raise
        except Exception as exc:
            logger.error("LLM analysis failed", error=str(exc))
            raise LLMError(f"LLM analysis failed: {exc}") from exc

    async def generate_remediation(
        self,
        root_cause: RootCause,
        similar_cases: list[SimilarCase],
        alert_context: dict[str, Any],
    ) -> RemediationSuggestion:
        """Generate remediation suggestion."""
        similar_cases_dict = [
            {
                "title": case.title,
                "root_cause": case.root_cause,
                "solution": case.solution,
                "resolution_time": case.resolution_time,
            }
            for case in similar_cases
        ]

        root_cause_dict = {
            "category": root_cause.category,
            "description": root_cause.description,
            "confidence": root_cause.confidence,
            "evidence": root_cause.evidence,
        }

        prompt = build_remediation_prompt(
            root_cause=root_cause_dict,
            similar_cases=similar_cases_dict,
            alert_context=alert_context,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if content is None:
                raise LLMError("Empty response from LLM")
            result = json.loads(content)

            return RemediationSuggestion(
                summary=result.get("summary", "暂无修复建议"),
                steps=result.get("steps", []),
                commands=result.get("commands", []),
                risks=result.get("risks", []),
                rollback_plan=result.get("rollback_plan"),
                estimated_time=result.get("estimated_time", "unknown"),
            )

        except Exception as exc:
            logger.error("Failed to generate remediation", error=str(exc))
            return RemediationSuggestion(
                summary="无法生成具体修复建议，请参考根因分析",
                steps=["查看详细根因分析", "根据分类查找相关文档"],
                commands=[],
                risks=["自动修复失败，需要人工介入"],
                rollback_plan=None,
                estimated_time="unknown",
            )
