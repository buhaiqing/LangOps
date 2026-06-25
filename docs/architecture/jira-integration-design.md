# JIRA 工单集成方案设计

> **状态**: 规划中 | **优先级**: P1 | **依赖**: 修复审批流程（已完成）

---

## 1. 设计目标

将 LangOps 的告警分析与修复审批流程与 JIRA 工单系统打通，实现：

1. **告警分析完成后自动创建 JIRA 工单**，关联 `trace_id` 和 `remediation_plan_id`
2. **修复计划状态变更时同步 JIRA 工单状态**
3. **（可选）JIRA 工单状态变化回写 LangOps**
4. **（可选）JIRA 作为通知通道**，与飞书/钉钉并列

---

## 2. 现有对接基础

| 组件 | 位置 | 与 JIRA 集成的对接方式 |
|------|------|----------------------|
| AlertProcessor | `agent/alert_processor.py:50` | `process()` 完成后触发 JIRA 建单 |
| RemediationRegistry | `services/remediation_executor.py:58` | 创建/更新计划时更新 JIRA 工单 |
| NotificationService | `services/notification.py:13` | JIRA 作为新通知通道扩展 |
| 配置层 | `core/config.py:108` | 新增 `JiraSettings` 子配置 |
| 模型层 | `models/remediation.py:19` | `RemediationPlan` 新增 `jira_issue_key` 字段 |
| FastAPI DI | `web/dependencies.py:99` | 新增 `get_jira_service()` 依赖注入 |

---

## 3. 分阶段实现方案

### Phase A：单向建单（MVP，约 1-2 天）

**核心流程：**

```
AlertProcessor.process() 完成
        │
        ▼
┌─────────────────────────────┐
│ 检查 JIRA 配置是否启用       │
│ JiraSettings.enabled=false  │──→ 跳过
└──────────┬──────────────────┘
           ▼ 启用
┌─────────────────────────────┐
│ JiraService.create_ticket() │
│   - project: ALERTS         │
│   - summary: 告警标题       │
│   - description: 根因+建议  │
│   - labels: [severity]      │
│   - custom fields:          │
│     * trace_id              │
│     * remediation_plan_id   │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│ 回写 RemediationPlan        │
│ plan.jira_issue_key = KEY-1 │
└─────────────────────────────┘
```

**文件变更：**

| 文件 | 变更 |
|------|------|
| `core/config.py` | 新增 `JiraSettings`（url、username、api_token、project、enabled） |
| `models/remediation.py` | `RemediationPlan` 新增 `jira_issue_key: str \| None` |
| `services/jira_integration.py` | 新建：`JiraService` 类 |
| `web/dependencies.py` | 新增 `get_jira_service()` |
| `agent/alert_processor.py` | `process()` 末尾调用 `jira_service.create_ticket()` |
| `.env.example` | 新增 `JIRA_URL`、`JIRA_USERNAME`、`JIRA_API_TOKEN`、`JIRA_PROJECT` 等 |

### Phase B：状态同步（约 2-3 天）

**双向同步：**

```
LangOps → JIRA（出站）
  plan.status:
    pending_approval → 待审批
    dry_run          → 验证中
    executed         → 已执行
    rejected         → 已拒绝
    failed           → 执行失败

JIRA → LangOps（入站，通过 Webhook）
  JIRA 工单转「关闭」→ 仅日志记录（LangOps 不自动变更修复计划）
  JIRA 工单备注更新 → 可选写入 RemediationPlan 的备注字段
```

**文件变更：**

| 文件 | 变更 |
|------|------|
| `services/remediation_executor.py` | `approve_and_execute()`、`reject()` 内调用 `jira_service.sync_status()` |
| `services/jira_integration.py` | 新增 `sync_status()`、`add_comment()` 方法 |
| `web/api/remediation.py` | 可选：新增 JIRA webhook 接收端点 `POST /api/v1/webhooks/jira` |
| `core/config.py` | 可选：`JIRA_WEBHOOK_SECRET` |

### Phase C：JIRA 通知通道（约 1 天）

在 `NotificationService` 中新增 JIRA 作为通知通道，用于将分析摘要推送至 JIRA 工单（comment）或将关键告警直接建单到特定项目。

---

## 4. 核心接口设计

### 4.1 JiraService

```python
class JiraService:
    """JIRA integration service."""

    def __init__(
        self,
        url: str,
        username: str,
        api_token: str,
        project: str,
        enabled: bool = True,
    ) -> None:
        ...

    async def create_ticket(
        self,
        *,
        summary: str,
        description: str,
        alert_id: str,
        severity: str,
        trace_id: str,
        remediation_plan_id: str | None = None,
        labels: list[str] | None = None,
    ) -> str:
        """Create a JIRA issue and return the issue key (e.g. 'ALERTS-42')."""
        ...

    async def sync_status(
        self,
        issue_key: str,
        status: RemediationStatus,
    ) -> bool:
        """Sync LangOps remediation status to JIRA issue."""
        ...

    async def add_comment(
        self,
        issue_key: str,
        comment: str,
    ) -> bool:
        """Add a comment to an existing JIRA issue."""
        ...

    async def close(self) -> None:
        """Release HTTP session."""
        ...
```

