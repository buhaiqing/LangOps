# LangOps - AI 智能化运维平台架构设计

> 基于 Langfuse 的云原生智能运维解决方案

---

## 1. 项目概述

### 1.1 项目定位

LangOps 是一个基于 Langfuse 构建的 AI 智能化运维平台，专注于：

- **云资源巡检**：阿里云 ECS、RDS、SLB 等资源监控与分析
- **Kubernetes Pod 巡检**：K8s 集群健康度、Pod 状态、性能分析
- **智能根因分析**：利用 LLM 自动分析告警根因
- **知识沉淀**：故障案例自动归档，支持 RAG 检索

### 1.2 核心价值

| 能力 | 价值 |
|-----|------|
| 智能根因分析 | 减少 MTTR（平均修复时间）50%+ |
| 告警降噪 | 过滤无效告警，降低告警疲劳 |
| 知识复用 | 历史经验自动沉淀，新人快速上手 |
| 全链路观测 | Langfuse 追踪每个 AI 决策过程 |

### 1.3 实现状态（截至 2026-06-25）

| 阶段 | 功能 | 状态 | 代码位置 |
|-----|------|------|---------|
| Phase 1 | 脚手架、配置、Prometheus 采集、RCA、ChromaDB、告警 API、Langfuse | ✅ 已交付 | `src/langops/` |
| Phase 2 | 阿里云 CMS、NL2PromQL、飞书/钉钉通知、Web UI | ✅ 已交付 | `collectors/`、`nl_query_engine.py`、`notification.py`、`web/static/` |
| Phase 3 | 预测性运维、告警降噪、修复审批执行 | ✅ 已交付 | `predictive_engine.py`、`alert_dedup.py`、`remediation_executor.py` |
| 规划中 | JIRA 集成、Loki/K8s 采集器、多租户、Redis 持久化 | ⏳ 未实现 | — |

**测试基线**：`pytest tests/ -q` → 126 passed。规范与 worktree 流程见 [AGENTS.md](../../AGENTS.md)。

---

## 2. 整体架构

### 2.1 架构分层

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LangOps - 分层架构                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         交互层 (Presentation)                        │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │   Web UI     │  │  告警通知    │  │  API 接口    │               │   │
│  │  │ (静态 /ui)   │  │ (飞书/钉钉)  │  │  (FastAPI)   │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         智能层 (Intelligence)                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                    AI Agent Core                             │   │   │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │   │   │
│  │  │  │ 根因分析 │  │ 知识检索 │  │ 修复建议 │  │ 预测预警 │    │   │   │
│  │  │  │  (RCA)   │  │  (RAG)   │  │ (Suggest)│  │(Forecast)│    │   │   │
│  │  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  │                              │                                      │   │
│  │                              ▼                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                   LLM Service                                │   │   │
│  │  │  (OpenAI / Claude / Qwen / 私有化部署)                        │   │   │
│  │  └─────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         数据层 (Data)                                │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  Langfuse    │  │  Vector DB   │  │   Cache      │               │   │
│  │  │  (观测中枢)   │  │(ChromaDB/   │  │  (Redis)     │               │   │
│  │  │              │  │  Milvus)     │  │              │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        接入层 (Integration)                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  Prometheus  │  │ 阿里云 CMS   │  │  Kubernetes  │               │   │
│  │  │  Collector   │  │  Collector   │  │  Collector   │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │    Loki      │  │  Alertmanager│  │   Custom     │               │   │
│  │  │  Collector   │  │   Webhook    │  │  Collectors  │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 各层职责

| 层级 | 核心职责 | 关键技术 |
|-----|---------|---------|
| **接入层** | 对接各类数据源，标准化数据格式 | Prometheus SDK、阿里云 SDK、k8s-client |
| **数据层** | 存储观测数据、向量知识、缓存 | Langfuse、ChromaDB、Redis |
| **智能层** | AI 分析核心，实现 RCA/RAG/建议 | LangChain、OpenAI API、自定义 Agent |
| **交互层** | 用户界面、告警通道、API 服务 | 静态 Web UI（`/ui`）、FastAPI、Webhook |

---

## 3. 核心工作流

