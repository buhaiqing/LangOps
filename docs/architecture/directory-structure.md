# LangOps 目录结构说明

## 项目根目录

```
LangOps/
├── docs/                       # 文档目录
├── src/                        # 源代码
├── tests/                      # 测试代码
├── config/                     # 配置文件
├── scripts/                    # 工具脚本
├── deployment/                 # K8s 部署文件
├── docker-compose.yml          # 本地开发环境
├── requirements.txt            # Python 依赖
├── pyproject.toml              # Python 项目配置
└── README.md                   # 项目说明
```

## 详细说明

### docs/ - 文档目录

```
docs/
├── architecture/               # 架构文档
│   ├── system-design.md        # 系统设计文档（主文档）
│   ├── directory-structure.md  # 目录结构说明（本文档）
│   ├── workflow.md             # 工作流详解
│   └── data-model.md           # 数据模型文档
├── api/                        # API 文档
│   ├── openapi.yaml            # OpenAPI 规范
│   └── examples.md             # API 使用示例
└── deployment/                 # 部署文档
    ├── local-setup.md          # 本地开发环境搭建
    ├── kubernetes.md           # K8s 部署指南
    └── configuration.md        # 配置详解
```

### src/ - 源代码

```
src/
├── __init__.py                 # 包初始化
├── agent/                      # AI Agent 核心模块
│   ├── __init__.py
│   ├── alert_processor.py      # 告警处理器 - 主入口
│   ├── rca_engine.py           # 根因分析引擎
│   ├── suggestion_engine.py    # 修复建议引擎
│   ├── nl_query_engine.py      # 自然语言查询引擎
│   └── prompts/                # 提示词模板
│       ├── rca_prompts.py      # 根因分析提示词
│       ├── suggestion_prompts.py
│       └── nl_query_prompts.py
├── collectors/                 # 数据采集器
│   ├── __init__.py
│   ├── base.py                 # 采集器基类
│   ├── prometheus_collector.py # Prometheus 采集器
│   ├── aliyun_collector.py     # 阿里云 CMS 采集器
│   ├── k8s_collector.py        # Kubernetes 采集器
│   └── loki_collector.py       # Loki 日志采集器
├── knowledge/                  # 知识库模块
│   ├── __init__.py
│   ├── vector_store.py         # 向量存储
│   ├── case_manager.py         # 案例管理
│   ├── embedding.py            # 向量化服务
│   └── retriever.py            # 检索器
├── web/                        # Web 服务
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用入口
│   ├── api/                    # API 路由
│   │   ├── __init__.py
│   │   ├── alerts.py           # 告警相关接口
│   │   ├── query.py            # 查询接口
│   │   ├── knowledge.py        # 知识库接口
│   │   └── traces.py           # Trace 查询接口
│   ├── models.py               # Pydantic 模型
│   ├── dependencies.py         # FastAPI 依赖
│   └── middleware.py           # 中间件
├── models/                     # 核心数据模型
│   ├── __init__.py
│   ├── alert.py                # 告警模型
│   ├── analysis.py             # 分析结果模型
│   ├── knowledge.py            # 知识库模型
│   └── common.py               # 通用模型
├── services/                   # 业务服务
│   ├── __init__.py
│   ├── notification.py         # 通知服务
│   ├── jira_integration.py     # JIRA 集成
│   └── feishu_integration.py   # 飞书集成
├── observability/              # 可观测性
│   ├── __init__.py
│   ├── langfuse_setup.py       # Langfuse 初始化
│   ├── metrics.py              # Prometheus 指标
│   └── logging.py              # 日志配置
├── core/                       # 核心工具
│   ├── __init__.py
│   ├── config.py               # 配置管理
│   ├── exceptions.py           # 自定义异常
│   └── utils.py                # 工具函数
└── server.py                   # 服务启动入口
```

### tests/ - 测试代码

