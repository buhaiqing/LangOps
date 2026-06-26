# Aliyun CMS Webhook Adapter 设计

> **Status:** Draft
> **Author:** 基于上一轮 Prometheus AlertManager Spec + §11 约束推导
> **Version:** 2026-06-26

## 1. Motivation & Scope

### 1.1 背景

阿里云云监控（Cloud Monitor Service, CMS）支持两种告警类型：
1. **阈值告警**：基于指标阈值的触发，可通过"报警回调"推送至 HTTP/HTTPS URL
2. **系统事件**：订阅 ECS/RDS/Redis 等产品的系统事件，可通过"推送渠道"推送至 Webhook

两者的 Payload 结构完全不同。本 Spec 要求在同一端点同时支持两种格式。

### 1.2 目标

- 新增 `POST /api/v1/webhooks/aliyun/cms` 端点
- 接收 CMS 阈值告警回调 → 映射为 `AlertCreate` → 走标准流水线
- 接收 CMS 系统事件回调 → 映射为 `AlertCreate` → 走标准流水线
- 静默处理 `alertState=OK` / `alertStatus=RESOLVED` 的恢复通知（不做误报处理，仅打日志）
- 复用 §11 定义的 5 个接口件

### 1.3 非目标

- 不处理 CMS FORM 格式（仅支持 JSON；CMS 控制台可选择 JSON/FORM，声明支持 JSON 即可）
- 不主动拉取 CMS 指标（已有 `AliyunCmsCollector` 负责指标采集；webhook 仅做告警映射）
- 不修改 `AlertCreate` 模型（见 §11.6 评估，无需扩展）

## 2. CMS Payload 格式

### 2.1 阈值告警（Threshold Alert）

CMS 配置"报警回调"时发送的 POST JSON：

```json
{
  "alertName": "ECS_CPU_utilization",
  "alertState": "ALERT",
  "curValue": "92.5",
  "dimensions": "{\"instanceId\":\"i-bp1234567890\",\"userId\":\"1234567890\"}",
  "expression": "Average(CPUUtilization)>85",
  "instanceName": "prod-web-01",
  "metricName": "CPUUtilization",
  "metricProject": "acs_ecs_dashboard",
  "namespace": "acs_ecs_dashboard",
  "preName": "ECS实例CPU使用率过高",
  "regionId": "cn-hangzhou",
  "ruleId": "rule_12345",
  "timestamp": 1716091800000,
  "triggerLevel": "WARN",
  "userId": "1234567890"
}
```

关键字段：
- `alertName`: 告警规则名称
- `alertState`: `ALERT` | `OK` | `INSUFFICIENT_DATA`
- `dimensions`: JSON 编码的维度字符串（含 `instanceId`）
- `triggerLevel`: `CRITICAL` | `WARN` | `INFO`
- `preName`: 中文展示名（最合适做 title）
- `namespace`: `acs_ecs_dashboard` / `acs_rds_dashboard` / `acs_slb_dashboard` 等

### 2.2 系统事件（System Event）

CMS 订阅策略推送时发送的 POST JSON：

```json
{
  "userInfo": { ... },
  "subscription": { ... },
  "batchId": "testbatchid",
  "alert": {
    "alertStatus": "TRIGGERED",
    "source": "SYS_EVENT",
    "eventName": "CloudAssistant:FirstHeartbeat",
    "arn": "acs:ecs:cn-hangzhou:testuser:instance/i-testhost",
    "timestamp": 1704780333000,
    "severity": "INFO",
    "product": "ECS",
    "eventRawContent": "{}",
    "dedupId": "test-id",
    "meta": {
      "sysEventMeta": {
        "regionId": "cn-hangzhou",
        "instanceName": "i-testhost",
        "product": "ECS",
        "level": "INFO",
        "name": "CloudAssistant:FirstHeartbeat",
        "eventTime": "20240109T140533.642+0800"
      }
    }
  },
  "severity": "INFO",
  "strategyName": "eventwebhook",
  "userId": "test",
  "time": 1704780333000
}
```

