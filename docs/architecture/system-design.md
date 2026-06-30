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
| Phase 2 | 阿里云 CMS、NL2PromQL、飞书/钉钉/企微通知、Web UI、JIRA 工单 | ✅ 已交付 | `collectors/`、`nl_query_engine.py`、`notification.py`、`web/static/`、`services/jira_integration.py` |
| Phase 3 | 预测性运维、告警降噪、修复审批执行、SQLAlchemy 持久化 | ✅ 已交付 | `predictive_engine.py`、`alert_dedup.py`、`remediation_executor.py`、`storage/` |
| 规划中 | Loki/K8s Events 采集、多租户、React SPA | ⏳ 未实现 | — |

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
│  │  │ (静态 /ui)   │  │ (飞书/钉钉/企微)  │  │  (FastAPI)   │               │   │
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
│  │                                                                      │   │
│  │  Push · 告警接入（Webhook Adapter — 外部 → LangOps）                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ Alertmanager │  │ 阿里云 CMS   │  │   Custom     │               │   │
│  │  │    [Push]    │  │  Webhook     │  │  Webhooks    │               │   │
│  │  │              │  │    [Push]    │  │    [Push]    │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  │                                                                      │   │
│  │  Pull · 上下文采集（Collector — LangOps → 外部，BaseCollector）      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │  Prometheus  │  │ 阿里云 CMS   │  │    Loki      │               │   │
│  │  │    [Pull]    │  │   [Pull]     │  │ [Pull·规划]  │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 各层职责

| 层级 | 核心职责 | 关键技术 |
|-----|---------|---------|
| **接入层** | 对接外部系统：Push 告警接入 + Pull 上下文采集 | Webhook Adapter、`BaseCollector`、Prometheus/阿里云 SDK |
| **数据层** | 存储观测数据、向量知识、缓存 | Langfuse、ChromaDB、Redis |
| **智能层** | AI 分析核心，实现 RCA/RAG/建议 | OpenAI API、自定义 Agent、Langfuse 追踪 |
| **服务层** | 通知、JIRA 工单、降噪分组、修复计划管理 | aiohttp、Webhook、SQLAlchemy |
| **交互层** | 用户界面、告警通道、API 服务 | 静态 Web UI（`/ui`）、FastAPI、Webhook |

### 2.3 接入模式：Collector vs Webhook Adapter

LangOps 接入层包含两种**方向相反**的集成，不可混称为 Collector：

| 概念 | 模式 | 数据方向 | 触发时机 | 代码位置 |
|-----|------|---------|---------|---------|
| **Webhook Adapter** | **Push** | 外部 → LangOps | 告警/fire 时外部主动 POST | `adapters/*.py`，`POST /api/v1/webhooks/*` |
| **Collector** | **Pull** | LangOps → 外部 | 收到告警后、RCA 前补上下文 | `collectors/BaseCollector`，`AlertProcessor._collect_context` |

**Collector 定义（Pull-only）**

- 继承 `BaseCollector`，在分析流水线 Phase 2（数据聚合）被调用。
- LangOps 根据告警的 `source` / 标签 / 时间窗口，**主动查询**外部 API（PromQL、CMS API、未来 LogQL 等）。
- 典型实现：`PrometheusCollector`、`AliyunCmsCollector`（指标查询，非 Webhook）。

**Webhook Adapter 定义（Push）**

- **不是 Collector**。外部系统在告警触发时向 LangOps 推送事件。
- Adapter 将载荷映射为 `AlertCreate`，进入 `process_one_alert` 流水线。
- 典型实现：`AlertmanagerAdapter`、`AliyunCmsWebhookAdapter`。

同一生态可同时存在 Push + Pull（例如阿里云：CMS Webhook 推送告警，CMS Collector 拉回指标序列）。

```
Push:  Alertmanager ──POST──▶ LangOps          （告警入口）
Pull:  LangOps ──GET PromQL──▶ Prometheus       （上下文 enrichment）
```

