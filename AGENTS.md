# LangOps — AI Agent 开发规范

> **强制执行**：在本仓库中编写、修改或审查代码的 AI Agent 与人类开发者，必须严格遵守本文档。  
> 与实现计划冲突时，以 [MVP 实现计划](docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md) 的具体步骤为准；计划未覆盖处，以本文档为准。

## 项目概览

| 项 | 说明 |
|---|---|
| **目标** | AI 智能化运维平台 MVP：告警接收 → 数据采集 → LLM 根因分析 → 结果输出 |
| **技术栈** | Python 3.11+、FastAPI、Langfuse、OpenAI API、ChromaDB、Redis、Docker Compose |
| **架构** | FastAPI 后端 + 模块化 Agent；Prometheus / 阿里云 CMS 数据源；Langfuse 全链路追踪 |
| **包名** | `langops`（源码在 `src/`，通过 `python -m langops.server` 启动） |

**参考文档**

- [系统设计](docs/architecture/system-design.md)
- [目录结构](docs/architecture/directory-structure.md)
- [快速参考](docs/architecture/quick-reference.md)
- [MVP 实现计划](docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md)

---

## 一、开发规范

### 1.1 设计原则

1. **YAGNI**：不实现计划外功能；不提前抽象。
2. **单一职责**：每个模块只负责一个功能域（`core` / `models` / `collectors` / `agent` / `knowledge` / `web`）。
3. **依赖注入**：通过构造函数注入依赖（`AlertProcessor`、`RCAEngine`、`VectorStore` 等），禁止在业务逻辑内硬编码单例。
4. **接口隔离**：采集器等可替换组件继承 `BaseCollector` 抽象基类。
5. **配置外置**：可配置项放 `config/` 与 `.env`；代码通过 `pydantic-settings` 的 `Settings` 读取，禁止硬编码密钥或 URL。
6. **最小 diff**：只改完成任务所需的文件；不重构无关代码；不新增未请求的依赖。
7. **TDD（测试驱动开发）**：严格执行红-绿-重构循环——先写失败测试，再写最小实现使测试通过，最后重构。代码变动完成后必须执行全量测试并通过，才能进入下一个需求迭代。**禁止跳过测试直接提交代码。**

### 1.1a Karpathy 编码准则