关键字段：
- `alert.alertStatus`: `TRIGGERED` | `RESOLVED`
- `alert.eventName`: 事件名
- `alert.product`: `ECS` / `RDS` / `Redis` / `SLB` 等
- `alert.arn`: 资源 ARN
- `alert.meta.sysEventMeta.regionId`: 地域
- `alert.meta.sysEventMeta.level`: `CRITICAL` | `WARN` | `INFO`

## 3. 数据模型

### 3.1 `AliyunCmsAlertPayload`

新建 `src/langops/models/cms.py`：

```python
class AliyunCmsAlertPayload(BaseModel):
    """CMS webhook payload — covers both threshold alert and system event formats.

    CMS adds fields regularly (documented guarantee), so ``extra='ignore'``
    safely absorbs unknown fields without breaking validation.
    """

    model_config = ConfigDict(extra="ignore")

    # Threshold alert fields
    alertName: str | None = None
    alertState: str | None = None
    curValue: str | None = None
    dimensions: str | None = None       # JSON string: {"instanceId":"i-xxx"}
    expression: str | None = None
    instanceName: str | None = None
    metricName: str | None = None
    metricProject: str | None = None
    namespace: str | None = None
    preName: str | None = None
    regionId: str | None = None
    ruleId: str | None = None
    triggerLevel: str | None = None

    # System event fields
    alert: dict[str, Any] | None = None  # nested alert object

    # Common / fallback
    timestamp: int | None = None
    time: int | None = None
```

### 3.2 类型检测

Adapter 通过检查 `alert` 字段是否为 dict 来判断 payload 类型：

| 条件 | 类型 |
|------|------|
| `payload.alert` is a dict with keys | 系统事件 |
| otherwise | 阈值告警 |

## 4. Adapter 映射规则

### 4.1 阈值告警映射

| `AlertCreate` 字段 | 来源 | 备注 |
|-------------------|------|------|
| `title` | `preName` → `alertName` → `"CMS alert"` | 截断 500 字符 |
| `description` | `expression` (含 curValue) → `metricName` | 截断 10000 字符 |
| `severity` | `triggerLevel` 映射 | `CRITICAL`→critical, `WARN`→medium, 其他→info |
| `category` | 基于 `metricName` + `namespace` 推断 | 同 AM 的 keyword 模式匹配 |
| `source.type` | `"aliyun"` | 固定 |
| `source.system` | `regionId` | 例 `"cn-hangzhou"` |
| `source.instance_id` | `dimensions` 中 parse `instanceId` | JSON decode |
| `source.resource_type` | `namespace` 提取 | `acs_ecs_dashboard` → `ecs` |
| `context` | 原始字段子集 | `alertState`, `alertName`, `metricName`, `curValue`, `ruleId` 等 |

### 4.2 系统事件映射

| `AlertCreate` 字段 | 来源 | 备注 |
|-------------------|------|------|
| `title` | `alert.eventName` → `alert.meta.sysEventMeta.name` | 截断 500 |
| `description` | `alert.eventName` + `alert.alertStatus` + product | 截断 10000 |
| `severity` | `alert.severity` / `alert.meta.sysEventMeta.level` | 同阈值映射 |
| `category` | 基于 `alert.product` + `alert.eventName` 推断 | |
| `source.type` | `"aliyun"` | |
| `source.system` | `alert.meta.sysEventMeta.regionId` | |
| `source.instance_id` | 从 `alert.arn` 解析 | parse `:instance/i-xxx` 后缀 |
| `source.resource_type` | `alert.product` 小写 | `ECS` → `ecs` |
| `context` | 原始 `alert` 字段子集 | `dedupId`, `eventType`, `traceId`, `alertStatus` 等 |

### 4.3 恢复通知处理

- **阈值告警** `alertState=OK` / `INSUFFICIENT_DATA`：静默丢弃，打一条 INFO 日志，不报警
- **系统事件** `alertStatus=RESOLVED`：同上
- 这样设计是为了避免 CMS 恢复通知触发 LangOps 重新分析（恢复时通常不需要 RCA）