| 组件 | 模式 | 说明 |
|-----|------|------|
| Alertmanager Webhook | Push | Prometheus 告警链路入口 |
| 阿里云 CMS Webhook | Push | 云监控告警入口 |
| Prometheus Collector | Pull | 指标 / K8s 标签关联的 PromQL 查询 |
| 阿里云 CMS Collector | Pull | ECS/RDS 等指标序列 |
| Loki Collector | Pull | 规划中，LogQL 日志查询 |
| Custom Webhooks | Push | 规划中，自定义告警源 |

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
│   │ 1. 告警接收      │  ◀── Push（Webhook Adapter）                         │
│   │    (Webhook)    │                                                        │
│   │                 │                                                        │
│   │ • Alertmanager  │                                                        │
│   │  (Prometheus)   │                                                        │
│   │ • 阿里云 CMS    │                                                        │
│   │   Webhook       │                                                        │
│   │ • 定时巡检任务  │  ◀── 内部触发（非外部 Push）                          │
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
│   │ 2. 数据聚合 (Data Collection)  ◀── Pull（Collector）              │      │
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
│  │  result = prometheus_collector.query_instant(                       │    │
│  │    promql=generated_promql,  # 瞬时查询，非 range                    │    │
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
┌─────────────────────┐     窗口内重复      ┌───────────────────┐
│ AlertNoiseReducer  │ ── fingerprint ──▶ │ action=suppress   │
│ (默认 900s 窗口)     │                     │ 跳过 LLM，返回 dedup │
└─────────────────────┘                     └───────────────────┘
        │ 新告警 / 窗口外
        ▼
   正常 AlertProcessor 流水线
```

- 指纹：`AlertNoiseReducer.fingerprint()` 基于 `category`、`severity`、`source.type`、`source.system`、`source.namespace`、`resource`、`标准化 title`（去除数字）生成 SHA256 前 16 位
- 降噪结果 `DedupInfo`：含 `action`（`process` / `suppress`）、`fingerprint`、`occurrence_count`、`message`
- 配置：`ALERT_DEDUP_ENABLED`、`ALERT_DEDUP_WINDOW_SECONDS`
- 统计：`GET /api/v1/alerts/dedup/stats` → `{"active_groups": N, "window_seconds": 900}`

### 3.4 修复审批工作流

```
分析完成且 suggestion.commands 非空
        │
        ▼
RemediationRegistry.create_from_analysis()  →  RemediationStatus.PENDING_APPROVAL
        │
        ▼
AnalysisResponse.remediation_plan_id
        │
        ├── Web UI「修复审批」页签
        └── API:
              GET  /api/v1/remediation
              POST /api/v1/remediation/{id}/execute  (dry_run=true 默认)
              POST /api/v1/remediation/{id}/reject
```

**安全策略**（`RemediationExecutor`）：

| 项 | 默认行为 |
|----|---------|
| `REMEDIATION_ENABLED` | `true`：注册计划 |
| `REMEDIATION_EXECUTION_ENABLED` | `false`：禁止真实命令执行 |
| kubectl 白名单 | `kubectl scale` / `kubectl patch` / `kubectl rollout restart` / `kubectl set resources` |
| 拦截关键词 | `delete`、`exec`、`apply -f http`、`curl`、`wget`、`bash`、`sh -c`、`rm -`、`dd` |
| 风险评估 | `assess_command_risk()`：全部白名单 → low；部分 → medium；全拦截 → high |
| 执行条件 | 仅 `risk_level=low` 且 `confirm=true` 才执行真实命令 |

> ponytail：计划状态存储在 SQLAlchemy（`storage/` 模块）；生产环境可迁移至 Redis/PostgreSQL。

### 3.5 预测性运维工作流

```
POST /api/v1/predict  或  告警分析内嵌 impact_prediction
        │
        ▼
PredictiveEngine：拉取 Prometheus 历史序列 → numpy OLS 线性趋势外推
        │
        ▼
返回 ImpactPrediction（overall_risk、forecasts、recommendation、confidence）
```

---

## 4. 核心组件详解

### 4.1 数据接入层

> **Collector = Pull-only**（见 §2.3）。告警 Push 接入走 Webhook Adapter，不在 `collectors/` 目录。

#### 4.1.1 Prometheus Collector（Pull）

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

#### 4.1.2 阿里云 CMS Collector（Pull）

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

from langfuse.decorators import observe, langfuse_context

class AlertProcessor:
    """
    告警处理器 - 智能分析核心

    职责：
    1. 接收告警事件
    2. 聚合多维度上下文数据
    3. 调用 LLM 进行根因分析
    4. 检索历史相似案例
    5. 生成修复建议
    """

    @observe(as_type="processor")
    async def process(self, alert: Alert) -> AnalysisResult:
        # 更新 Langfuse Trace 元数据
        langfuse_context.update_current_trace(
            name="alert_analysis",
            metadata={
                "alert_id": alert.id,
                "severity": alert.severity.value,
                "category": alert.category.value,
                "source": alert.source.type,
            }
        )

        # Step 1: 收集上下文数据（Prometheus / 阿里云 CMS）
        context = await self._collect_context(alert)

        # Step 2: 根因分析（调用 LLM）
        root_cause = await self._analyze_root_cause(context)

        # Step 3: 知识检索（ChromaDB Top-K）
        similar_cases = await self._retrieve_similar_cases(alert)

        # Step 4: 生成修复建议（调用 LLM）
        suggestion = await self._generate_remediation(root_cause, similar_cases)

        # Step 5: 注册修复计划（如 commands 非空）
        remediation_plan = None
        if suggestion.commands:
            remediation_plan = await self._registry.create_from_analysis(
                AnalysisResult(alert=alert, root_cause=root_cause, ...)
            )

        return AnalysisResult(...)

    @observe(as_type="span")
    async def _collect_context(self, alert: Alert) -> AlertContext:
        """收集告警相关的上下文数据"""
        # source.type == "kubernetes" → prometheus_collector.collect_pod_metrics()
        # source.type == "aliyun"     → aliyun_collector.collect_ecs/rds_metrics()
        ...

    @observe(as_type="generation")
    async def _analyze_root_cause(self, context: AlertContext) -> RootCause:
        """调用 LLM 分析根因（temperature=0.2，JSON 模式）"""
        prompt = build_rca_prompt(context)
        response = await self._llm.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return RootCause(**json.loads(response.choices[0].message.content))

    @observe(as_type="span")
    async def _retrieve_similar_cases(self, alert: Alert, top_k: int = 3):
        """ChromaDB 相似案例检索（filter: resolved=True）"""
        results = await self._vector_store.search(
            query=f"{alert.title} {alert.description}",
            top_k=top_k,
            filter_category=alert.category.value,
        )
        return [SimilarCase(score=r.score, **r.metadata) for r in results]

    @observe(as_type="generation")
    async def _generate_remediation(self, root_cause, similar_cases):
        """调用 LLM 生成修复建议（temperature=0.3）"""
        ...
```
```

### 4.3 数据存储层

#### 4.3.1 向量知识库（ChromaDB）

```python
# src/knowledge/vector_store.py

class VectorStore:
    """使用 ChromaDB 的向量知识库。"""

    def __init__(
        self,
        collection_name: str = "ops_knowledge",
        host: str = "localhost",
        port: int = 8001,
        persist_directory: str | None = None,
    ) -> None:
        # 持久化模式（本地文件）或 HTTP 模式（远程服务）
        if persist_directory:
            self.client = chromadb.PersistentClient(path=persist_directory)
        else:
            self.client = chromadb.HttpClient(host=host, port=port)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Operations knowledge base"},
        )

    async def add_case(self, title, description, category, service,
                       root_cause, solution, ...) -> str:
        # MD5 指纹作为 case_id；resolved 固定为 True
        metadata = {"title", "category", "service", "root_cause",
                     "solution", "resolved": True, ...}
        self.collection.add(ids=[case_id], documents=[document],
                            metadatas=[metadata])

    async def search(self, query: str, top_k: int = 3,
                     filter_category, filter_service) -> list[SearchResult]:
        # 自动用 query_texts 查询；相似度 = 1 / (1 + distance)
        results = self.collection.query(
            query_texts=[query], n_results=top_k,
            where=where_filter if len(where_filter) > 1 else None,
        )