### 3.1 告警处理工作流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        告警智能分析工作流                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   触发源                                                                      │
│     │                                                                         │
│     ▼                                                                         │
│   ┌─────────────────┐                                                        │
│   │ 1. 告警接收      │                                                        │
│   │    (Webhook)    │                                                        │
│   │                 │                                                        │
│   │ • Prometheus    │                                                        │
│   │ • Alertmanager  │                                                        │
│   │ • 阿里云告警    │                                                        │
│   │ • 定时巡检任务  │                                                        │
│   └────────┬────────┘                                                        │
│            │                                                                 │
│            ▼                                                                 │
│   ╔═══════════════════════════════════════════════════════════════════════╗ │
│   ║  Langfuse Trace Start                                                ║ │
│   ║  trace = langfuse.trace(                                             ║ │
│   ║    name="alert_analysis",                                            ║ │
│   ║    user_id="ops_team",                                               ║ │
│   ║    metadata={                                                        ║ │
│   ║      "alert_id": "alert_xxx",                                        ║ │
│   ║      "severity": "critical",                                         ║ │
│   ║      "service": "order-service"                                      ║ │
│   ║    }                                                                 ║ │
│   ║  )                                                                   ║ │
│   ╚═══════════════════════════════════════════════════════════════════════╝ │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │ 2. 数据聚合 (Data Collection)                                     │      │
│   │                                                                  │      │
│   │  span = trace.span(name="collect_context")                       │      │
│   │                                                                  │      │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │      │
│   │  │ Prometheus  │  │ 阿里云 CMS  │  │ K8s Events  │              │      │
│   │  │  指标查询   │  │  补充数据   │  │  事件关联   │              │      │
│   │  │  (30min)   │  │  (ECS/RDS)  │  │ (Pod/Node)  │              │      │
│   │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │      │
│   │         └─────────────────┼─────────────────┘                    │      │
│   │                           ▼                                      │      │
│   │              ┌─────────────────────┐                             │      │
│   │              │   统一上下文对象    │                             │      │
│   │              │   AlertContext      │                             │      │
│   │              └─────────────────────┘                             │      │
│   │                                                                  │      │
│   │  span.end()                                                      │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │ 3. 根因分析 (Root Cause Analysis)                                 │      │
│   │                                                                  │      │
│   │  generation = trace.generation(                                  │      │
│   │    name="rca_analysis",                                          │      │
│   │    model="gpt-4",                                                │      │
│   │    prompt=build_rca_prompt(context),                             │      │
│   │    temperature=0.2                                               │      │
│   │  )                                                               │      │
│   │                                                                  │      │
│   │  LLM 输出结构:                                                    │      │
│   │  {                                                               │      │
│   │    "root_cause_category": "资源不足",                             │      │
│   │    "confidence": 0.85,                                           │      │
│   │    "key_evidence": [                                             │      │
│   │      "CPU使用率持续高于90%",                                       │      │
│   │      "Pod重启3次，OOMKilled"                                       │      │
│   │    ],                                                            │      │
│   │    "related_metrics": [...],                                     │      │
│   │    "impact_analysis": "影响订单服务可用性"                         │      │
│   │  }                                                               │      │
│   │                                                                  │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │ 4. 知识检索 (RAG Retrieval)                                       │      │
│   │                                                                  │      │
│   │  span = trace.span(name="knowledge_retrieval")                   │      │
│   │                                                                  │      │
│   │  ┌─────────────┐      ┌─────────────────┐      ┌─────────────┐  │      │
│   │  │ 向量化查询  │─────▶│ 相似度搜索      │─────▶│ 历史案例    │  │      │
│   │  │ (Embedding) │      │ (Vector DB)     │      │ (Top-3)     │  │      │
│   │  └─────────────┘      └─────────────────┘      └─────────────┘  │      │
│   │                                                                  │      │
│   │  检索结果注入 LLM 上下文                                          │      │
│   │                                                                  │      │
│   │  span.end()                                                      │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │ 5. 修复建议 (Remediation)                                         │      │
│   │                                                                  │      │
│   │  generation = trace.generation(                                  │      │
│   │    name="remediation_suggestion",                                │      │
│   │    model="gpt-4",                                                │      │
│   │    prompt=build_suggestion_prompt(                               │      │
│   │      root_cause, similar_cases                                   │      │
│   │    )                                                             │      │
│   │  )                                                               │      │
│   │                                                                  │      │
│   │  输出: 具体修复步骤 + 命令 + 风险评估                              │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐      │
│   │ 6. 结果输出                                                       │      │
│   │                                                                  │      │
│   │  • 告警降噪：重复告警在窗口内 suppress，跳过 LLM（可选）           │      │
│   │  • 影响预测：写入 impact_prediction（PredictiveEngine）           │      │
│   │  • 修复计划：有 commands 时注册 RemediationPlan（待审批）         │      │
│   │                                                                  │      │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │      │
│   │  │   Web UI     │  │  通知渠道    │  │ 修复审批 API │            │      │
│   │  │  展示报告    │  │ 飞书/钉钉    │  │ dry-run/拒绝 │            │      │
│   │  └──────────────┘  └──────────────┘  └──────────────┘            │      │
│   └──────────────────────────────────────────────────────────────────┘      │
│            │                                                                 │
│            ▼                                                                 │
│   ╔═══════════════════════════════════════════════════════════════════════╗ │
│   ║  Langfuse Trace End                                                  ║ │
│   ║                                                                      ║ │
│   ║  # 收集用户反馈，用于模型优化                                          ║ │
│   ║  trace.score(                                                        ║ │
│   ║    name="rca_accuracy",                                              ║ │
│   ║    value=user_rating,  # 1-5                                         ║ │
│   ║    comment="根因分析准确，建议有效"                                   ║ │
│   ║  )                                                                   ║ │
│   ╚═══════════════════════════════════════════════════════════════════════╝ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 自然语言查询工作流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        自然语言查询工作流                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户输入: "过去24小时，哪些服务的CPU使用率超过80%？"                          │
│                                                                              │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 1. NL2PromQL 转换                                                   │    │
│  │                                                                     │    │
│  │  generation = trace.generation(                                     │    │
│  │    name="nl2promql",                                                │    │
│  │    prompt=f"""                                                      │    │
│  │ 将自然语言转换为 PromQL 查询:                                        │    │
│  │ 用户问题: {user_query}                                              │    │
│  │                                                                     │    │
│  │ 可用的指标:                                                          │    │
│  │ - container_cpu_usage_seconds_total                                 │    │
│  │ - container_memory_usage_bytes                                      │    │
│  │ - kube_pod_container_status_restarts_total                          │    │
│  │ """                                                                │    │
│  │  )                                                                  │    │
│  │                                                                     │    │
│  │  输出:                                                              │    │
│  │  {                                                                  │    │
│  │    "promql": "sum(rate(container_cpu_usage_seconds_total[5m])) > 0.8",│   │
│  │    "time_range": "24h",                                             │    │
│  │    "explanation": "查询过去24小时CPU使用率超过80%的容器"              │    │
│  │  }                                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 2. 执行查询                                                         │    │
│  │                                                                     │    │
│  │  result = prometheus_client.query(                                  │    │
│  │    promql=generated_promql,                                         │    │
│  │    time_range="24h"                                                 │    │
│  │  )                                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 3. 结果解读                                                         │    │
│  │                                                                     │    │
│  │  generation = trace.generation(                                     │    │
│  │    name="result_interpretation",                                    │    │
│  │    prompt=f"""                                                      │    │
│  │ 将 PromQL 查询结果转换为人类可读的报告:                               │    │
│  │ 原始数据: {query_result}                                            │    │
│  │ 用户问题: {user_query}                                              │    │
│  │ """                                                                │    │
│  │  )                                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 4. 返回用户                                                         │    │
│  │                                                                     │    │
│  │  "过去24小时，以下服务的CPU使用率超过80%:                             │    │
│  │   - order-service (峰值 92%, 持续 15min)                            │    │
│  │   - payment-service (峰值 87%, 持续 8min)                           │    │
│  │   建议关注这两服务的扩容配置。"                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 告警降噪工作流