### 4.4 降级路径（Best-effort）

所有映射步骤中各字段缺失都不会抛异常（`get()` / `or` 兜底），最终至少返回一个有 `title`, `description`, `severity`, `category`, `source` 的 `AlertCreate`。这符合 §4.5 的 guidelines。

## 5. 端点设计

### 5.1 URL

```
POST /api/v1/webhooks/aliyun/cms
```

遵循 §11.4 命名约定。

### 5.2 参数

| 参数 | 位置 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|------|
| `coalesce` | query | string | 否 | — | 启动时间窗口聚合，同 AlertManager（§4.4） |

### 5.3 处理流程

```
CMS POST → FastAPI
  │
  ├─ 1. Content-Length 预检查
  ├─ 2. 读取 body + 大小检查
  ├─ 3. Pydantic 验证 (AliyunCmsAlertPayload)
  ├─ 4. Adapter → list[AlertCreate] (to_alert_creates)
  │      └─ 逐元素检查 alertState/alertStatus → 恢复通知静默丢弃
  ├─ 5. Audit: webhook.received
  ├─ 6. Metrics: webhook_alerts_received_total
  ├─ 7. [coalesce] 进入 CoalesceBuffer
  │      └─ key = "aliyun_cms" (webhook_source)
  └─ 8. [default] gather → process_one_alert
       └─ 返回 WebhookBatchResponse
```

### 5.4 请求/响应示例

**阈值告警请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/aliyun/cms" \
  -H "Content-Type: application/json" \
  -d '{
    "alertName": "ECS_CPU_utilization",
    "alertState": "ALERT",
    "curValue": "92.5",
    "dimensions": "{\"instanceId\":\"i-bp1234567890\"}",
    "expression": "Average(CPUUtilization)>85",
    "namespace": "acs_ecs_dashboard",
    "preName": "ECS实例CPU使用率过高",
    "regionId": "cn-hangzhou",
    "triggerLevel": "WARN"
  }'
```

**成功响应：**

```json
{
  "success": true,
  "received": 1,
  "results": [
    {
      "alert_id": "alert-abc123",
      "success": true,
      "data": { ... },
      "remediation_plan_id": null
    }
  ],
  "audit": {}
}
```

**系统事件请求：**

```bash
curl -X POST "http://localhost:8000/api/v1/webhooks/aliyun/cms" \
  -H "Content-Type: application/json" \
  -d '{
    "alert": {
      "alertStatus": "TRIGGERED",
      "eventName": "InstanceStatusChange",
      "arn": "acs:ecs:cn-hangzhou:user:instance/i-bp123",
      "severity": "WARN",
      "product": "ECS",
      "meta": {
        "sysEventMeta": {
          "regionId": "cn-hangzhou",
          "level": "WARN",
          "name": "因实例错误实例重启开始"
        }
      }
    }
  }'