```
tests/
├── __init__.py
├── conftest.py                 # pytest 配置
├── unit/                       # 单元测试
│   ├── test_agent/
│   │   ├── test_alert_processor.py
│   │   ├── test_rca_engine.py
│   │   └── test_suggestion_engine.py
│   ├── test_collectors/
│   │   ├── test_prometheus_collector.py
│   │   └── test_aliyun_collector.py
│   └── test_knowledge/
│       ├── test_vector_store.py
│       └── test_case_manager.py
├── integration/                # 集成测试
│   ├── test_api/
│   │   ├── test_alerts_api.py
│   │   └── test_query_api.py
│   └── test_workflow/
│       └── test_alert_processing.py
├── e2e/                        # 端到端测试
│   └── test_full_pipeline.py
└── fixtures/                   # 测试数据
    ├── alerts/
    ├── metrics/
    └── cases/
```

### config/ - 配置文件

```
config/
├── application.yaml            # 主配置文件
├── application-dev.yaml        # 开发环境配置
├── application-prod.yaml       # 生产环境配置
├── prompts/                    # 提示词配置
│   ├── rca.yaml
│   ├── suggestion.yaml
│   └── nl_query.yaml
└── rules/                      # 业务规则
    ├── alert_rules.yaml
    └── rca_rules.yaml
```

### scripts/ - 工具脚本

```
scripts/
├── setup/                      # 初始化脚本
│   ├── init_db.py              # 数据库初始化
│   ├── init_knowledge.py       # 知识库初始化
│   └── create_admin.py         # 创建管理员
├── maintenance/                # 维护脚本
│   ├── backup_knowledge.py     # 知识库备份
│   ├── cleanup_traces.py       # 清理旧 Trace
│   └── health_check.py         # 健康检查
├── dev/                        # 开发工具
│   ├── generate_openapi.py     # 生成 OpenAPI 文档
│   ├── run_tests.py            # 运行测试
│   └── lint.sh                 # 代码检查
└── deployment/                 # 部署脚本
    ├── build_image.sh          # 构建镜像
    ├── deploy_k8s.sh           # K8s 部署
    └── rollback.sh             # 回滚脚本
```

### deployment/ - K8s 部署文件

```
deployment/
├── base/                       # 基础配置
│   ├── namespace.yaml
│   ├── configmap.yaml
│   └── secret.yaml
├── langops/                    # LangOps 应用
│   ├── deployment.yaml
│   ├── service.yaml
│   └── hpa.yaml               # 自动扩缩容
├── dependencies/               # 依赖服务
│   ├── langfuse/              # Langfuse 部署
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── postgres.yaml
│   ├── chromadb/              # ChromaDB 部署
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── pvc.yaml
│   └── redis/                 # Redis 部署
│       ├── deployment.yaml
│       └── service.yaml
├── monitoring/                 # 监控配置
│   ├── service-monitor.yaml
│   └── alerts.yaml
└── kustomization.yaml         # Kustomize 配置
```

## 关键文件说明

### 入口文件

| 文件 | 说明 |
|-----|------|
| `src/server.py` | 服务启动入口，初始化 FastAPI 应用 |
| `src/web/main.py` | FastAPI 应用定义，注册路由和中间件 |
| `src/agent/alert_processor.py` | 告警处理主逻辑 |

### 配置文件

| 文件 | 说明 |
|-----|------|
| `config/application.yaml` | 主配置文件，包含所有模块配置 |
| `docker-compose.yml` | 本地开发环境依赖服务定义 |
| `pyproject.toml` | Python 项目元数据和工具配置 |

### 核心模型

| 文件 | 说明 |
|-----|------|
| `src/models/alert.py` | 告警数据模型定义 |
| `src/models/analysis.py` | 分析结果数据模型定义 |
| `src/web/models.py` | API 请求/响应 Pydantic 模型 |

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
docker-compose up -d

# 运行单元测试
pytest tests/unit -v

# 运行特定测试
pytest tests/unit/test_agent/test_alert_processor.py::test_process_alert -v

# 查看 Langfuse UI
open http://localhost:3000

# 查看 API 文档
open http://localhost:8000/docs
```