```
告警 POST /api/v1/alerts
        │
        ▼
┌───────────────────┐     窗口内重复      ┌───────────────────┐
│ AlertDedupService │ ── fingerprint ──▶ │ action=suppress   │
│ (默认 900s 窗口)   │                     │ 跳过 LLM，返回 dedup │
└───────────────────┘                     └───────────────────┘
        │ 新告警 / 窗口外
        ▼
   正常 AlertProcessor 流水线
```

- 指纹：基于 `source`（类型、集群、命名空间、Pod 等）与 `category` 生成
- 配置：`ALERT_DEDUP_ENABLED`、`ALERT_DEDUP_WINDOW_SECONDS`
- 统计：`GET /api/v1/alerts/dedup/stats`

### 3.4 修复审批工作流

```
分析完成且 suggestion.commands 非空
        │
        ▼
RemediationRegistry.create_from_analysis()  →  status=pending_approval
        │
        ▼
AnalysisResponse.remediation_plan_id
        │
        ├── Web UI「修复审批」页签
        └── API:
              GET  /api/v1/remediation
              POST /api/v1/remediation/{id}/execute  (dry_run 默认推荐)
              POST /api/v1/remediation/{id}/reject
```

**安全策略**（`RemediationExecutor`）：

| 项 | 默认行为 |
|----|---------|
| `REMEDIATION_ENABLED` | `true`：注册计划 |
| `REMEDIATION_EXECUTION_ENABLED` | `false`：禁止真实命令执行 |
| kubectl 白名单 | `scale` / `patch` / `rollout restart` / `set resources` |
| 拦截 | `delete`、`exec`、`curl`、`rm` 等 |

> ponytail：计划与降噪状态均为进程内内存存储；生产环境升级路径为 Redis/DB。

### 3.5 预测性运维工作流

```
POST /api/v1/predict  或  告警分析内嵌 impact_prediction
        │
        ▼
PredictiveEngine：拉取 Prometheus 历史序列 → 线性趋势外推
        │
        ▼
返回 overall_risk、forecasts、recommendation
```

---

## 4. 核心组件详解

### 4.1 数据接入层

#### 4.1.1 Prometheus Collector

```python
# src/langops/collectors/prometheus_collector.py

from datetime import datetime, timedelta
from typing import List, Dict, Any
import aiohttp

class PrometheusCollector:
    """Prometheus 指标采集器"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
    
    async def collect_pod_metrics(
        self,
        namespace: str,
        pod_name: str,
        time_window: timedelta = timedelta(minutes=30)
    ) -> Dict[str, Any]:
        """
        采集 Pod 相关指标
        
        Args:
            namespace: K8s 命名空间
            pod_name: Pod 名称
            time_window: 查询时间窗口
            
        Returns:
            指标数据字典
        """
        end_time = datetime.now()
        start_time = end_time - time_window
        
        queries = {
            "cpu_usage": f"""
                sum(rate(container_cpu_usage_seconds_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m])) by (container)
            """,
            "memory_usage": f"""
                container_memory_usage_bytes{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "restart_count": f"""
                kube_pod_container_status_restarts_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "network_errors": f"""
                sum(rate(container_network_receive_errors_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m]))
            """
        }
        
        results = {}
        for metric_name, query in queries.items():
            results[metric_name] = await self._query_range(
                query, start_time, end_time
            )
        
        return results
    
    async def _query_range(
        self,
        query: str,
        start: datetime,
        end: datetime
    ) -> List[Dict]:
        """执行 PromQL 范围查询"""
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": "15s"
        }
        
        async with self.session.get(url, params=params) as resp:
            data = await resp.json()
            return data.get("data", {}).get("result", [])
```

