# LangOps API Reference

> Base URL: `http://localhost:8000`（默认端口，可通过 `settings.port` 修改）

交互式文档：启动服务后访问 `http://localhost:8000/docs`（Swagger UI）。

---

## 目录

- [通用约定](#通用约定)
- [1. GET / — 服务信息](#1-get--服务信息)
- [2. GET /health — 健康检查](#2-get-health--健康检查)
- [3. GET /metrics — Prometheus 指标](#3-get-metrics--prometheus-指标)
- [4. POST /api/v1/alerts — 告警分析](#4-post-apiv1alerts--告警分析)
- [5. POST /api/v1/webhooks/alertmanager — Prometheus Webhook](#5-post-apiv1webhooksalertmanager--prometheus-webhook)
- [6. GET /api/v1/alerts/dedup/stats — 降噪统计](#6-get-apiv1alertsdedupstats--降噪统计)
- [7. GET /api/v1/alerts/health — 告警模块健康检查](#7-get-apiv1alertshealth--告警模块健康检查)
- [8. POST /api/v1/query — 自然语言查询](#8-post-apiv1query--自然语言查询)
- [9. POST /api/v1/predict — 容量预测](#9-post-apiv1predict--容量预测)
- [10. GET /api/v1/remediation — 修复计划列表](#10-get-apiv1remediation--修复计划列表)
- [11. GET /api/v1/remediation/{plan_id} — 修复计划详情](#11-get-apiv1remediationplan_id--修复计划详情)
- [12. POST /api/v1/remediation/{plan_id}/execute — 执行修复](#12-post-apiv1remediationplan_idexecute--执行修复)
- [13. POST /api/v1/remediation/{plan_id}/reject — 拒绝修复](#13-post-apiv1remediationplan_idreject--拒绝修复)
- [数据模型参考](#数据模型参考)

---

## 通用约定

| 项目 | 说明 |
|------|------|
| Content-Type | `application/json` |
| 认证 | MVP 阶段无认证；生产环境按需添加 |
| 错误格式 | `{"success": false, "error": "..."}` |
| ID 格式 | `alert-{uuid8}`, `plan-{uuid8}`, `trace-{uuid8}` |

---

## 1. GET / — 服务信息

返回服务名称、版本和常用链接。

**curl**

```bash
curl http://localhost:8000/
```

**Response** `200 OK`

```json
{
  "name": "LangOps",
  "version": "0.1.0",
  "description": "AI-powered intelligent operations platform",
  "docs": "/docs",
  "ui": "/ui"
}
```

---

## 2. GET /health — 健康检查

**curl**

```bash
curl http://localhost:8000/health
```

**Response** `200 OK`

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

---

## 3. GET /metrics — Prometheus 指标

返回 Prometheus exposition format 文本，供 Prometheus Server 抓取。

**curl**

```bash
curl -s http://localhost:8000/metrics | head -20
```

**Response** `200 OK` — `text/plain; version=0.0.4`

```
# HELP langops_alerts_received_total Total alerts received
# TYPE langops_alerts_received_total counter
langops_alerts_received_total{severity="critical",category="resource"} 1
# HELP langops_alerts_processed_total Total alerts processed
...
```

---

## 4. POST /api/v1/alerts — 告警分析

核心端点。接收告警后依次执行：降噪判定 → 数据采集 → LLM 根因分析 → 知识库检索 → 修复建议 →（可选）注册修复计划并创建 JIRA 工单。

### Request Body — `AlertCreate`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | ✅ | 告警标题（1–500 字符） |
| `description` | string | ✅ | 告警描述（1–10000 字符） |
| `severity` | string | ✅ | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `category` | string | ✅ | `resource` \| `availability` \| `performance` \| `security` |
| `source` | object | ✅ | 告警来源（见下表） |
| `metric_data` | object | — | 原始指标键值对，提升 RCA 精度 |
| `log_snippets` | string[] | — | 相关日志行 |
| `context` | object | — | 任意补充上下文 |

**`source` 对象**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | `kubernetes` \| `aliyun` \| `prometheus`（Webhook 固定为 `prometheus`） |
| `system` | string | ✅ | 集群名或地域（如 `prod-cluster`、`cn-hangzhou`） |
| `service` | string | — | 服务名 |
| `namespace` | string | — | K8s 命名空间 |
| `pod_name` | string | — | K8s Pod 名称 |
| `instance_id` | string | — | 云实例 ID（ECS/RDS/SLB 的实例标识） |
| `resource_type` | string | — | 云资源类型：`ecs` \| `rds` \| `slb`；K8s 告警可省略 |

### curl 示例

**Kubernetes 告警**

```bash
curl -s -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CPU使用率过高",
    "description": "order-service Pod CPU使用率超过90%，持续5分钟",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "kubernetes",
      "system": "prod-cluster",
      "namespace": "production",
      "pod_name": "order-service-abc123"
    },
    "metric_data": {
      "cpu_usage_percent": 95.5,
      "memory_usage_percent": 78.2
    },
    "log_snippets": [
      "2024-01-15 10:30:45 ERROR High CPU usage detected"
    ],
    "context": {
      "deployment_version": "v2.3.1"
    }
  }' | jq .
```

**阿里云 ECS 告警**

```bash
curl -s -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "ECS CPU使用率过高",
    "description": "ECS 实例 CPU 使用率超过 90%，持续 10 分钟",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "aliyun",
      "system": "cn-hangzhou",
      "instance_id": "i-bp1example0001",
      "resource_type": "ecs",
      "service": "order-service"
    },
    "metric_data": {
      "cpu_usage_percent": 93.2
    }
  }' | jq .
```

**阿里云 RDS 告警**

```bash
curl -s -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "RDS 连接数使用率过高",
    "description": "RDS 实例连接数使用率超过 85%，接近上限",
    "severity": "high",
    "category": "availability",
    "source": {
      "type": "aliyun",
      "system": "cn-hangzhou",
      "instance_id": "rm-bp1example0002",
      "resource_type": "rds",
      "service": "order-db"
    },
    "metric_data": {
      "ConnectionUsage": 87.3,
      "CpuUsage": 45.2,
      "MemoryUsage": 62.1
    }
  }' | jq .
```

### Response — `AnalysisResponse`

**场景一：分析成功**

```json
{
  "success": true,
  "data": {
    "alert_id": "alert-a1b2c3d4",
    "trace_id": "trace-abc123",
    "root_cause": {
      "category": "资源不足",
      "description": "Pod CPU 资源不足，导致性能下降",
      "confidence": 0.92,
      "evidence": ["CPU使用率95%", "无CPU limit配置"],
      "related_metrics": [],
      "impact_analysis": null
    },
    "similar_cases": [],
    "suggestion": {
      "summary": "增加 Pod CPU limit 或扩容",
      "steps": ["检查当前资源配置", "修改 deployment CPU limit"],
      "commands": [
        "kubectl set resources deployment/order-service --limits=cpu=1000m"
      ],
      "risks": [],
      "rollback_plan": null,
      "estimated_time": "10 minutes"
    },
    "impact_prediction": {},
    "processing_time_seconds": 12.34
  },
  "error": null,
  "dedup": {
    "fingerprint": "fp-abc123",
    "action": "process",
    "occurrence_count": 1,
    "window_seconds": 900,
    "message": "First occurrence, proceeding with analysis"
  },
  "remediation_plan_id": "plan-a1b2c3d4"
}
```

**场景二：降噪抑制**

```json
{
  "success": true,
  "data": null,
  "error": null,
  "dedup": {
    "fingerprint": "fp-abc123",
    "action": "suppress",
    "occurrence_count": 3,
    "window_seconds": 900,
    "message": "3rd occurrence within 900s window, suppressed"
  },
  "remediation_plan_id": null
}
```

**场景三：处理失败**

```json
{
  "success": false,
  "data": null,
  "error": "LLM API timeout after 60s",
  "dedup": null,
  "remediation_plan_id": null
}
```

---

## 5. POST /api/v1/webhooks/alertmanager — Prometheus Webhook

Receives Prometheus AlertManager v4 webhook callbacks. Translates the payload into LangOps `AlertCreate` and runs the same AI analysis pipeline as `POST /api/v1/alerts`.

**Use case:** Configure AlertManager to forward firing/resolved alerts to this URL. The adapter normalizes AM's `labels`/`annotations` shape into LangOps's `AlertSource`/`context` fields.

**Configure AlertManager** (`alertmanager.yml`):

```yaml
receivers:
  - name: langops
    webhook_configs:
      - url: 'http://langops:8000/api/v1/webhooks/alertmanager'
        send_resolved: true
```

**Headers:** `Content-Type: application/json`

**Query parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `coalesce` | `Ns` / `Nm` / `Nh` | unset | Time-window aggregation. Example: `?coalesce=5m` buffers alerts for 5 minutes after the last arrival, then processes them as one batch. **Disabled when `workers > 1`.** |

**Request body** — AlertManager v4 payload (see [official schema](https://prometheus.io/docs/alerting/latest/configuration/#webhook_config)). Key fields:

| Field | Required | Description |
|-------|----------|-------------|
| `version` | yes | Always `"4"` |
| `status` | yes | `firing` or `resolved` |
| `alerts` | yes | Non-empty array of alert objects |
| `alerts[].status` | yes | `firing` or `resolved` |
| `alerts[].labels` | yes | Label key-value pairs (alertname, severity, namespace, pod, ...) |
| `alerts[].annotations` | no | Free-form annotation values (summary, description, message) |
| `alerts[].startsAt` | yes | ISO 8601 timestamp |
| `alerts[].endsAt` | no | ISO 8601 timestamp (zero when still firing) |

**Response 200 OK** (sync):

```json
{
  "success": true,
  "received": 3,
  "results": [
    {
      "alert_id": "alert-a1b2c3d4",
      "success": true,
      "data": { /* AnalysisResult */ },
      "error": null,
      "dedup": { "fingerprint": "fp-abc", "action": "process", "occurrence_count": 1 },
      "remediation_plan_id": "plan-..."
    }
  ],
  "audit": { "coalesced": false }
}
```

**Response 200 OK** (coalesced): `audit.coalesced: true`, `results: []`. Processing happens after the window expires.

**Errors:**

| Status | When |
|--------|------|
| 422 | Payload > `WEBHOOK_MAX_PAYLOAD_BYTES` (default 1MB) |
| 422 | `len(alerts) > WEBHOOK_MAX_ALERTS_PER_BATCH` (default 100) |
| 422 | Invalid JSON or AM schema mismatch |
| 422 | Invalid `coalesce` format |

**Configuration:**

| Env var | Default | Purpose |
|---------|---------|---------|
| `WEBHOOK_MAX_PAYLOAD_BYTES` | `1048576` | Reject oversized bodies (DoS guard) |
| `WEBHOOK_MAX_ALERTS_PER_BATCH` | `100` | Reject oversized batches |
| `WEBHOOK_AUDIT_LOG_PATH` | `logs/langops-audit.log` | Audit log file (rotated daily) |
| `WEBHOOK_AUDIT_LOG_RETENTION_DAYS` | `7` | Auto-cleanup window |
| `WEBHOOK_COALESCE_MAX_BUFFERED_ALERTS` | `500` | Per-source buffer cap |

**Troubleshooting:**

- **`?coalesce=` ignored silently?** Check `workers` setting. Multi-worker deployment disables coalesce (in-process buffer cannot coordinate). Set `workers=1` or remove the query param.
- **AlertManager keeps retrying (non-2xx)?** Check LangOps reachability and audit log at `logs/langops-audit.log` for `webhook.received` / `alert.processed` decisions.
- **Audit log empty?** Verify `WEBHOOK_AUDIT_LOG_PATH` is writable; the directory is created automatically.
- **`webhook_source` vs `source.type`**: audit logs use `webhook_source=alertmanager`. Domain `AlertSource.type` is `prometheus`. Both are present in logs; do not conflate.

---

## 6. GET /api/v1/alerts/dedup/stats — 降噪统计

返回当前活跃的告警分组数及各分组出现次数。

**curl**

```bash
curl http://localhost:8000/api/v1/alerts/dedup/stats
```

**Response** `200 OK`

```json
{
  "active_groups": 3,
  "groups": {
    "fp-abc123": 5,
    "fp-def456": 2,
    "fp-ghi789": 1
  }
}
```

---

## 7. GET /api/v1/alerts/health — 告警模块健康检查

**curl**

```bash
curl http://localhost:8000/api/v1/alerts/health
```

**Response** `200 OK`

```json
{
  "status": "healthy",
  "service": "alerts"
}
```

---

## 8. POST /api/v1/query — 自然语言查询

将自然语言问题转换为 PromQL 查询并执行，返回 LLM 解读结果。

### Request Body — `NLQueryRequest`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 自然语言问题（≥1 字符） |

### curl

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "过去1小时哪些 Pod CPU 使用率最高？"}' | jq .
```

### Response — `NLQueryResponse`

```json
{
  "success": true,
  "data": {
    "answer": "过去1小时内，order-service-abc123 的 CPU 使用率最高，平均达到 95.5%。",
    "promql": "topk(5, rate(container_cpu_usage_seconds_total[1h]))",
    "explanation": "按 namespace 和 pod 维度聚合 CPU 使用率，取 Top 5",
    "time_range": "1h",
    "data": [
      {"pod": "order-service-abc123", "cpu_percent": 95.5},
      {"pod": "payment-svc-xyz", "cpu_percent": 72.3}
    ]
  },
  "error": null
}
```

---

## 9. POST /api/v1/predict — 容量预测

采集历史指标并预测未来趋势，用于预测性运维。

### Request Body — `PredictRequest`

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `resource_type` | string | — | `"kubernetes"` | `kubernetes` \| `ecs` \| `rds` |
| `system` | string | — | `"prod-cluster"` | 集群名（K8s）或阿里云地域（如 `cn-hangzhou`） |
| `namespace` | string | — | `null` | K8s 命名空间 |
| `pod_name` | string | — | `null` | K8s Pod 名称 |
| `instance_id` | string | — | `null` | 云实例 ID |
| `service` | string | — | `null` | 服务名 |
| `horizon_hours` | int | — | `24` | 预测时长（1–168 小时） |
| `thresholds` | object | — | `{"cpu":0.9,"memory":0.9}` | 各指标风险阈值 |

### curl

**Kubernetes Pod 预测**

```bash
curl -s -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "kubernetes",
    "namespace": "production",
    "pod_name": "order-service-abc123",
    "horizon_hours": 24
  }' | jq .
```

**阿里云 ECS 预测**

```bash
curl -s -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "ecs",
    "system": "cn-hangzhou",
    "instance_id": "i-bp1example0001",
    "horizon_hours": 48
  }' | jq .
```

**阿里云 RDS 预测**

```bash
curl -s -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "rds",
    "system": "cn-hangzhou",
    "instance_id": "rm-bp1example0002",
    "service": "order-db",
    "horizon_hours": 24,
    "thresholds": {"ConnectionUsage": 0.8, "CpuUsage": 0.85}
  }' | jq .
```

### Response — `PredictResponse`

```json
{
  "success": true,
  "data": {
    "affected_service": "order-service",
    "horizon_hours": 24,
    "overall_risk": "high",
    "forecasts": [
      {
        "metric": "cpu_usage_percent",
        "current": 95.5,
        "trend": "rising",
        "slope_per_hour": 1.2,
        "forecast_value": 99.8,
        "risk_level": "critical",
        "summary": "CPU 使用率持续上升，预计 4 小时内达到 100%"
      }
    ],
    "recommendation": "建议立即扩容 Pod CPU limit 至 2000m，或增加副本数",
    "confidence": 0.85
  },
  "error": null
}
```

---

## 10. GET /api/v1/remediation — 修复计划列表

返回所有待审批的修复计划。

**curl**

```bash
curl -s http://localhost:8000/api/v1/remediation | jq .
```

**Response** `200 OK`

```json
[
  {
    "plan_id": "plan-a1b2c3d4",
    "alert_id": "alert-a1b2c3d4",
    "trace_id": "trace-abc123",
    "summary": "增加 Pod CPU limit 或扩容",
    "commands": [
      "kubectl set resources deployment/order-service --limits=cpu=1000m"
    ],
    "risks": [],
    "rollback_plan": null,
    "risk_level": "low",
    "status": "pending_approval",
    "created_at": "2024-01-15T10:30:00Z",
    "approved_by": null,
    "execution_output": null,
    "jira_issue_key": "ALERTS-42"
  }
]
```

---

## 11. GET /api/v1/remediation/{plan_id} — 修复计划详情

**curl**

```bash
curl -s http://localhost:8000/api/v1/remediation/plan-a1b2c3d4 | jq .
```

**Response** `200 OK` — 同上单个 `RemediationPlan` 对象。

**Response** `404 Not Found`

```json
{"detail": "Plan not found"}
```

---

## 12. POST /api/v1/remediation/{plan_id}/execute — 执行修复

审批并执行（或 dry-run）修复计划。默认 `dry_run=true`，不会执行真实命令。

### Request Body — `RemediationExecuteRequest`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `approved_by` | string | ✅ | 审批人标识 |
| `confirm` | bool | ✅ | 必须为 `true` 才能继续 |
| `dry_run` | bool | — | `true`（默认）仅模拟；`false` 执行真实命令 |

### curl

**Dry-run（推荐）**

```bash
curl -s -X POST http://localhost:8000/api/v1/remediation/plan-a1b2c3d4/execute \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "ops-user",
    "confirm": true,
    "dry_run": true
  }' | jq .
```

**真实执行**（需 `REMEDIATION_EXECUTION_ENABLED=true`）

```bash
curl -s -X POST http://localhost:8000/api/v1/remediation/plan-a1b2c3d4/execute \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "ops-user",
    "confirm": true,
    "dry_run": false
  }' | jq .
```

### Response — `RemediationExecuteResponse`

```json
{
  "success": true,
  "plan": {
    "plan_id": "plan-a1b2c3d4",
    "alert_id": "alert-a1b2c3d4",
    "trace_id": "trace-abc123",
    "summary": "增加 Pod CPU limit 或扩容",
    "commands": [
      "kubectl set resources deployment/order-service --limits=cpu=1000m"
    ],
    "risks": [],
    "rollback_plan": null,
    "risk_level": "low",
    "status": "dry_run",
    "created_at": "2024-01-15T10:30:00Z",
    "approved_by": "ops-user",
    "execution_output": "kubectl executed (dry-run): set resources deployment/order-service --limits=cpu=1000m",
    "jira_issue_key": "ALERTS-42"
  },
  "error": null
}
```

---

## 13. POST /api/v1/remediation/{plan_id}/reject — 拒绝修复

### Request Body — `RemediationRejectRequest`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rejected_by` | string | ✅ | 拒绝人标识 |
| `reason` | string | — | 拒绝原因 |

### curl

```bash
curl -s -X POST http://localhost:8000/api/v1/remediation/plan-a1b2c3d4/reject \
  -H "Content-Type: application/json" \
  -d '{
    "rejected_by": "ops-lead",
    "reason": "需要在维护窗口执行"
  }' | jq .
```

### Response — `RemediationExecuteResponse`

```json
{
  "success": true,
  "plan": {
    "plan_id": "plan-a1b2c3d4",
    "alert_id": "alert-a1b2c3d4",
    "trace_id": "trace-abc123",
    "summary": "增加 Pod CPU limit 或扩容",
    "commands": [],
    "risks": [],
    "rollback_plan": null,
    "risk_level": "low",
    "status": "rejected",
    "created_at": "2024-01-15T10:30:00Z",
    "approved_by": "ops-lead",
    "execution_output": "Rejected: 需要在维护窗口执行",
    "jira_issue_key": "ALERTS-42"
  },
  "error": null
}
```

---

## 数据模型参考

### AlertSeverity

| 值 | 说明 |
|----|------|
| `critical` | 紧急 — 服务中断或数据丢失风险 |
| `high` | 高 — 性能严重下降 |
| `medium` | 中 — 资源预警（`warning` 会自动映射为 `medium`） |
| `low` | 低 — 信息性预警 |
| `info` | 信息 — 仅记录 |

### AlertCategory

| 值 | 说明 |
|----|------|
| `resource` | 资源（CPU、内存、磁盘） |
| `availability` | 可用性（Pod 重启、实例宕机） |
| `performance` | 性能（延迟、错误率） |
| `security` | 安全（异常访问、漏洞） |

### RemediationStatus

| 值 | 说明 |
|----|------|
| `pending_approval` | 等待审批 |
| `rejected` | 已拒绝 |
| `dry_run` | 模拟执行完成 |
| `executed` | 已真实执行 |
| `failed` | 执行失败 |

### DedupInfo.action

| 值 | 说明 |
|----|------|
| `process` | 通过降噪检查，正常进入分析流水线 |
| `suppress` | 被降噪抑制，跳过 LLM 分析 |

---

**提示**：启动服务后访问 `http://localhost:8000/docs` 可获取自动生成的交互式 Swagger 文档，本文档与其保持同步。