```

#### 4.3.2 关系存储（SQLAlchemy）

```python
# src/langops/storage/base.py

class Storage(ABC):
    """统一存储门面 — 提供所有 Repository 的访问入口。"""
    @property @abstractmethod
    def alerts(self) -> AlertRepository: ...
    @property @abstractmethod
    def analyses(self) -> AnalysisRepository: ...
    @property @abstractmethod
    def dedup(self) -> DedupRepository: ...
    @property @abstractmethod
    def remediations(self) -> RemediationRepository: ...

class AlertRepository(ABC):
    async def save(alert: Alert) -> None: ...
    async def get(alert_id: str) -> dict | None: ...
    async def list_recent(limit=50, offset=0) -> list[dict]: ...

class DedupRepository(ABC):
    async def get(fingerprint: str) -> dict | None: ...
    async def upsert(fingerprint, first_seen, last_seen, count) -> None: ...
    async def purge_expired(cutoff) -> int: ...
    async def count() -> int: ...

class RemediationRepository(ABC):
    async def save(plan: RemediationPlan) -> None: ...
    async def get(plan_id: str) -> dict | None: ...
    async def update_status(plan_id, status, approved_by=..., ...) -> None: ...
    async def list_pending() -> list[dict]: ...
```

**实现**：`src/langops/storage/sql.py` → `SqlStorage`，默认 SQLite（`sqlite:///.langops/data.db`，走 SQLAlchemy 同步 driver + `asyncio.to_thread`），配置 `STORAGE_URL` 可切换 PostgreSQL。