#### 4.1.2 阿里云 CMS Collector

```python
# src/langops/collectors/aliyun_cms_collector.py

from alibabacloud_cms20190101 import Client as CmsClient
from alibabacloud_tea_openapi import models as open_api_models

class AliyunCmsCollector:
    """阿里云云监控采集器"""
    
    def __init__(self, access_key_id: str, access_key_secret: str):
        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret
        )
        config.endpoint = "metrics.aliyuncs.com"
        self.client = CmsClient(config)
    
    async def collect_ecs_metrics(
        self,
        instance_id: str,
        time_window: timedelta = timedelta(minutes=30)
    ) -> Dict[str, Any]:
        """采集 ECS 实例指标"""
        metrics = [
            "CPUUtilization",      # CPU 使用率
            "memory_usedutilization",  # 内存使用率
            "DiskReadIOPS",        # 磁盘读 IOPS
            "DiskWriteIOPS",       # 磁盘写 IOPS
            "InternetInRate",      # 公网入流量
            "InternetOutRate"      # 公网出流量
        ]
        
        results = {}
        for metric in metrics:
            results[metric] = await self._query_metric(
                namespace="acs_ecs_dashboard",
                metric_name=metric,
                instance_id=instance_id,
                time_window=time_window
            )
        
        return results
    
    async def collect_rds_metrics(
        self,
        instance_id: str,
        time_window: timedelta = timedelta(minutes=30)
    ) -> Dict[str, Any]:
        """采集 RDS 实例指标"""
        metrics = [
            "CpuUsage",           # CPU 使用率
            "MemoryUsage",        # 内存使用率
            "IOPSUsage",          # IOPS 使用率
            "ConnectionUsage",    # 连接数使用率
            "DiskUsage"           # 磁盘使用率
        ]
        
        results = {}
        for metric in metrics:
            results[metric] = await self._query_metric(
                namespace="acs_rds_dashboard",
                metric_name=metric,
                instance_id=instance_id,
                time_window=time_window
            )
        
        return results
```

### 4.2 智能分析层

#### 4.2.1 AI Agent Core

