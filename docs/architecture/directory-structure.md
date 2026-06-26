# LangOps 目录结构说明

> **包名**：`langops`（源码在 `src/langops/`）。与 [AGENTS.md](../../AGENTS.md) 及当前仓库一致；下文「规划中」项尚未创建。

## 项目根目录

```
LangOps/
├── docs/                       # 文档
├── src/langops/                # 应用源码（Python 包）
├── tests/                      # 测试
├── config/                     # 配置模板
├── scripts/                    # 工具脚本
├── .worktrees/                 # Git worktree（本地，已 gitignore）
├── docker-compose.yml          # 本地依赖（Langfuse、ChromaDB 等）
├── pyproject.toml              # 项目元数据与依赖
├── requirements.txt            # 锁定依赖（可选）
├── AGENTS.md                   # AI / 开发者规范
└── README.md
```

## 详细说明

### docs/ - 文档目录

```
docs/
├── architecture/
│   ├── system-design.md        # 系统设计（主文档）
│   ├── directory-structure.md  # 本文档
│   └── quick-reference.md      # 快速参考
└── superpowers/plans/
    └── 2026-06-25-langops-mvp-implementation.md  # MVP 实施计划
```

### src/langops/ - 源代码（实际结构）

```
src/langops/
├── __init__.py
├── server.py                   # uvicorn 入口：python -m langops.server
├── core/
│   ├── config.py               # pydantic-settings（LLM、Langfuse、降噪、修复等）
│   ├── exceptions.py
│   └── logging.py
├── models/
│   ├── alert.py
│   ├── analysis.py             # AnalysisResult、AnalysisResponse、DedupInfo
│   ├── dedup.py
│   ├── prediction.py
│   ├── query.py
│   ├── remediation.py          # RemediationPlan、审批请求/响应
│   └── __init__.py
├── collectors/
│   ├── base.py
│   ├── prometheus_collector.py
│   └── aliyun_cms_collector.py
├── agent/
│   ├── alert_processor.py      # 告警处理主流程
│   ├── rca_engine.py
│   ├── nl_query_engine.py      # NL2PromQL
│   ├── predictive_engine.py    # 容量趋势预测
│   └── prompts.py
├── knowledge/
│   └── vector_store.py         # ChromaDB 封装
├── services/
│   ├── notification.py         # 飞书 / 钉钉
│   ├── alert_dedup.py          # 告警降噪
│   └── remediation_executor.py # 修复计划注册与 kubectl 白名单执行
└── web/
    ├── main.py                 # FastAPI create_app、静态 UI 挂载
    ├── dependencies.py         # DI：processor、registry、executor
    ├── api/
    │   ├── alerts.py
    │   ├── query.py
    │   ├── predict.py
    │   └── remediation.py
    └── static/                 # Web UI（无构建步骤）
        ├── index.html
        ├── css/app.css
        └── js/app.js
```

### tests/ - 测试代码（实际结构）

```
tests/
├── conftest.py                 # 环境变量、FastAPI dependency overrides
├── unit/
│   ├── test_core/
│   ├── test_models/
│   ├── test_agent/
│   ├── test_collectors/
│   ├── test_knowledge/
│   ├── test_services/          # notification、dedup、remediation
│   ├── test_web/               # API、UI 静态资源
│   ├── test_scripts/
│   └── test_server.py
└── integration/
    ├── test_e2e.py
    └── test_ui.py
```

运行：`pytest tests/ -q`（当前基线 126 passed）。

### config/ - 配置文件

```
config/
└── .env.example                # 环境变量模板（与根目录 .env.example 同步维护）
```

应用配置通过 **环境变量 + `.env`** 加载，见 `langops.core.config.Settings`。

### scripts/ - 工具脚本

```
scripts/
└── init_knowledge.py           # 向 ChromaDB 写入示例运维案例
```

### deployment/ - K8s 部署（规划中）

```
deployment/                     # 尚未在仓库中落地，见 system-design.md 目标结构
```

## 关键文件说明

### 入口文件

| 文件 | 说明 |
|-----|------|
| `src/langops/server.py` | `python -m langops.server` 启动 uvicorn |
| `src/langops/web/main.py` | FastAPI 应用、路由注册、`/ui` 静态页 |
| `src/langops/agent/alert_processor.py` | 告警分析流水线 |

### 配置文件

| 文件 | 说明 |
|-----|------|
| `.env.example` | 环境变量模板 |
| `.env` | 本地密钥（不提交） |
| `docker-compose.yml` | Langfuse、ChromaDB、Redis 等 |
| `pyproject.toml` | 依赖与工具配置 |

### 核心模型

| 文件 | 说明 |
|-----|------|
| `models/alert.py` | 告警输入 |
| `models/analysis.py` | 分析结果与 API 响应（含 `dedup`、`remediation_plan_id`） |
| `models/remediation.py` | 修复审批计划 |

## 编码规范

### 模块组织原则

1. **单一职责**：每个模块只负责一个功能领域
2. **依赖注入**：通过构造函数注入依赖，便于测试
3. **接口隔离**：定义抽象基类，具体实现可替换
4. **配置外置**：所有可配置项放在 `config/` 目录

### 导入规范

```python
# 标准库
import json
from datetime import datetime
from typing import List, Optional

# 第三方库
import aiohttp
from langfuse import Langfuse
from pydantic import BaseModel

# 项目内部
from langops.models.alert import Alert
from langops.core.config import settings
```

### 命名规范

| 类型 | 命名风格 | 示例 |
|-----|---------|------|
| 模块/包 | 小写下划线 | `alert_processor.py` |
| 类 | 大驼峰 | `AlertProcessor` |
| 函数/方法 | 小写下划线 | `process_alert()` |
| 常量 | 大写下划线 | `MAX_RETRY_COUNT` |
| 私有属性 | 前下划线 | `_internal_state` |

## 开发工作流

### 添加新功能

1. **数据模型**：在 `src/models/` 定义数据模型
2. **业务逻辑**：在 `src/agent/` 或 `src/services/` 实现
3. **API 接口**：在 `src/web/api/` 添加路由
4. **单元测试**：在 `tests/unit/` 编写测试
5. **集成测试**：在 `tests/integration/` 验证
6. **文档更新**：在 `docs/` 更新相关文档

### 调试技巧

```bash
# 启动本地开发环境
docker compose up -d

# 启动 API
python -m langops.server

# 运行测试
pytest tests/ -q

# Web UI / API 文档
open http://localhost:8000/ui
open http://localhost:8000/docs

# Langfuse UI
open http://localhost:3000
```