**初始化**：
```bash
make init-db  # 创建 .langops/data.db 并初始化表结构
```

---

## 5. 数据模型

### 5.1 核心数据模型

> **注意**：所有领域模型使用 **Pydantic v2** `BaseModel`（`model_config = ConfigDict(extra="allow")`），不使用 `dataclass`。

```python
# src/langops/models/alert.py

class AlertSeverity(str, Enum):
    """告警严重级别（与 JSON 字符串一致）。"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class AlertCategory(str, Enum):
    RESOURCE = "resource"
    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    SECURITY = "security"

class AlertSource(BaseModel):
    """告警来源信息（extra="allow"，允许未知字段）。"""
    type: str
    system: str
    service: str | None = None
    namespace: str | None = None
    pod_name: str | None = None
    instance_id: str | None = None
    resource_type: str | None = None

class Alert(BaseModel):
    """标准化告警对象。"""
    id: str
    title: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    source: AlertSource
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metric_data: dict[str, Any] = Field(default_factory=dict)
    log_snippets: list[str] = Field(default_factory=list)
    related_events: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value):
        # "warning" → MEDIUM 等自动规范化
        ...

class AlertContext(BaseModel):
    """RCA 阶段的丰富上下文。"""
    alert: Alert
    metrics: dict[str, Any] = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    time_range_minutes: int = 30
```

```python
# src/langops/models/analysis.py

class RootCause(BaseModel):
    category: str
    description: str
    confidence: float  # 0-1
    evidence: list[str]
    related_metrics: list[str]
    impact_analysis: str | None = None

class SimilarCase(BaseModel):
    case_id: str
    similarity_score: float
    title: str
    root_cause: str
    solution: str
    resolution_time: int | None = None  # minutes

class RemediationSuggestion(BaseModel):
    summary: str
    steps: list[str]
    commands: list[str]
    risks: list[str]
    rollback_plan: str | None = None
    estimated_time: str = "unknown"

class AnalysisResult(BaseModel):
    alert_id: str
    trace_id: str
    root_cause: RootCause
    similar_cases: list[SimilarCase]
    suggestion: RemediationSuggestion
    impact_prediction: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

```python
# src/langops/models/remediation.py

class RemediationStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    DRY_RUN = "dry_run"
    EXECUTED = "executed"
    FAILED = "failed"

class RemediationPlan(BaseModel):
    plan_id: str
    alert_id: str
    trace_id: str
    summary: str
    commands: list[str]
    risks: list[str]
    rollback_plan: str | None = None
    risk_level: str  # low | medium | high
    status: RemediationStatus = RemediationStatus.PENDING_APPROVAL
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_by: str | None = None
    execution_output: str | None = None
    jira_issue_key: str | None = None

class RemediationExecuteRequest(BaseModel):
    approved_by: str
    confirm: bool  # 必须为 true 才执行
    dry_run: bool = False
```

```python
# src/langops/models/dedup.py

class DedupInfo(BaseModel):
    action: str           # "process" | "suppress"
    fingerprint: str
    occurrence_count: int
    window_seconds: int
    message: str
```

```python
# src/langops/models/prediction.py

class Forecast(BaseModel):
    metric: str
    horizon_minutes: int
    predicted_value: float
    confidence_lower: float
    confidence_upper: float

class PredictionResult(BaseModel):
    overall_risk: str   # low | medium | high
    forecasts: list[Forecast]
    recommendation: str
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

> **实际实现**：配置通过 `pydantic-settings` + `.env` 环境变量管理，无 `config/application.yaml`。`config/` 目录预留（当前为空），后续可扩展 YAML 配置。

```python
# src/langops/core/config.py

class Settings(BaseSettings):
    """根配置类 — 所有子配置通过 env prefix 隔离。"""

    # 应用
    app_name: str = "LangOps"
    debug: bool = False
    log_level: str = "INFO"

    # 服务器
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # 子配置（各自对应 env prefix）
    llm: LLMSettings               # env: LLM_*
    langfuse: LangfuseSettings     # env: LANGFUSE_*
    prometheus: PrometheusSettings  # env: PROMETHEUS_*
    aliyun: AliyunSettings          # env: ALIYUN_*
    vector_store: VectorStoreSettings  # env: VECTOR_*
    redis: RedisSettings            # env: REDIS_*
    feishu: FeishuSettings          # env: FEISHU_*
    dingtalk: DingtalkSettings     # env: DINGTALK_*
    wechat_work: WechatWorkSettings # env: WECHAT_WORK_*
    alert_dedup: AlertDedupSettings # env: ALERT_DEDUP_*
    remediation: RemediationSettings  # env: REMEDIATION_*
    jira: JiraSettings             # env: JIRA_*
    storage: StorageSettings        # env: STORAGE_*
```

**关键环境变量**（见 `.env.example`）：

| 变量 | 说明 | 默认值 |
|-----|------|--------|
| `LLM_API_KEY` | OpenAI API Key | — |
| `LLM_MODEL` | 模型名 | `gpt-4` |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥 | — |
| `LANGFUSE_SECRET_KEY` | Langfuse 私钥 | — |
| `LANGFUSE_HOST` | Langfuse 服务地址 | `http://localhost:3000` |
| `PROMETHEUS_URL` | Prometheus 地址 | `http://localhost:9090` |
| `STORAGE_URL` | 数据库 URL | `sqlite:///.langops/data.db` |
| `ALERT_DEDUP_ENABLED` | 启用降噪 | `true` |
| `ALERT_DEDUP_WINDOW_SECONDS` | 降噪窗口 | `900` |
| `REMEDIATION_EXECUTION_ENABLED` | 允许真实执行命令 | `false` |

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