```python
# src/langops/agent/alert_processor.py

from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
from typing import Optional
import json

class AlertProcessor:
    """
    告警处理器 - 智能分析核心
    
    职责:
    1. 接收告警事件
    2. 聚合多维度上下文数据
    3. 调用 LLM 进行根因分析
    4. 检索历史相似案例
    5. 生成修复建议
    """
    
    def __init__(
        self,
        langfuse: Langfuse,
        llm_client,
        vector_store,
        prometheus_collector,
        aliyun_collector
    ):
        self.langfuse = langfuse
        self.llm = llm_client
        self.vector_store = vector_store
        self.prom_collector = prometheus_collector
        self.aliyun_collector = aliyun_collector
    
    @observe(as_type="processor")
    async def process_alert(self, alert: Alert) -> AnalysisResult:
        """
        处理单个告警，返回分析结果
        
        Args:
            alert: 标准化告警对象
            
        Returns:
            AnalysisResult: 包含根因、建议、Trace ID 的结果
        """
        # 更新 Trace 元数据
        langfuse_context.update_current_trace(
            name="alert_analysis",
            user_id=alert.service,
            metadata={
                "alert_id": alert.id,
                "severity": alert.severity,
                "category": alert.category,
                "source": alert.source
            }
        )
        
        # Step 1: 收集上下文数据
        context = await self._collect_context(alert)
        
        # Step 2: 根因分析
        root_cause = await self._analyze_root_cause(context)
        
        # Step 3: 知识检索
        similar_cases = await self._retrieve_similar_cases(alert)
        
        # Step 4: 生成修复建议
        suggestion = await self._generate_remediation(
            root_cause, similar_cases
        )
        
        # Step 5: 预测影响
        impact = await self._predict_impact(context, root_cause)
        
        return AnalysisResult(
            alert_id=alert.id,
            trace_id=langfuse_context.get_current_trace_id(),
            root_cause=root_cause,
            similar_cases=similar_cases,
            suggestion=suggestion,
            impact_prediction=impact,
            timestamp=datetime.now()
        )
    
    @observe(as_type="span")
    async def _collect_context(self, alert: Alert) -> AlertContext:
        """收集告警相关的上下文数据"""
        context = AlertContext(alert=alert)
        
        # 根据告警类型收集不同数据
        if alert.source.type == "kubernetes":
            context.metrics = await self.prom_collector.collect_pod_metrics(
                namespace=alert.source.namespace,
                pod_name=alert.source.pod_name
            )
            context.events = await self._collect_k8s_events(alert)
            
        elif alert.source.type == "aliyun":
            if alert.source.resource_type == "ecs":
                context.metrics = await self.aliyun_collector.collect_ecs_metrics(
                    instance_id=alert.source.instance_id
                )
            elif alert.source.resource_type == "rds":
                context.metrics = await self.aliyun_collector.collect_rds_metrics(
                    instance_id=alert.source.instance_id
                )
        
        # 收集相关日志
        context.logs = await self._collect_related_logs(alert)
        
        return context
    
    @observe(as_type="generation")
    async def _analyze_root_cause(self, context: AlertContext) -> RootCause:
        """使用 LLM 分析根因"""
        prompt = self._build_rca_prompt(context)
        
        response = await self.llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_RCA},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        return RootCause(
            category=result["root_cause_category"],
            description=result["description"],
            confidence=result["confidence"],
            evidence=result["key_evidence"],
            related_metrics=result.get("related_metrics", [])
        )
    
    @observe(as_type="span")
    async def _retrieve_similar_cases(
        self,
        alert: Alert,
        top_k: int = 3
    ) -> List[SimilarCase]:
        """从向量库检索相似历史案例"""
        # 向量化告警描述
        query_embedding = await self.vector_store.embed(
            text=f"{alert.title} {alert.description}"
        )
        
        # 相似度搜索
        results = await self.vector_store.search(
            embedding=query_embedding,
            top_k=top_k,
            filter={
                "category": alert.category,
                "resolved": True
            }
        )
        
        similar_cases = []
        for result in results:
            similar_cases.append(SimilarCase(
                case_id=result.id,
                similarity_score=result.score,
                title=result.metadata["title"],
                root_cause=result.metadata["root_cause"],
                solution=result.metadata["solution"],
                resolution_time=result.metadata.get("resolution_time")
            ))
        
        return similar_cases
    
    @observe(as_type="generation")
    async def _generate_remediation(
        self,
        root_cause: RootCause,
        similar_cases: List[SimilarCase]
    ) -> RemediationSuggestion:
        """生成修复建议"""
        prompt = self._build_suggestion_prompt(root_cause, similar_cases)
        
        response = await self.llm.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_REMEDIATION},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        
        return RemediationSuggestion(
            summary=result["summary"],
            steps=result["steps"],
            commands=result.get("commands", []),
            risks=result.get("risks", []),
            rollback_plan=result.get("rollback_plan"),
            estimated_time=result.get("estimated_time", "unknown")
        )
    
    def _build_rca_prompt(self, context: AlertContext) -> str:
        """构建根因分析提示词"""
        return f"""请分析以下告警的根因：

告警信息:
- 标题: {context.alert.title}
- 描述: {context.alert.description}
- 严重程度: {context.alert.severity}
- 服务: {context.alert.service}
- 时间: {context.alert.timestamp}

指标数据:
{json.dumps(context.metrics, indent=2, ensure_ascii=False)}

相关事件:
{json.dumps(context.events, indent=2, ensure_ascii=False)}

相关日志 (最近10条):
{chr(10).join(context.logs[:10])}

请输出 JSON 格式：
{{
  "root_cause_category": "根因分类(资源不足/配置错误/依赖故障/代码缺陷/外部因素)",
  "description": "详细的根因描述",
  "confidence": 0.85,
  "key_evidence": ["证据1", "证据2"],
  "related_metrics": ["关联指标1", "关联指标2"],
  "impact_analysis": "影响范围分析"
}}
"""
```

### 4.3 数据存储层

#### 4.3.1 向量知识库

```python
# src/knowledge/vector_store.py

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any
import hashlib

class VectorStore:
    """
    向量知识库 - 存储和检索运维知识
    
    存储内容：
    - 历史故障案例
    - 运维手册片段
    - 解决方案
    """
    
    def __init__(self, persist_directory: str = "./data/vector_db"):
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_directory
        ))
        self.collection = self.client.get_or_create_collection(
            name="ops_knowledge",
            metadata={"description": "运维知识库"}
        )
        self.embedding_model = None  # 注入 embedding 模型
    
    async def add_case(self, case: FailureCase) -> str:
        """
        添加故障案例到知识库
        
        Args:
            case: 故障案例对象
            
        Returns:
            case_id: 案例唯一标识
        """
        # 生成唯一 ID
        case_id = hashlib.md5(
            f"{case.title}{case.timestamp}".encode()
        ).hexdigest()
        
        # 向量化文档
        document = f"""
故障: {case.title}
描述: {case.description}
根因: {case.root_cause}
解决方案: {case.solution}
        """.strip()
        
        embedding = await self.embed(document)
        
        # 存储到向量库
        self.collection.add(
            ids=[case_id],
            embeddings=[embedding],
            documents=[document],
            metadatas=[{
                "title": case.title,
                "category": case.category,
                "service": case.service,
                "root_cause": case.root_cause,
                "solution": case.solution,
                "resolution_time": case.resolution_time,
                "resolved": case.resolved,
                "timestamp": case.timestamp.isoformat()
            }]
        )
        
        return case_id
    
    async def search(
        self,
        query: str = None,
        embedding: List[float] = None,
        top_k: int = 5,
        filter: Dict[str, Any] = None
    ) -> List[SearchResult]:
        """
        搜索相似案例
        
        Args:
            query: 文本查询（自动向量化）
            embedding: 向量查询（优先使用）
            top_k: 返回结果数量
            filter: 元数据过滤条件
            
        Returns:
            相似案例列表
        """
        if embedding is None and query is not None:
            embedding = await self.embed(query)
        
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=filter
        )
        
        search_results = []
        for i in range(len(results["ids"][0])):
            search_results.append(SearchResult(
                id=results["ids"][0][i],
                score=results["distances"][0][i],
                document=results["documents"][0][i],
                metadata=results["metadatas"][0][i]
            ))
        
        return search_results
    
    async def embed(self, text: str) -> List[float]:
        """文本向量化"""
        # 使用 embedding 模型
        # 例如: text-embedding-3-small, bge-large-zh
        return await self.embedding_model.embed(text)
```

