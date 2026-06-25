"""LLM prompt templates for LangOps."""

import json
from typing import Any

# System prompts
SYSTEM_PROMPT_RCA = """你是一个专业的运维专家，擅长分析系统告警并找出根因。

你的任务是：
1. 分析告警信息和相关数据
2. 找出问题的根本原因
3. 提供证据支持你的结论
4. 评估问题的影响范围

输出必须严格遵循 JSON 格式。"""

SYSTEM_PROMPT_REMEDIATION = """你是一个专业的运维专家，擅长提供可操作的修复建议。

你的任务是：
1. 基于根因分析结果，提供具体的修复步骤
2. 提供可执行的命令（如 kubectl、docker 等）
3. 评估修复操作的风险
4. 提供回滚方案

输出必须严格遵循 JSON 格式。"""


def build_rca_prompt(
    alert_title: str,
    alert_description: str,
    severity: str,
    category: str,
    source: dict[str, Any],
    metrics: dict[str, Any],
    logs: list[str],
    events: list[dict[str, Any]],
) -> str:
    """Build prompt for root cause analysis."""
    max_logs = 10
    logs_str = "\n".join(logs[:max_logs]) if logs else "无相关日志"

    max_events = 5
    events_str = (
        json.dumps(events[:max_events], ensure_ascii=False, indent=2) if events else "无相关事件"
    )

    metrics_str = json.dumps(metrics, ensure_ascii=False, indent=2) if metrics else "无指标数据"

    return f"""请分析以下告警的根因：

## 告警信息

- 标题: {alert_title}
- 描述: {alert_description}
- 严重程度: {severity}
- 类别: {category}
- 来源: {json.dumps(source, ensure_ascii=False)}

## 指标数据

```json
{metrics_str}
```

## 相关日志 (最近{max_logs}条)

```
{logs_str}
```

## 相关事件 (最近{max_events}条)

```json
{events_str}
```

## 分析要求

1. 根因分类必须是以下之一：资源不足、配置错误、依赖故障、代码缺陷、外部因素、未知
2. 置信度范围 0-1，基于证据的充分程度
3. 关键证据必须引用具体的数据点
4. 影响分析需说明对业务和系统的影响

## 输出格式

请输出严格的 JSON 格式，不要包含其他内容：

{{
  "root_cause_category": "根因分类",
  "description": "详细的根因描述，2-3句话",
  "confidence": 0.85,
  "key_evidence": ["证据1：具体数据", "证据2：具体数据"],
  "related_metrics": ["关联指标1", "关联指标2"],
  "impact_analysis": "影响范围分析"
}}
"""


def build_remediation_prompt(
    root_cause: dict[str, Any],
    similar_cases: list[dict[str, Any]],
    alert_context: dict[str, Any],
) -> str:
    """Build prompt for remediation suggestion."""
    if similar_cases:
        similar_cases_str = "## 历史相似案例\n\n"
        for i, case in enumerate(similar_cases[:3], 1):
            similar_cases_str += f"""案例{i}:
- 标题: {case.get('title', 'N/A')}
- 根因: {case.get('root_cause', 'N/A')}
- 解决方案: {case.get('solution', 'N/A')}
- 解决时间: {case.get('resolution_time', '未知')} 分钟

"""
    else:
        similar_cases_str = "## 历史相似案例\n\n无历史相似案例。\n\n"

    return f"""基于以下根因分析结果，提供修复建议：

## 根因分析

- 分类: {root_cause.get('category', 'N/A')}
- 描述: {root_cause.get('description', 'N/A')}
- 置信度: {root_cause.get('confidence', 0)}
- 关键证据: {json.dumps(root_cause.get('evidence', []), ensure_ascii=False)}

{similar_cases_str}
## 告警上下文

- 服务: {alert_context.get('service', 'N/A')}
- 命名空间: {alert_context.get('namespace', 'N/A')}
- 资源类型: {alert_context.get('resource_type', 'N/A')}

## 输出要求

请输出严格的 JSON 格式：

{{
  "summary": "修复建议摘要，1句话",
  "steps": [
    "步骤1：具体操作",
    "步骤2：具体操作"
  ],
  "commands": [
    "可执行的命令1",
    "可执行的命令2"
  ],
  "risks": [
    "风险1及应对措施",
    "风险2及应对措施"
  ],
  "rollback_plan": "如果修复失败，如何回滚（如有）",
  "estimated_time": "预计修复时间，如：10分钟"
}}

注意：
1. commands 中的命令必须是可执行的，优先使用 kubectl 命令
2. 如果无法提供具体命令，commands 可以为空数组
3. risks 必须包含每个风险的应对措施
4. 如果修复不可逆，rollback_plan 填写 "无"
"""


def build_nl_query_prompt(user_query: str, available_metrics: list[str]) -> str:
    """Build prompt for natural language to PromQL conversion."""
    metrics_str = "\n".join([f"- {metric}" for metric in available_metrics[:20]])

    return f"""将以下自然语言查询转换为 PromQL：

用户查询: {user_query}

可用的指标（部分）：
{metrics_str}

输出 JSON 格式：
{{
  "promql": "生成的 PromQL 查询",
  "time_range": "时间范围，如：1h, 24h, 7d",
  "explanation": "查询解释",
  "requires_aggregation": true/false
}}

注意：
1. 如果无法转换为有效的 PromQL，promql 字段返回 null
2. time_range 默认为 1h
3. 对于复杂的分析需求，requires_aggregation 设为 true
"""