> **实际实现**：`src/langops/web/metrics.py`，通过 `GET /metrics` 暴露（`prometheus_client`）。

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `langops_alerts_received_total` | Counter | severity, category | 接收告警总数 |
| `langops_alerts_processed_total` | Counter | severity, status | 处理完成总数 |
| `langops_alert_processing_duration_seconds` | Histogram | — | 告警处理端到端耗时 |
| `langops_dedup_suppressed_total` | Counter | — | 降噪抑制告警总数 |
| `langops_llm_calls_total` | Counter | model, status | LLM 调用总数 |
| `langops_llm_call_duration_seconds` | Histogram | model | LLM 调用耗时 |
| `langops_llm_tokens_total` | Counter | model, type | Token 用量（prompt/completion） |
| `langops_collector_query_duration_seconds` | Histogram | source | 数据采集器查询耗时 |
| `langops_remediation_plans_total` | Counter | risk_level | 修复计划创建总数 |
| `langops_remediation_actions_total` | Counter | action, status | 修复操作总数（execute/reject） |
| `langops_http_requests_total` | Counter | method, path, status_code | HTTP 请求总数 |
| `langops_http_request_duration_seconds` | Histogram | method, path | HTTP 请求耗时 |

---

## 10. 外部告警源（External Alert Sources — Push）

> 告警接入均为 **Push**，由 Webhook Adapter 处理，**不是 Collector**（见 §2.3）。

LangOps 通过 Webhook 接收器接入外部监控系统的告警。每个源都配有专属适配器（adapter），把外部载荷归一化为 LangOps 的 `AlertCreate` 模型。映射之后，所有源共享同一条分析流水线（`process_one_alert`）。

**当前支持的源：**

| 源 | 端点 | 适配器 | 模式 |
|----|------|--------|------|
| Prometheus AlertManager | `POST /api/v1/webhooks/alertmanager` | `AlertmanagerAdapter` | Push |
| 阿里云 CMS | `POST /api/v1/webhooks/aliyun-cms` | `AliyunCmsWebhookAdapter` | Push |

**数据流：**

```
外部系统 → POST /api/v1/webhooks/{source}
              │
              ├─ Content-Length 预检
              ├─ Pydantic 校验源特定载荷
              ├─ Adapter 映射 → list[AlertCreate]
              ├─ ?coalesce=Nm 缓冲（可选，进程内）
              └─ process_one_alert × N
                    ├─ dedup → 抑制？
                    ├─ AlertProcessor.process
                    ├─ persist_alert_and_result
                    └─（可选）remediation + JIRA
```

**适配器设计约束**（前瞻）：

- 适配器为具体类（非抽象基类），直到出现第二个具体适配器再考虑抽象
- 所有源共享：`process_one_alert`、`AuditLogger`、`CoalesceBuffer`、`WebhookBatchResponse` schema
- 新增源 = 一个新 adapter + 一个新 router + 复用同一共享流水线

---

## 11. 演进路线

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
| JIRA 工单集成 | ✅ | `services/jira_integration.py`（best-effort，失败不阻断） |

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
| 持久化状态 | P0 | 降噪分组、修复计划存 Redis/PostgreSQL |
| Slack 通知 | P1 | 多渠道通知扩展 |
| Loki / K8s Events 采集 | P1 | 扩展上下文维度 |
| React SPA | P2 | 替换当前静态 Web UI（可选） |

---

## 12. 附录

### 12.1 术语表

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

### 12.2 参考资源

- [Langfuse 官方文档](https://langfuse.com/docs)
- [Prometheus 最佳实践](https://prometheus.io/docs/practices/)
- [Kubernetes 监控指南](https://kubernetes.io/docs/concepts/cluster-administration/system-metrics/)
- [阿里云云监控文档](https://help.aliyun.com/product/43508.html)

---

**文档版本**: v1.2.0  
**最后更新**: 2026-06-26（同步代码：JIRA 已实现、storage 层、services 模块、metrics 完整、Makefile → UV）  
**作者**: LangOps Team