```

## 6. §11 5 个接口件复用情况

| 接口件 | 文件 | 复用方式 |
|--------|------|----------|
| `process_one_alert` | `web/_alert_flow.py` | 直接调用，传入 `webhook_source="aliyun_cms"` |
| `CoalesceBuffer` | `web/_coalesce.py` | 同一 buffer 实例，source key 为 `"aliyun_cms"` |
| `AuditLogger` | `core/audit.py` | 同一 logger 实例 |
| `WebhookBatchResponse` / metrics | `models/webhook.py` / `web/metrics.py` | 同一 response schema + 同一 metrics（按 `webhook_source` 区分） |
| `WebhookSettings` | `core/config.py` | 同一配置，无需新增 CMS 专属配置项 |

**不需要新增的部分：**
- 不需要新的 dependencies（复用已有的 `get_audit_logger`, `get_coalesce_buffer`）
- 不需要新的 config 项（复用 `WebhookSettings`）
- 不需要新的 metrics（已有 `webhook_received_total`, `webhook_duration_seconds`, `webhook_alerts_received_total` 按 `webhook_source` 标签区分）
- 不需要新的 response model（`WebhookBatchResponse` 是 source-agnostic 的）

## 7. AlertCreate §11.6 评估

| 候选扩展 | 评估 | 结论 |
|----------|------|------|
| `source.resource_id` | CMS 有 `ARN` 但 `instance_id` 足够标识资源 | 放 `context` 即可 |
| `source.region` | `source.system` 已承担 region 角色 | 无需新增 |
| `alertmanager_status` 类型化 | CMS 用 `alertState` / `alertStatus`，放 `context` | 无需新增 |

**结论：`AlertCreate` 无需扩展。**

## 8. 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `src/langops/models/cms.py` | `AliyunCmsAlertPayload` Pydantic 模型 |
| 修改 | `src/langops/models/__init__.py` | 导出新模型 |
| 新增 | `src/langops/adapters/aliyun_cms.py` | `AliyunCmsAdapter` 映射逻辑 |
| 修改 | `src/langops/web/api/webhooks.py` | 新增 `@router.post("/aliyun/cms")` 端点 |
| 修改 | `src/langops/web/main.py` | 无变化（已有 webhooks router） |
| 修改 | `src/langops/web/metrics.py` | 无变化（已有 webhook metrics） |
| 修改 | `.env.example` | 无变化（复用 WebhookSettings） |
| 修改 | `docs/api-reference.md` | 新增 CMS webhook 端点文档 |
| 新增 | `tests/unit/test_models/test_cms_payload.py` | 模型单元测试 |
| 新增 | `tests/unit/test_adapters/test_aliyun_cms_adapter.py` | Adapter 单元测试 |
| 新增 | `tests/integration/test_webhook_aliyun_cms.py` | 集成测试 |

## 9. 测试策略

### 9.1 单元测试

**模型（`test_cms_payload.py`）**：
- 有效阈值告警 payload 解析
- 有效系统事件 payload 解析
- 额外字段被忽略（`extra="ignore"`）
- 空 body 拒绝（min_length? — 使用 model_validate_json 时有 required 字段 → 默认均 optional，因此不会验证失败，但 adapter 会处理空 alerts 情况）

**Adapter（`test_aliyun_cms_adapter.py`）**：
- 阈值告警 → AlertCreate 映射（验证 title, description, severity, source 均正确）
- 系统事件 → AlertCreate 映射
- `alertState=OK` 恢复通知 → 返回空列表
- `alertStatus=RESOLVED` 恢复通知 → 返回空列表
- `dimensions` JSON 解析失败时的降级（缺 instanceId → 空字符串）
- ARN 解析失败时的降级
- 缺少 `preName` 时的 title 降级链
- Unicode 处理

### 9.2 集成测试（`test_webhook_aliyun_cms.py`）

- 有效阈值告警 → 200 + 完整的响应
- 有效系统事件 → 200 + 完整的响应
- 恢复通知（OK/RESOLVED）→ 200 + results 为空
- 超大 payload → 422
- 无效 payload → 422
- `?coalesce=5m` → 返回 coalesced 响应
- 并发请求

## 10. 未解决问题

1. **CMS 控制台自定义字段**：CMS 允许用户在 Webhook 中添加自定义 Header/Param。无影响——仅对 URL 和 header 做处理。
2. **多 Product 订阅**：CMS 系统事件可一次订阅多个产品（ECS, RDS, Redis 等）。本适配器处理 product 字段自动识别 resource_type。
3. **`dimensions` 格式变种**：阈值告警的 `dimensions` 也可能是 URL 查询格式（`userId=xxx,instanceId=xxx`）而非 JSON 字符串。当前先 JSON parse，失败再回退到 URL parse。
4. **ARN 格式变种**：不同产品的 ARN 格式可能不同。当前处理 `:instance/` 和 `:resource/` 两种后缀。

---

**版本**: 2026-06-26
**下一阶段**: 批准后进入 TDD 实施