### 4.2 配置模型

```python
class JiraSettings(BaseSettings):
    """JIRA integration configuration."""

    model_config = SettingsConfigDict(env_prefix="JIRA_")

    url: str = Field(default="", description="JIRA base URL")
    username: str = Field(default="", description="JIRA username or email")
    api_token: str = Field(default="", description="JIRA API token")
    project: str = Field(default="ALERTS", description="Project key for new issues")
    enabled: bool = Field(default=False, description="Enable JIRA integration")
    timeout: int = Field(default=10, description="HTTP timeout in seconds")
    webhook_secret: str | None = Field(default=None, description="Webhook verification secret")
```

### 4.3 数据模型变更

```python
class RemediationPlan(BaseModel):
    """Existing model — add jira_issue_key field."""

    ...
    jira_issue_key: str | None = Field(
        default=None,
        description="Linked JIRA issue key (e.g. ALERTS-42)",
    )
```

---

## 5. JIRA 工单模板

### Issue Type: `Task`

| 字段 | 内容 |
|------|------|
| **Summary** | `[critical] Pod CPU 使用率过高 — order-service` |
| **Description** | 见下方模板 |
| **Labels** | `langops`, `{severity}`, `{category}` |
| **Priority** | 映射：critical→Highest, high→High, medium→Medium, low→Low |

**Description 模板：**

```
h2. 告警信息

| 字段 | 值 |
|------|-----|
| 告警 ID | {alert_id} |
| 严重程度 | {severity} |
| 类别 | {category} |
| 来源类型 | {source_type} |
| 集群 | {source_system} |
| 资源 | {pod_name / instance_id} |

h2. 根因分析

{root_cause_description}

*置信度*: {confidence}

h2. 关键证据

{key_evidence}

h2. 修复建议

{remediation_summary}

*风险等级*: {risk_level}

{remediation_steps}

h2. 关联链接

- Langfuse Trace: [链接|{langfuse_url}/trace/{trace_id}]
- LangOps API: /api/v1/remediation/{plan_id}
```

---

## 6. 依赖与风险

| 类型 | 说明 | 缓解措施 |
|------|------|---------|
| **依赖** | 需要 JIRA 管理员创建 API Token | 文档中写清楚所需权限（Write issue, Read project） |
| **风险** | JIRA API 限流 | `JiraService` 内部使用 `tenacity` 退避重试；`create_ticket()` 失败不阻断主流程（打日志降级） |
| **风险** | 网络不通 / JIRA 不可用 | `enabled=false` 默认关闭；HTTP 超时默认 10s；所有调用 `try/except` 不冒泡 |
| **安全** | API Token 泄露 | 配置项通过 `.env` 加载，禁止硬编码；日志中 mask 后半段 token |

---

## 7. 测试策略

| 层级 | 内容 | mock 策略 |
|------|------|----------|
| 单元测试 | `JiraService.create_ticket()` 参数构造、返回解析 | mock `aiohttp.ClientSession.post` |
| 单元测试 | 配置 disabled 时跳过 | `jira.enabled=False` 验证不调用 HTTP |
| 单元测试 | 网络异常降级 | mock 抛出 `aiohttp.ClientError`，验证不抛异常 |
| 集成测试 | `AlertProcessor` + mock `JiraService` | 验证 `process()` 完成后调用 `create_ticket()` |
| 集成测试 | `RemediationRegistry` + mock `JiraService` | 验证执行/拒绝后调用 `sync_status()` |

---

## 8. 实施顺序建议

```
Phase A（单向建单）
  ├─ core/config.py: JiraSettings
  ├─ models/remediation.py: jira_issue_key
  ├─ services/jira_integration.py: JiraService (create_ticket)
  ├─ web/dependencies.py: get_jira_service
  ├─ agent/alert_processor.py: 触发建单
  ├─ tests/unit/test_services/test_jira_integration.py
  ├─ config/.env.example: JIRA 配置项
  └─ docs: 更新 system-design.md 状态表

Phase B（状态同步）
  ├─ services/jira_integration.py: sync_status, add_comment
  ├─ services/remediation_executor.py: 同步状态
  ├─ tests: 状态同步测试
  └─ docs: 更新系统设计

Phase C（JIRA 通知通道）
  ├─ services/notification.py: 扩展 _format_and_send
  └─ tests: 通知测试
```

---

**整体估算**: Phase A ~1.5 天，Phase B ~2 天，Phase C ~0.5 天
**关键原则**: 所有 JIRA 调用都是"尽力而为"——不因 JIRA 不可用而阻塞告警分析主流程。
