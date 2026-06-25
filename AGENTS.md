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

### 1.2 目录与文件约定

```
src/
├── core/           # config、exceptions、logging
├── models/         # Pydantic 数据模型（Alert、AnalysisResult 等）
├── collectors/     # 数据采集器（BaseCollector + 具体实现）
├── agent/          # AlertProcessor、RCAEngine、prompts
├── knowledge/      # ChromaDB 向量存储封装
├── web/            # FastAPI app、api 路由、dependencies
└── server.py       # uvicorn 入口

tests/
├── conftest.py
├── unit/           # 按 src 模块镜像目录
└── integration/    # API 与端到端流程

config/
├── application.yaml
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

**日志**

- 使用 `structlog`（`get_logger(__name__)`）；禁止 `print()` 调试残留。
- 生产环境 JSON 输出；`DEBUG=true` 时 Console 渲染。
- 日志字段用 snake_case 键名：`logger.error("LLM analysis failed", error=str(e), model=model)`。

**Langfuse 可观测性**

- 主流程方法加 `@observe(as_type="processor")`（或 `generation` / `span`）。
- 用 `langfuse_context.update_current_trace()` 写入 `alert_id`、`severity` 等元数据。
- 每个 `AnalysisResult` 必须包含 `trace_id`，便于 UI 回溯。

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
- **仅在被明确要求时** 执行 `git commit`；不提交 `.env` 或含密钥文件。

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

### 3.6 Agent 行为红线

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

---

## 五、Agent 工作流

### 5.1 实施 MVP 计划

1. 阅读 [MVP 实现计划](docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md) 当前 Task。
2. 在独立分支/worktree 开发（勿直接在 `main` 上大规模改动）。
3. 严格按计划中的 **Files** 列表创建/修改文件。
4. 完成 Task 内 **验证步骤**（运行测试、curl、脚本）后再进入下一 Task。
5. 遇阻塞（依赖缺失、测试持续失败、指令歧义）**停止并询问**，不猜测。

### 5.2 代码审查自检清单

提交前逐项确认：

- [ ] 符合本文档四节规范  
- [ ] 符合计划当前 Task 的文件与代码结构  
- [ ] 无硬编码密钥、无 `print` 调试  
- [ ] 新增逻辑有对应测试  
- [ ] `@observe` 与 `trace_id` 已接入（若改动 Agent 流水线）  
- [ ] 文档未擅自大量新增（除非 Task 要求）  

### 5.3 本地开发速查

```bash
docker-compose up -d
cp .env.example .env   # 填入密钥
pip install -e ".[dev]"
python -m langops.server
pytest tests/unit -v
black src/ tests/ && isort src/ tests/ && flake8 src/ && mypy src/
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