---

## 5. 数据模型

### 5.1 核心数据模型

```python
# src/models/alert.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class AlertSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class AlertCategory(Enum):
    RESOURCE = "resource"       # 资源类
    AVAILABILITY = "availability"  # 可用性
    PERFORMANCE = "performance"    # 性能
    SECURITY = "security"       # 安全

@dataclass
class AlertSource:
    """告警来源信息"""
    type: str  # prometheus, aliyun, kubernetes, custom
    system: str  # 系统/集群名称
    service: Optional[str] = None
    namespace: Optional[str] = None
    pod_name: Optional[str] = None
    instance_id: Optional[str] = None
    resource_type: Optional[str] = None  # ecs, rds, slb

@dataclass
class Alert:
    """标准化告警对象"""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    source: AlertSource
    timestamp: datetime
    metric_data: Dict[str, Any]
    log_snippets: List[str]
    related_events: List[str]
    context: Dict[str, Any]
    
@dataclass
class RootCause:
    """根因分析结果"""
    category: str
    description: str
    confidence: float  # 0-1
    evidence: List[str]
    related_metrics: List[str]
    impact_analysis: Optional[str] = None

@dataclass
class SimilarCase:
    """相似历史案例"""
    case_id: str
    similarity_score: float
    title: str
    root_cause: str
    solution: str
    resolution_time: Optional[int] = None  # 分钟

@dataclass
class RemediationSuggestion:
    """修复建议"""
    summary: str
    steps: List[str]
    commands: List[str]
    risks: List[str]
    rollback_plan: Optional[str]
    estimated_time: str

@dataclass
class AnalysisResult:
    """完整分析结果"""
    alert_id: str
    trace_id: str
    root_cause: RootCause
    similar_cases: List[SimilarCase]
    suggestion: RemediationSuggestion
    impact_prediction: Dict[str, Any]
    timestamp: datetime
```

---

## 6. API 设计

### 6.1 RESTful API

```yaml
# API 概览

openapi: 3.0.0
info:
  title: LangOps API
  version: 1.0.0
  description: AI 智能化运维平台 API

paths:
  # 告警处理
  /api/v1/alerts:
    post:
      summary: 接收告警并触发分析
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Alert'
      responses:
        200:
          description: 分析结果
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AnalysisResult'
    
    get:
      summary: 查询告警列表
      parameters:
        - name: service
          in: query
          schema:
            type: string
        - name: severity
          in: query
          schema:
            type: string
            enum: [critical, high, medium, low]
        - name: time_range
          in: query
          schema:
            type: string
            example: "1h, 24h, 7d"
      responses:
        200:
          description: 告警列表

  /api/v1/alerts/{alert_id}:
    get:
      summary: 获取告警详情
      parameters:
        - name: alert_id
          in: path
          required: true
          schema:
            type: string
      responses:
        200:
          description: 告警详情

  # 自然语言查询
  /api/v1/query:
    post:
      summary: 自然语言查询
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  example: "过去24小时CPU使用率最高的服务"
      responses:
        200:
          description: 查询结果
          content:
            application/json:
              schema:
                type: object
                properties:
                  answer:
                    type: string
                  promql:
                    type: string
                  data:
                    type: array

  # 知识库管理
  /api/v1/knowledge/cases:
    get:
      summary: 搜索知识库案例
      parameters:
        - name: q
          in: query
          description: 搜索关键词
          schema:
            type: string
      responses:
        200:
          description: 案例列表
    
    post:
      summary: 添加案例到知识库
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/FailureCase'
      responses:
        201:
          description: 创建成功

  # Trace 查询
  /api/v1/traces/{trace_id}:
    get:
      summary: 获取 Trace 详情
      description: 查询 Langfuse Trace 的完整链路
      parameters:
        - name: trace_id
          in: path
          required: true
          schema:
            type: string
      responses:
        200:
          description: Trace 详情

components:
  schemas:
    Alert:
      type: object
      properties:
        id:
          type: string
        title:
          type: string
        description:
          type: string
        severity:
          type: string
          enum: [critical, high, medium, low, info]
        category:
          type: string
          enum: [resource, availability, performance, security]
        source:
          type: object
        timestamp:
          type: string
          format: date-time
    
    AnalysisResult:
      type: object
      properties:
        alert_id:
          type: string
        trace_id:
          type: string
        root_cause:
          $ref: '#/components/schemas/RootCause'
        similar_cases:
          type: array
          items:
            $ref: '#/components/schemas/SimilarCase'
        suggestion:
          $ref: '#/components/schemas/RemediationSuggestion'
    
    RootCause:
      type: object
      properties:
        category:
          type: string
        description:
          type: string
        confidence:
          type: number
          minimum: 0
          maximum: 1
        evidence:
          type: array
          items:
            type: string
    
    SimilarCase:
      type: object
      properties:
        case_id:
          type: string
        similarity_score:
          type: number
        title:
          type: string
        root_cause:
          type: string
        solution:
          type: string
    
    RemediationSuggestion:
      type: object
      properties:
        summary:
          type: string
        steps:
          type: array
          items:
            type: string
        commands:
          type: array
          items:
            type: string
        risks:
          type: array
          items:
            type: string
    
    FailureCase:
      type: object
      properties:
        title:
          type: string
        description:
          type: string
        category:
          type: string
        service:
          type: string
        root_cause:
          type: string
        solution:
          type: string
        resolution_time:
          type: integer
          description: 解决时间（分钟）
```

