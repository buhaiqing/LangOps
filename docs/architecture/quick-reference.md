# LangOps 快速参考指南

> 与当前代码库同步（Phase 1–3 已交付）。详细设计见 [system-design.md](./system-design.md)。

## 架构总览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Prometheus │     │  阿里云 CMS │     │  API/Webhook│
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
              ┌─────────────────────┐
              │   AlertProcessor    │
              │  采集 → RCA → RAG   │  ◄── Langfuse Trace
              │  → 建议 → 预测      │
              └──────────┬──────────┘
                         │
       ┌─────────────────┼─────────────────┐
       ▼                 ▼                 ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ 告警降噪     │  │ 修复计划     │  │ 通知        │
│ AlertDedup  │  │ Remediation │  │ 飞书/钉钉   │
└─────────────┘  └─────────────┘  └─────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │ Web UI `/ui`        │
              │ API `/api/v1/*`     │
              └─────────────────────┘
```

## 核心数据流

```
告警 POST ──▶ [降噪?] ──▶ 数据采集 ──▶ LLM RCA ──▶ ChromaDB RAG ──▶ 修复建议
                │                                              │
                │ suppress                                     ▼
                └──────────────────────────────────▶ 注册 RemediationPlan
                                                              │
                                                              ▼
                                                    人工审批 / dry-run
```

## 关键类与接口

### 1. AlertProcessor

```python
# langops.agent.alert_processor.AlertProcessor

async def process_alert(self, alert: Alert) -> AnalysisResult:
    """
    1. collect_context()        - Prometheus（+ 可选 CMS）
    2. analyze_root_cause()     - RCAEngine + Langfuse generation
    3. retrieve_similar_cases() - VectorStore
    4. generate_remediation()   - 修复建议（commands、risks）
    """
```

### 2. 数据模型（Pydantic）

```python
# 输入：langops.models.Alert

# 输出：langops.models.AnalysisResult
#   - trace_id, root_cause, similar_cases, suggestion
#   - impact_prediction（PredictiveEngine，可选）

# API 响应：langops.models.AnalysisResponse
#   - success, data, error
#   - dedup: DedupInfo（降噪指纹、action、count）
#   - remediation_plan_id（有待执行命令时）
```

### 3. API 端点（已实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/alerts` | 告警分析（含降噪、通知、修复计划） |
| GET | `/api/v1/alerts/dedup/stats` | 降噪统计 |
| POST | `/api/v1/query` | NL2PromQL 自然语言查询 |
| POST | `/api/v1/predict` | 容量趋势预测 |
| GET | `/api/v1/remediation` | 待审批修复计划 |
| GET | `/api/v1/remediation/{plan_id}` | 计划详情 |
| POST | `/api/v1/remediation/{plan_id}/execute` | 审批执行 / dry-run |
| POST | `/api/v1/remediation/{plan_id}/reject` | 拒绝计划 |
| GET | `/ui` | Web 管理界面 |
| GET | `/docs` | Swagger |

> 知识库、Trace 代理、JIRA 等 API 尚在规划中；案例管理当前通过 `scripts/init_knowledge.py` 初始化。

## 配置速查

配置类：`langops.core.config.Settings`（环境变量 + `.env`）。

### 必填环境变量

```bash
LLM_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-...
LANGFUSE_SECRET_KEY=sk-...
```

### 常用可选变量

```bash
# LLM
LLM_MODEL=gpt-4

# 数据源
PROMETHEUS_URL=http://localhost:9090
VECTOR_HOST=localhost
VECTOR_PORT=8001

# 阿里云 CMS（可选）
ALIYUN_ACCESS_KEY_ID=
ALIYUN_ACCESS_KEY_SECRET=

# 通知
FEISHU_WEBHOOK=
DINGTALK_WEBHOOK=

# 告警降噪（默认开启，900s 窗口）
ALERT_DEDUP_ENABLED=true
ALERT_DEDUP_WINDOW_SECONDS=900

# 自动修复（默认仅注册计划，不执行真实 kubectl）
REMEDIATION_ENABLED=true
REMEDIATION_EXECUTION_ENABLED=false
```

完整模板：[config/.env.example](../../config/.env.example)

## 常用命令

```bash
# 依赖服务
docker compose up -d

# 知识库初始化
python scripts/init_knowledge.py

# 启动服务
python -m langops.server

# 测试（基线 126 passed）
pytest tests/ -q

# 界面
open http://localhost:8000/ui
open http://localhost:8000/docs
open http://localhost:3000   # Langfuse
```

## 调试技巧

### 告警 + 修复计划

```bash
curl -s -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CPU使用率过高",
    "description": "order-service CPU > 90%",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "kubernetes",
      "system": "prod-cluster",
      "namespace": "production",
      "pod_name": "order-service-xxx"
    }
  }' | jq '.remediation_plan_id, .dedup'

# Dry-run 修复
curl -X POST http://localhost:8000/api/v1/remediation/plan-xxxxxxxx/execute \
  -H "Content-Type: application/json" \
  -d '{"approved_by":"ops-user","confirm":true,"dry_run":true}'
```

### Langfuse Trace

分析成功后从响应 `data.trace_id` 取值，在 Langfuse UI 打开对应 Trace。

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| Langfuse 连接失败 | 服务未启动 | `docker compose up -d` |
| LLM 调用失败 | Key 无效 / 网络 | 检查 `LLM_API_KEY` |
| 向量检索无结果 | 知识库为空 | `python scripts/init_knowledge.py` |
| 修复无法真执行 | 安全默认关闭 | 设 `REMEDIATION_EXECUTION_ENABLED=true` 且命令在白名单内 |
| 重复告警仍调 LLM | 降噪关闭或指纹不同 | 检查 `ALERT_DEDUP_*` 与 `source` 字段 |

## 扩展开发

### 添加采集器

```python
from langops.collectors.base import BaseCollector

class MyCollector(BaseCollector):
    async def collect(self, alert): ...
```

在 `AlertProcessor` 构造时注入，并在 `dependencies.py` 装配。

### 添加 API 路由

1. `src/langops/web/api/` 新建路由模块  
2. `main.py` 中 `include_router`  
3. `tests/unit/test_web/` 补充测试  

## 参考资源

- [系统设计文档](./system-design.md)
- [目录结构说明](./directory-structure.md)
- [AGENTS.md](../../AGENTS.md)
- [README.md](../../README.md)

---

**提示**: 本文为快速参考；实现细节以源码与 Swagger `/docs` 为准。