> 来源：[Andrej Karpathy](https://x.com/karpathy/status/2015883857489522876) 对 LLM 编码常见错误的观察。偏向谨慎而非速度。

1. **先想再写**：不要假设，不要隐藏困惑，明确表达权衡。实现前：显式声明假设；多种解释并存时列出而非静默选择；更简单的方案主动提出；不确定就停下来问。
2. **简单优先**：只写解决问题的最小代码。不做未要求的功能，不为单次使用抽象，不加未请求的"灵活性"，不处理不可能的场景。写 200 行能 50 行解决就重写。自问："高级工程师会觉得这过度复杂吗？"
3. **外科手术式改动**：只动必须动的。不"改进"相邻代码/注释/格式；不重构没坏的东西；匹配现有风格；发现无关死代码只提不删。每个改动的行都应直接追溯到用户需求。
4. **目标驱动执行**：把任务转为可验证目标。多步任务先列简要计划并逐步验证。强成功标准让你能独立循环，弱标准（"能跑就行"）需要反复确认。

### 1.1b Ponytail 极简编码准则

> 来源：[ponytail](https://github.com/DietrichGebert/ponytail) — 懒程序员哲学：能删则不写。

**决策阶梯**（遇到需求时自上向下检查，停在第一级可行的）：

1. **需要存在吗？** 非请求功能、 speculative 需求 → 不写，标记 YAGNI。
2. **代码库已有？** 复用现有 helper/util，禁止在 3 个文件外重新实现。
3. **标准库能行？** 优先 `functools.lru_cache` 而非自写缓存；优先 `pathlib` 而非 `os.path`。
4. **平台原生支持？** HTML5 原生 `<input type="date">` 优于 datepicker 库。
5. **已安装依赖可解？** 禁止为新功能引入新依赖，除非上述全部失效。
6. **能一行解决？** 一行代码优于 10 行封装。

**禁止事项**：
- 单实现接口（`Repository` 只有 `SqlRepository` 时，不要抽象基类）
- 配置项默认值永不被改动的配置
- "为以后预留"的扩展点

**完成标准**：
每次改动后自问："net: -N lines possible?" 若代码增加但功能未增，回滚重写。

### 1.2 目录与文件约定

```
src/langops/
├── core/           # config、exceptions、logging
├── models/         # Pydantic 数据模型（Alert、AnalysisResult、DedupInfo 等）
├── collectors/     # 数据采集器（BaseCollector + 具体实现）
├── agent/          # AlertProcessor、RCAEngine、prompts
├── knowledge/      # ChromaDB 向量存储封装
├── services/       # 通知、JIRA、降噪、修复执行
├── storage/        # SQLAlchemy 持久化（AlertRepository 等）
├── web/            # FastAPI app、api 路由、dependencies
└── server.py       # uvicorn 入口（python -m langops.server）

tests/
├── conftest.py
├── unit/           # 按 src 模块镜像目录
└── integration/    # API 与端到端流程

config/
└── .env.example    # 环境变量模板（根目录 .env.example 同步维护）
```

**新增功能顺序**（不得跳步）：

1. `src/models/` 定义数据模型  
2. `src/agent/` 或 `src/collectors/` 实现业务逻辑  
3. `src/web/api/` 暴露 API  
4. `tests/unit/` 单元测试  
5. `tests/integration/` 集成测试  
6. 必要时更新 `docs/`

### 1.3 Python 编码规范

**语言与工具**

- Python **≥ 3.11**；类型注解完整；`mypy --strict` 无报错。
- 格式化：`black`（行宽 100）、`isort`（profile=black）。
- 静态检查：`flake8`、`mypy`。

**导入顺序**

```python
# 1. 标准库
import json
from datetime import datetime
from typing import Any, Optional

# 2. 第三方库
from langfuse.decorators import observe
from pydantic import BaseModel, Field

# 3. 项目内部（langops 包）
from langops.core import get_logger, settings
from langops.models import Alert
```

**命名**

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/包 | snake_case | `alert_processor.py` |
| 类 | PascalCase | `AlertProcessor` |
| 函数/方法 | snake_case | `process_alert()` |
| 常量 | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| 私有成员 | 前导 `_` | `_session` |

**异步**

- I/O 密集操作（HTTP、LLM、DB）**必须** `async/await`。
- 禁止在 `async` 函数中调用阻塞 I/O；必要时用 `asyncio.to_thread()`。
- HTTP 客户端复用 `aiohttp.ClientSession` / `httpx.AsyncClient`，在 `close()` 中释放。

**数据模型**

- 领域模型使用 **Pydantic v2** `BaseModel`（计划中的 dataclass 以 Pydantic 为准）。
- API 请求/响应与领域模型分离：路由层可用 `web/models.py` 做 DTO 映射。
- 枚举用 `str, Enum`，值与 API JSON 一致（如 `critical`、`high`）。

**异常**

- 继承 `LangOpsException` 体系：`ConfigurationError`、`CollectorError`、`LLMError`、`VectorStoreError`、`AnalysisError`。
- 捕获后记录结构化日志，再向上抛或转为 API 错误响应；禁止裸 `except:`。
- 自定义异常携带上下文（如 `CollectorError(message, source="prometheus")`）。
- **Best-effort 外部调用**：非关键路径的外部服务（通知、JIRA、向量库等）失败时不阻断主流程——catch 后打日志，继续返回成功响应。关键路径（LLM 推理、核心数据写入）失败时才向上抛异常。每个 best-effort 调用必须在代码中标注 `# best-effort: <failure behavior>` 注释。

**结构化日志**

- 使用 `structlog`（`get_logger(__name__)`）；禁止 `print()` 调试残留。
- 生产环境 JSON 输出；`DEBUG=true` 时 Console 渲染。
- 日志字段用 snake_case 键名：`logger.error("LLM analysis failed", error=str(e), model=model)`。
- **每个模块入口**（`__init__.py` 或模块顶层）必须初始化 logger：`logger = get_logger(__name__)`。
- **禁止在函数体内重复导入或创建 logger**——始终使用模块级实例。

**日志滚动与归档**

- 生产环境日志文件必须启用自动滚动：`logging.handlers.RotatingFileHandler`（按大小）或 `TimedRotatingFileHandler`（按时间）。
- 默认配置：单文件上限 **10MB**，保留 **7 天**或 **5 个备份文件**。
- 日志路径通过 `Settings.log_file` 配置，默认 `logs/langops.log`。
- Docker/K8s 部署时，同时输出到 stdout（容器日志采集）和文件（本地排查）。
- 日志目录 `.gitignore` 忽略；禁止提交日志文件。

**请求生命周期日志**

- FastAPI 中间件记录每个请求的：`method`、`path`、`status_code`、`duration_ms`、`request_id`。
- `request_id` 通过 `X-Request-ID` header 传入或自动生成 UUID，贯穿整个请求链路。
- 所有下游调用（LLM、采集器、向量库）的日志必须包含 `request_id`，便于关联。
- 示例：`logger.info("Alert processed", request_id=req_id, alert_id=alert.id, duration_ms=1234)`

**业务关键路径日志**

- `AlertProcessor.process()`：记录入口（alert_id、severity）、每个阶段耗时（collect/analyze/remediate）、出口（trace_id、success/failure）。
- `RCAEngine.analyze()`：记录模型名、prompt 长度、响应耗时、token 用量、JSON 解析结果。
- 采集器 `collect()`：记录查询参数、返回数据量、HTTP 状态码、耗时。
- 降噪 `AlertNoiseReducer.evaluate()`：记录指纹、动作（process/suppress）、出现次数。
- 修复 `RemediationRegistry`：记录计划创建、状态变更、审批人、执行结果。

**错误日志规范**

- 所有 `except` 块必须记录：异常类型、异常消息、上下文字段（alert_id、plan_id 等）。
- 禁止空 `except:` 或 `except Exception: pass`——至少打 WARNING。
- 异常堆栈使用 `logger.exception()` 或 `logger.error(..., exc_info=True)`。
- 结构化字段示例：`logger.error("LLM call failed", error=str(e), model=model, alert_id=alert.id, exc_info=True)`

**外部调用诊断日志**

- HTTP 外部调用（Prometheus、阿里云 CMS、JIRA、通知 Webhook）：记录请求 URL、方法、状态码、耗时。
- LLM 调用：记录模型名、请求 token 数、响应 token 数、耗时、是否超时。
- 数据库操作：记录操作类型（select/insert/update）、表名、耗时、影响行数。
- 向量检索：记录查询文本（截断到 100 字符）、top_k、返回结果数。

**敏感信息脱敏**

- API Key、Secret 只记录后 4 位：`sk-...xxxx`。
- 禁止在日志中打印完整 PromQL 查询中的敏感标签值。
- 用户输入（告警 description）按原文记录，但日志收集端需配置脱敏规则。

**Langfuse 可观测性**

- 主流程方法加 `@observe(as_type="processor")`（或 `generation` / `span`）。
- 用 `langfuse_context.update_current_trace()` 写入 `alert_id`、`severity` 等元数据。
- 每个 `AnalysisResult` 必须包含 `trace_id`，便于 UI 回溯。
- Langfuse trace 与 structlog 日志通过 `trace_id` / `request_id` 双向关联。

**LLM 调用**

- 使用 `openai.AsyncOpenAI`；`response_format={"type": "json_object"}` 约束输出。
- Prompt 模板集中在 `src/agent/prompts.py`，禁止在业务代码内拼接大段字符串。
- 解析 JSON 失败抛 `LLMError`；修复建议生成失败可降级为 fallback，但须打日志。

**Collector**

- 实现 `collect()`、`health_check()`、`close()`。
- 外部服务不可用时抛 `CollectorError`，由上层决定是否继续流水线。
- 查询超时使用配置项（默认 Prometheus `timeout=10`），配合 `tenacity` 重试（最多 3 次，指数退避）。

**API（FastAPI）**

- 路由前缀 `/api/v1/`；健康检查 `/health`、`/` 无版本前缀。
- 使用 `Depends()` 注入 `AlertProcessor` 等依赖（`web/dependencies.py`）。
- 请求体验证失败返回 **422**；业务错误返回结构化 JSON（`success` / `error` 字段）。
- 不在路由处理函数内写核心业务逻辑，只做参数解析与调用 `AlertProcessor`。

**提交信息**

- 格式：`<type>(<scope>): <subject>`（英文、祈使句、小写 subject）
- type：`feat` | `fix` | `test` | `docs` | `refactor` | `chore`
- 示例：`feat(collectors): add Prometheus collector with K8s metrics support`
- **Worktree 流程内的 `git commit` / `git merge` / `git push` 属于 5.1 流程本身的一部分,不需用户每次单独授权**;除此之外的提交仍需明确要求。
- 不提交 `.env` 或含密钥文件。

---

## 二、测试规范

### 2.1 测试金字塔

| 层级 | 目录 | 职责 | 外部依赖 |
|------|------|------|----------|
| 单元测试 | `tests/unit/` | 模型、prompt 构建、解析逻辑、纯函数 | 全部 mock |
| 集成测试 | `tests/integration/` | FastAPI 路由、组件协作 | 可 mock LLM / 向量库 |
| 端到端 | `tests/integration/test_e2e.py` | 完整告警流水线 | 需 docker-compose 栈（可选 CI 跳过） |

### 2.2 工具与配置

- 框架：**pytest** + **pytest-asyncio**（`asyncio_mode = auto`）。
- 配置：`pyproject.toml` `[tool.pytest.ini_options]` 或根目录 `pytest.ini`。
- 覆盖率：新模块目标 **≥ 80%** 行覆盖（`pytest --cov=langops`）；核心路径（`AlertProcessor`、`RCAEngine`）必须有测试。

### 2.3 编写规则

1. **先写失败测试再实现**（对非平凡逻辑）：TDD 适用于解析器、prompt 构建、模型校验。
2. **命名**：文件 `test_<module>.py`；类 `Test*`；函数 `test_<behavior>_<condition>`。
3. **Fixtures**：共享 fixture 放 `tests/conftest.py`（`client`、`sample_alert_data` 等）。
4. **隔离**：
   - 单元测试不得依赖真实 OpenAI、Langfuse、ChromaDB、Prometheus。
   - 使用 `unittest.mock.AsyncMock` / `pytest-mock` mock 外部客户端。
   - 集成测试用 `TestClient(app)`，不启动真实 uvicorn。
5. **断言**：
   - 验证状态码、响应 schema 关键字段、异常类型。
   - 告警创建成功时断言 `alert_id`、`trace_id`、`root_cause` 存在；失败时断言 `error` 字段。
6. **禁止**：依赖测试执行顺序；使用真实 API Key；在仓库留下临时 `test_*.py` 脚本（应进 `tests/`）。
7. **HTTP 客户端 Mock 规范**：
   - 将 session 获取提取为 `_get_session()` 方法（返回 `AsyncMock`），测试中通过 mock `_get_session` 注入 `MagicMock(session)`。
   - 禁止在业务方法内直接 `aiohttp.ClientSession()`，否则单元测试无法替换。
   - 模拟网络异常时使用 `aiohttp.ClientConnectionError` 等真实异常类型，而非 `ConnectionError`（避免 catch 遗漏）。

### 2.4 运行命令

```bash
# 单元测试（默认 CI 门禁）
pytest tests/unit -v

# 集成测试
pytest tests/integration -v

# 全量 + 覆盖率
pytest tests/ -v --cov=langops --cov-report=term-missing

# 单个测试
pytest tests/unit/test_agent/test_alert_processor.py::test_process_alert -v
```

### 2.5 完成定义（DoD）

任务完成前必须满足：

- [ ] 相关单元测试已添加并通过  
- [ ] `black`、`isort`、`flake8`、`mypy` 无新增错误  
- [ ] 若改动 API，集成测试已更新  
- [ ] 未将密钥写入测试代码或 fixture  

---

## 三、安全规范

### 3.1 密钥与配置

| 规则 | 说明 |
|------|------|
| 禁止硬编码密钥 | API Key、AK/SK、Webhook URL 仅来自环境变量或密钥管理系统 |
| 禁止提交敏感文件 | `.env`、`*.pem`、`kubeconfig` 已在 `.gitignore`；提交前检查 `git status` |
| 模板文件 | `.env.example` 只用占位符（`xxxxx`、`sk-lf-xxxxx`） |
| 配置加载 | `Settings` 使用 `extra="ignore"`；日志中不得打印完整密钥（最多后四位） |

### 3.2 输入验证与输出安全

- 所有 API 入参经 **Pydantic** 校验；额外字段默认拒绝或忽略（与模型定义一致）。
- 告警 `description`、`metric_data` 等字段传入 LLM 前不做 HTML 渲染；API 响应设置合适 `Content-Type`。
- 对用户可控字符串做长度限制（建议：title ≤ 500 字符，description ≤ 10000 字符）。
- LLM 返回的 `commands` 字段仅作建议展示，**禁止**在服务端自动执行 shell 命令。

### 3.3 网络安全

- 出站 HTTP 必须设置 **timeout**（连接 + 读取）；禁止无限等待。
- 生产环境对外服务启用 HTTPS；`NEXTAUTH_SECRET`、`SALT` 等本地 docker 默认值不得用于生产。
- Prometheus / K8s / 阿里云凭证按最小权限配置；不在日志中记录完整 PromQL 中的敏感标签值。

### 3.4 API 安全（MVP 基线）

- MVP 阶段：内网或受信 Webhook 调用；`/health` 可公开。
- 计划外不擅自添加认证；若添加 JWT/API Key，须同步更新 `docs/` 与测试。
- 错误响应不泄露堆栈（`debug=false` 时返回通用消息，详情仅写日志）。

### 3.5 依赖安全

- 依赖版本在 `pyproject.toml` / `requirements.txt` 中锁定下限版本。
- 不引入未经批准的新依赖；优先标准库 + 已有栈。
- 处理外部 JSON 用 `json.loads` 后校验 schema，不信任 LLM 输出结构。

### 3.7 幂等性与副作用

- 所有产生外部副作用的操作（创建工单、发送通知、执行命令）**必须**是幂等的或在调用前做好去重检查。
- API 层不做自动重试有副作用的调用；由调用方（客户端/Webhook）决定重试策略。
- 修复执行等高风险操作始终需要显式确认，不支持自动审批后的自动重试。

### 3.8 Agent 行为红线

- 不执行 `git push --force`、不修改 `git config`、不跳过 hooks（除非用户明确要求）。
- 不将用户告警原文、凭证写入 AGENTS.md 或随意创建的文档。
- 安全相关改动需注明威胁模型（防什么、不防什么）。

---

## 四、性能规范

### 4.1 延迟目标（MVP）

| 阶段 | 目标 | 说明 |
|------|------|------|
| API 健康检查 | < 50ms | 无外部依赖 |
| 数据采集 | < 5s | 单告警 Prometheus 查询 |
| LLM 根因分析 | < 30s | 含网络；可配置 timeout |
| 端到端 `POST /api/v1/alerts` | < 60s | P95，依赖 LLM |

### 4.2 并发与异步

```python
# 多数据源采集必须并行
results = await asyncio.gather(
    collect_prometheus(alert),
    collect_logs(alert),
    return_exceptions=True,  # 单项失败不拖垮整链路
)
```

- FastAPI 路由处理函数为 `async def`。
- `workers`：开发 `1`；生产按 CPU 配置（`settings.workers`），注意 Langfuse 客户端线程安全。

### 4.3 超时与重试

| 组件 | 默认超时 | 重试 |
|------|----------|------|
| Prometheus HTTP | 10s | tenacity 最多 3 次 |
| OpenAI API | 60s | 仅对 429/5xx 退避重试 |
| ChromaDB | 10s | 1 次 |
| Redis | 5s | 缓存失败降级为直查 |

- 使用 `tenacity` 统一重试策略；禁止无界重试。
- 重试与超时写入配置类，便于测试覆盖。

### 4.4 缓存

- 热点指标查询：Redis 缓存 TTL **300s**（key 含 pod/namespace 维度）。
- 配置与 prompt 模板：进程内 `lru_cache`（`get_settings()` 已示范）。
- 向量检索：`top_k` 默认 5，最大 20；避免全表扫描。

### 4.5 资源与扩展

- HTTP Session / 连接池在应用生命周期内复用，在 shutdown 事件 `close()`。
- 单请求 LLM `max_tokens` 上限 1500（RCA）/ 1500（remediation），避免失控账单。
- 大 `metric_data` 传入 LLM 前做摘要或截断（保留最近 N 个数据点）。
- 列表 API 必须分页（`limit` / `offset` 或 cursor），默认 `limit=20`。

### 4.6 可观测性与性能排查

- 关键步骤在 Langfuse 中记录耗时（`collect`、`analyze`、`retrieve`、`remediate`）。
- 结构化日志包含 `duration_ms` 字段。
- 性能回退时先查 Langfuse Trace，再查 Prometheus/collector 延迟。

### 4.6a Request ID 与请求链路追踪

- FastAPI 中间件从 `X-Request-ID` header 读取或自动生成 UUID4。
- `request_id` 存入 `contextvars.ContextVar`，所有 structlog 日志自动携带。
- 所有下游调用（LLM、采集器、存储、外部 API）的日志必须包含 `request_id`。
- Langfuse trace 通过 `trace_id` 关联，structlog 日志通过 `request_id` 关联——双向可查。
- API 响应 header 返回 `X-Request-ID`，便于前端/调用方关联。

### 4.6b 应用级 Prometheus Metrics

- 暴露 `/metrics` 端点（prometheus_client 库），格式兼容 Prometheus scrape。
- 核心指标（必须实现）：

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `langops_alerts_received_total` | Counter | severity, category | 接收告警总数 |
| `langops_alerts_processed_total` | Counter | severity, status | 处理完成总数（status=success/failure） |
| `langops_alert_processing_duration_seconds` | Histogram | — | 告警处理端到端耗时 |
| `langops_dedup_suppressed_total` | Counter | — | 降噪抑制告警总数 |
| `langops_llm_calls_total` | Counter | model, status | LLM 调用总数 |
| `langops_llm_call_duration_seconds` | Histogram | model | LLM 调用耗时 |
| `langops_llm_tokens_total` | Counter | model, type | Token 用量（type=prompt/completion） |
| `langops_collector_query_duration_seconds` | Histogram | source | 数据采集器查询耗时 |
| `langops_remediation_plans_total` | Counter | risk_level | 修复计划创建总数 |
| `langops_remediation_actions_total` | Counter | action, status | 修复操作总数（action=execute/reject） |
| `langops_http_requests_total` | Counter | method, path, status_code | HTTP 请求总数 |
| `langops_http_request_duration_seconds` | Histogram | method, path | HTTP 请求耗时 |

- Metrics 不得包含用户告警原文、API Key 等敏感信息。
- Metrics 标签值必须为枚举或有限集合，禁止高基数标签（如 alert_id、request_id）。

### 4.6c Health Check 深度检查

- `/health` 端点必须检查所有已配置的下游依赖，返回每个依赖的状态和延迟。
- 响应格式：
  ```json
  {
    "status": "healthy|degraded|unhealthy",
    "version": "0.1.0",
    "checks": {
      "storage": {"status": "up", "latency_ms": 2},
      "langfuse": {"status": "up", "latency_ms": 45},
      "prometheus": {"status": "down", "latency_ms": null, "error": "timeout"}
    }
  }
  ```
- `status` 判定规则：所有 up → healthy；部分 down → degraded；核心依赖（storage）down → unhealthy。
- Health check 超时：单个依赖 **3 秒**，整体 **10 秒**。
- Health check 不得泄露敏感配置（URL 中的密码、Token 等）。

### 4.6d AlertProcessor 流水线阶段日志

- `AlertProcessor.process()` 内部每个阶段必须记录独立的结构化日志：
  - **collect**：`logger.info("Metrics collected", alert_id=..., sources=..., metrics_count=..., duration_ms=...)`
  - **analyze**：`logger.info("RCA analysis completed", alert_id=..., trace_id=..., model=..., tokens=..., duration_ms=...)`
  - **retrieve**：`logger.info("Knowledge retrieved", alert_id=..., results_count=..., duration_ms=...)`
  - **remediate**：`logger.info("Remediation plan created", alert_id=..., plan_id=..., risk_level=..., duration_ms=...)`
- 每个阶段的成功/失败必须独立记录，不得只在顶层记录。

### 4.6e 外部调用诊断日志

- 所有外部 HTTP 调用（Prometheus、阿里云 CMS、JIRA、通知 Webhook）必须记录：
  ```python
  logger.info("HTTP request completed",
      component="prometheus_collector",
      method="GET",
      status_code=200,
      duration_ms=234,
      target="prometheus",
  )
  ```
- LLM 调用必须记录：模型名、请求 token 数、响应 token 数、耗时、是否超时。
- 数据库操作必须记录：操作类型（select/insert/update）、表名、耗时、影响行数。
- 向量检索必须记录：查询文本（截断到 100 字符）、top_k、返回结果数。

### 4.6f 审计日志

- 所有产生外部副作用的操作必须记录审计日志（`logger.info`，级别不低于 INFO）：
  - 修复计划创建、审批、执行、拒绝（含操作人）
  - JIRA 工单创建
  - 告警降噪抑制决策
- 审计日志必须包含：操作类型、操作人、目标资源 ID、操作结果、时间戳。
- 审计日志不得包含密码、Token 等敏感信息。

### 4.7 数据库连接池

- SQLAlchemy `create_engine` 配置 `pool_size` 和 `max_overflow`：
  - SQLite：无需连接池（单写者模型），`pool_size=0`。
  - PostgreSQL：`pool_size=10`，`max_overflow=20`，`pool_timeout=30`。
- 连接池参数写入 `StorageSettings`，便于测试覆盖。
- 应用 shutdown 时调用 `engine.dispose()` 释放连接。

### 4.8 熔断器（Circuit Breaker）

- 对外部服务（LLM API、Prometheus、ChromaDB）启用熔断保护。
- 连续失败 **5 次**后进入 OPEN 状态，拒绝后续请求 **60 秒**。
- HALF-OPEN 状态下允许 **1 次**探测请求，成功则恢复 CLOSED。
- 实现方式：`tenacity` 的 `circuit_breaker` 或独立的 `circuitbreaker` 库。
- 熔断事件记录到 structlog，便于告警。

### 4.9 并发与限流

- 单实例 LLM 并发上限：通过 `asyncio.Semaphore` 控制，默认 **5** 并发。
- API 层限流：使用 `slowapi` 或自定义中间件，默认 **100 req/s**。
- 超出限流返回 `429 Too Many Requests`，日志记录拒绝事件。
- 并发/限流参数写入 `Settings`，便于测试覆盖。

### 4.10 内存保护

- 向量检索结果集：`top_k` 硬上限 **20**，超过截断并打 WARNING。
- `metric_data` 传入 LLM 前：单字段大小上限 **10KB**，超过做摘要或截断。
- 大批量操作（如知识库初始化）使用流式处理，避免一次性加载全量数据到内存。

### 4.11 负载测试基线

- 单实例目标 QPS：**50**（含 LLM 调用，P99 < 120s）。
- 纯 API（无 LLM）目标 QPS：**200**（P99 < 1s）。
- 压测工具：`locust` 或 `k6`，脚本放 `tests/load/`。
- CI 不自动执行压测；发版前手动运行一次，结果记录到 Langfuse。

---

## 五、Agent 工作流

### 5.1 实施 MVP 计划

1. 阅读 [MVP 实现计划](docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md) 当前 Task。
2. **每个新功能点都必须在独立 Git Worktree + 功能分支上开发**（禁止在 `main` 上直接改代码）；一个 Worktree 只承载一个功能点的所有变更。
   - **「功能点」定义**：最小可独立合并并独立回滚的语义单元（通常对应 1 个 User Story 或 1.2 节的单个功能位次）。禁止把多个独立功能点的变更堆在同一个 Worktree / 分支里一起合并——这会让"独立复盘、独立回滚"成为空话。
   - 本节是 1.1a Karpathy 编码准则中「目标驱动执行 + 外科手术式改动」在 Worktree 维度的落地。
3. 严格按计划中的 **Files** 列表创建/修改文件。
4. 在 Worktree 内执行「**开发 → 测试 → 自我复盘 → 修复问题**」的循环：跑完测试后必须主动复盘代码与测试结果（设计合理性、边界用例、命名、可观测性、是否符合本规范第 1–4 节），把发现的问题在 Worktree 内修复后再跑一轮测试。**该循环需往复多次，直到自觉没有遗留问题为止**——不允许"测试一次通过就合并"。
5. 合并需同时满足**客观门 + 自觉门**,缺一不可:
   - **客观门**(必须全部满足):
     - Worktree 内 `pytest` 全绿;
     - `black` / `isort` / `flake8` / `mypy` 无新增错误;
     - 5.2 自检清单逐项勾选通过。
   - **自觉门**:对照 1.1 设计原则与 1.1a Karpathy 准则完成复盘,本轮已无明显遗留问题。
   - 仅两扇门都通过后,才允许合并回 `main` → 在 main 上重跑 `pytest` 验证合并结果 → `git push origin main` → 删除 worktree 与功能分支。
6. 遇阻塞（依赖缺失、测试持续失败、指令歧义、复盘发现无法自决的设计问题）**停止并询问**,不猜测。

#### Git Worktree 标准流程（每个新功能点强制执行）

Worktree 目录：`.worktrees/<branch-slug>/`（已在 `.gitignore` 中忽略）

```bash
# 1. 确保 main 最新
git checkout main && git pull origin main

# 2. 创建 worktree + 功能分支（一个 worktree 仅承载一个功能点）
#    slug 形如：<type>/<scope>-<short-name>，例：feat/models-pydantic、fix/collector-timeout
git worktree add .worktrees/feat-models-pydantic -b feat/models-pydantic

# 3. 进入隔离工作区并安装依赖
cd .worktrees/feat-models-pydantic
uv sync --dev
export LLM_API_KEY=sk-test LANGFUSE_PUBLIC_KEY=pk-test LANGFUSE_SECRET_KEY=sk-lf-test
pytest tests/ -q   # 基线必须全绿

# 4. 开发 → 测试 → 自我复盘 → 修复，往复循环，直到自觉无问题
#    - 实现代码与对应测试（红-绿-重构，遵循 1.7 节 TDD）
#    - pytest / black / isort / flake8 / mypy 全部通过
#    - 自我复盘：对照 5.2 自检清单 + 1.1 设计原则，找出可优化点
#    - 在同一 worktree 内修复问题、补测试，再跑一遍验证
#    - 重复上述步骤，直到本轮已无明显遗留问题
git add ... && git commit -m "feat(models): ..."

# 5. 合并回 main 并推送（仅在客观门 + 自觉门都通过后执行）
cd /path/to/LangOps   # 主工作区
git checkout main && git merge feat/models-pydantic --no-edit
pytest tests/ -q      # 合并后再次验证（main 期间可能有他人合入,Worktree 内全绿不代表合并后仍全绿）
git push origin main

# 6. 清理
git worktree remove .worktrees/feat-models-pydantic
git branch -d feat/models-pydantic
```

**分支命名**：`<type>/<scope>-<short-name>`，其中 `type` 取 `feat` / `fix` / `refactor` / `test` / `docs` / `chore`；例：`feat/models-pydantic`、`fix/collector-timeout`、`feat/agent-rca-engine`。
- 这是 **git branch 名**,与 1.3 节 commit message 的 `<type>(<scope>): <subject>` 是两套独立规范:branch 用 `/` 分隔,commit message 用 `()` 包裹 scope。
- 例:`branch: feat/collector-timeout` → 对应 commit: `fix(collector): add timeout for prometheus queries`。

**Worktree 颗粒度**：一个 Worktree + 一个分支 = 一个功能点；不允许把多个独立功能点的变更堆在同一个 Worktree / 分支里一起合并。

### 5.2 代码审查自检清单

提交前逐项确认：

- [ ] 符合本文档四节规范  
- [ ] 符合计划当前 Task 的文件与代码结构  
- [ ] 无硬编码密钥、无 `print` 调试  
- [ ] 新增逻辑有对应测试  
- [ ] `@observe` 与 `trace_id` 已接入（若改动 Agent 流水线）  
- [ ] 文档未擅自大量新增（除非 Task 要求）  

#### Review 反馈处理规则

收到代码审查反馈后：

1. **先理解，再修改**：确认反馈的技术依据后再执行修改。不盲目执行。
2. **对不可靠的建议先验证**：如果反馈的建议看上去缺少验证或与代码实际行为不符，**先验证再修改**，不止于「just fix it」。
3. **有异议时用技术论据回应**：用具体代码推断回应（如「第 42 行做了类型守卫，这里不会出现 None」），不接受压迫式答复。
4. **修改后回归测试**：修改后重新运行全部相关测试，确认未引入回归。

### 5.3 本地开发速查

```bash
docker-compose up -d
cp .env.example .env   # 填入密钥
uv sync --dev
uv run langops.server
uv run pytest tests/unit -v
uv run black src/ tests/ && uv run isort src/ tests/ && uv run flake8 src/ && uv run mypy src/
```

---

## 六、规范冲突处理

| 优先级 | 来源 |
|--------|------|
| 1 | 用户当前明确指令 |
| 2 | MVP 实现计划具体步骤 |
| 3 | 本文档（AGENTS.md） |
| 4 | docs/architecture/* |
| 5 | 通用 Python/FastAPI 最佳实践 |

---

**版本**：与 MVP 实现计划同步（2026-06-25）  
**维护**：架构或计划变更时，同步更新本文档对应章节。