---

## 7. 部署架构

### 7.1 Kubernetes 部署

```yaml
# deployment/langops-deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: langops-agent
  namespace: langops
spec:
  replicas: 2
  selector:
    matchLabels:
      app: langops-agent
  template:
    metadata:
      labels:
        app: langops-agent
    spec:
      containers:
        - name: agent
          image: langops/agent:latest
          ports:
            - containerPort: 8000
          env:
            - name: LANGFUSE_HOST
              value: "http://langfuse-server:3000"
            - name: LANGFUSE_PUBLIC_KEY
              valueFrom:
                secretKeyRef:
                  name: langops-secrets
                  key: langfuse-public-key
            - name: PROMETHEUS_URL
              value: "http://prometheus:9090"
            - name: REDIS_URL
              value: "redis://redis:6379"
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "2Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: langops-agent
  namespace: langops
spec:
  selector:
    app: langops-agent
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

### 7.2 依赖服务

```yaml
# deployment/dependencies.yaml

# Langfuse Server
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langfuse-server
  namespace: langops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: langfuse-server
  template:
    metadata:
      labels:
        app: langfuse-server
    spec:
      containers:
        - name: langfuse
          image: ghcr.io/langfuse/langfuse:latest
          ports:
            - containerPort: 3000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: langops-secrets
                  key: database-url
            - name: NEXTAUTH_SECRET
              valueFrom:
                secretKeyRef:
                  name: langops-secrets
                  key: nextauth-secret
            - name: SALT
              valueFrom:
                secretKeyRef:
                  name: langops-secrets
                  key: salt

---
# ChromaDB (向量数据库)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chromadb
  namespace: langops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chromadb
  template:
    metadata:
      labels:
        app: chromadb
    spec:
      containers:
        - name: chromadb
          image: chromadb/chroma:latest
          ports:
            - containerPort: 8000
          volumeMounts:
            - name: chromadb-data
              mountPath: /chroma/chroma
      volumes:
        - name: chromadb-data
          persistentVolumeClaim:
            claimName: chromadb-pvc

---
# Redis (缓存)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: langops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
        - name: redis
          image: redis:7-alpine
          ports:
            - containerPort: 6379
```

---

## 8. 配置管理

### 8.1 应用配置

```yaml
# config/application.yaml

langops:
  # 服务配置
  server:
    host: "0.0.0.0"
    port: 8000
    workers: 4
  
  # Langfuse 配置
  langfuse:
    host: "${LANGFUSE_HOST}"
    public_key: "${LANGFUSE_PUBLIC_KEY}"
    secret_key: "${LANGFUSE_SECRET_KEY}"
  
  # LLM 配置
  llm:
    provider: "openai"  # openai, azure, anthropic
    model: "gpt-4"
    temperature: 0.2
    max_tokens: 2000
    timeout: 30
  
  # Embedding 配置
  embedding:
    provider: "openai"
    model: "text-embedding-3-small"
    batch_size: 100
  
  # 数据采集配置
  collectors:
    prometheus:
      url: "${PROMETHEUS_URL}"
      timeout: 10
      scrape_interval: 15
    
    aliyun:
      access_key_id: "${ALIYUN_ACCESS_KEY_ID}"
      access_key_secret: "${ALIYUN_ACCESS_KEY_SECRET}"
      region: "cn-hangzhou"
    
    kubernetes:
      config_path: "~/.kube/config"
      in_cluster: true
  
  # 向量数据库配置
  vector_store:
    type: "chromadb"  # chromadb, milvus, pgvector
    persist_directory: "./data/vector_db"
    collection_name: "ops_knowledge"
  
  # 告警处理配置
  alert_processor:
    # 根因分析配置
    rca:
      max_evidence_count: 5
      min_confidence: 0.6
    
    # RAG 配置
    rag:
      top_k: 3
      similarity_threshold: 0.7
      max_context_length: 4000
    
    # 通知配置
    notification:
      channels:
        - type: "feishu"
          webhook: "${FEISHU_WEBHOOK}"
          enabled: true
        - type: "dingtalk"
          webhook: "${DINGTALK_WEBHOOK}"
          enabled: false
  
  # 知识库配置
  knowledge:
    # 自动归档规则
    auto_archive:
      enabled: true
      min_confidence: 0.8
      require_feedback: true
```

---

## 9. 监控与可观测性

### 9.1 Langfuse 集成

```python
# src/observability/langfuse_setup.py

from langfuse import Langfuse
from langfuse.decorators import langfuse_context

# 初始化 Langfuse
langfuse = Langfuse(
    public_key="${LANGFUSE_PUBLIC_KEY}",
    secret_key="${LANGFUSE_SECRET_KEY}",
    host="${LANGFUSE_HOST}"
)

# 自动评估规则
async def setup_evaluations():
    """配置 Langfuse 自动评估"""
    
    # 评估规则 1: 根因分析质量
    @langfuse.evaluation("rca_quality")
    async def evaluate_rca(trace):
        output = trace.output
        
        checks = {
            "has_evidence": len(output.get("evidence", [])) >= 2,
            "confidence_ok": output.get("confidence", 0) > 0.7,
            "has_category": output.get("category") is not None,
        }
        
        return {
            "score": sum(checks.values()) / len(checks),
            **checks
        }
    
    # 评估规则 2: 建议可执行性
    @langfuse.evaluation("actionability")
    async def evaluate_actionability(trace):
        output = trace.output
        suggestion = output.get("suggestion", {})
        
        checks = {
            "has_steps": len(suggestion.get("steps", [])) >= 1,
            "has_commands": len(suggestion.get("commands", [])) >= 1,
            "has_risk_assessment": len(suggestion.get("risks", [])) >= 1,
        }
        
        return {
            "score": sum(checks.values()) / len(checks),
            **checks
        }
```

### 9.2 自定义指标

```python
# src/observability/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# 业务指标
ALERTS_PROCESSED = Counter(
    'langops_alerts_processed_total',
    'Total number of alerts processed',
    ['category', 'severity', 'status']
)

ANALYSIS_DURATION = Histogram(
    'langops_analysis_duration_seconds',
    'Time spent on alert analysis',
    ['stage']  # collect, rca, rag, suggest
)

LLM_TOKENS = Counter(
    'langops_llm_tokens_total',
    'Total LLM tokens consumed',
    ['model', 'operation']
)

KNOWLEDGE_CASES = Gauge(
    'langops_knowledge_cases_total',
    'Total cases in knowledge base',
    ['category']
)

RAG_SIMILARITY = Histogram(
    'langops_rag_similarity_score',
    'Similarity score of RAG results'
)
```

---

## 10. 演进路线

### Phase 1: MVP — ✅ 已完成

| 功能 | 状态 | 说明 |
|-----|------|------|
| Prometheus 数据采集 | ✅ | `prometheus_collector.py` |
| 基础根因分析 | ✅ | `RCAEngine` + `prompts.py` |
| Langfuse 集成 | ✅ | `AlertProcessor` 全链路 Trace |
| 告警 API | ✅ | `POST /api/v1/alerts` |
| ChromaDB 知识库 | ✅ | `vector_store.py` + `init_knowledge.py` |

### Phase 2: 增强 — ✅ 已完成

| 功能 | 状态 | 说明 |
|-----|------|------|
| 阿里云 CMS 集成 | ✅ | `aliyun_cms_collector.py` |
| 自然语言查询 | ✅ | `nl_query_engine.py`，`POST /api/v1/query` |
| Web UI | ✅ | 静态资源 `/ui`（告警 / 查询 / 预测 / 修复审批） |
| 飞书/钉钉通知 | ✅ | `notification.py` |
| JIRA 工单集成 | ⏳ | 规划中 |

### Phase 3: 智能化 — ✅ 已完成

| 功能 | 状态 | 说明 |
|-----|------|------|
| 预测性运维 | ✅ | `predictive_engine.py`，`POST /api/v1/predict` |
| 告警降噪 | ✅ | `alert_dedup.py`，响应 `dedup` 字段 |
| 自动修复（人工审批） | ✅ | `remediation_executor.py`，kubectl 白名单 + dry-run |
| 多租户 | ⏳ | 规划中 |

### Phase 4: 生产化（规划中）

| 功能 | 优先级 | 说明 |
|-----|-------|------|
| 认证与 RBAC | P0 | API / 修复审批鉴权 |
| 持久化状态 | P0 | 降噪分组、修复计划存 Redis/DB |
| JIRA / Slack | P1 | 工单与多渠道通知 |
| Loki / K8s Events 采集 | P1 | 扩展上下文维度 |
| React SPA | P2 | 替换当前静态 Web UI（可选） |

---

## 11. 附录

### 11.1 术语表

| 术语 | 说明 |
|-----|------|
| Langfuse | LLM 应用可观测性平台 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| RCA | Root Cause Analysis，根因分析 |
| MTTR | Mean Time To Repair，平均修复时间 |
| PromQL | Prometheus 查询语言 |
| NL2PromQL | Natural Language to PromQL，自然语言转查询 |
| RemediationPlan | 待人工审批的修复执行计划 |
| Alert Dedup | 告警降噪，窗口内重复告警抑制 LLM 调用 |

### 11.2 参考资源

- [Langfuse 官方文档](https://langfuse.com/docs)
- [Prometheus 最佳实践](https://prometheus.io/docs/practices/)
- [Kubernetes 监控指南](https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/)
- [阿里云云监控文档](https://help.aliyun.com/product/43508.html)

---

**文档版本**: v1.1.0  
**最后更新**: 2026-06-25（同步 Phase 1–3 实现状态）  
**作者**: LangOps Team
