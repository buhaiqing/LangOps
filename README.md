# LangOps - AI 智能化运维平台

> 基于 Langfuse 的云原生智能运维解决方案

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Langfuse](https://img.shields.io/badge/Langfuse-4.x-orange.svg)](https://langfuse.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## 🎯 项目定位

LangOps 是一个开源的 AI 智能化运维平台，专注于：

- ☁️ **云资源巡检**：阿里云 ECS、RDS 等指标采集（CMS）
- 🚢 **Kubernetes 巡检**：K8s 集群健康度、Pod 状态、性能分析
- 🧠 **智能根因分析**：利用 LLM 自动分析告警根因
- 📚 **知识沉淀**：故障案例归档与向量检索（RAG）

## ✨ 核心特性

| 特性 | 状态 | 描述 |
|-----|------|------|
| 🤖 **智能 RCA** | ✅ MVP | 多维度数据聚合 + LLM 推理 |
| 📊 **全链路观测** | ✅ MVP | Langfuse 追踪告警分析流水线 |
| 🔍 **RAG 知识库** | ✅ MVP | ChromaDB 向量检索历史案例 |
| 📡 **Prometheus 采集** | ✅ MVP | K8s Pod 指标采集 |
| 🌐 **告警 API** | ✅ MVP | FastAPI `POST /api/v1/alerts` |
| 💬 **自然语言查询** | ✅ | NL2PromQL + Prometheus 执行 |
| 🔔 **智能通知** | ✅ | 飞书/钉钉 Webhook |
| 🖥️ **Web UI** | ✅ | `/ui` 管理界面 |

## 📦 MVP 实现进度

| 模块 | 说明 | 状态 |
|------|------|------|
| `core` | 配置、日志、异常 | ✅ |
| `models` | Alert、AnalysisResult 等 Pydantic 模型 | ✅ |
| `collectors` | Prometheus 采集器（K8s 指标） | ✅ |
| `agent` | RCAEngine、AlertProcessor、提示词模板 | ✅ |
| `knowledge` | ChromaDB VectorStore | ✅ |
| `web` | FastAPI 应用与告警 API | ✅ |
| `server` | 统一启动入口 `server.py` | ✅ Task 9 |
| `integration` | 端到端集成测试 | ✅ |
| `scripts` | 知识库初始化脚本 | ✅ |

开发规范见 [AGENTS.md](AGENTS.md)，实现计划见 [docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md](docs/superpowers/plans/2026-06-25-langops-mvp-implementation.md)。

## 🏗️ 架构概览

```
告警 Webhook / API
        │
        ▼
┌───────────────────┐     ┌───────────────────┐
│  FastAPI (web)    │────▶│  AlertProcessor   │
└───────────────────┘     └─────────┬─────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Prometheus      │       │  RCAEngine      │       │  VectorStore    │
│ Collector       │       │  (OpenAI API)   │       │  (ChromaDB)     │
└─────────────────┘       └─────────────────┘       └─────────────────┘
                                    │
                                    ▼
                          ┌─────────────────┐
                          │  Langfuse       │
                          │  (全链路 Trace)  │
                          └─────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Docker & Docker Compose
- OpenAI API Key（或兼容接口）
- Langfuse、ChromaDB（通过 docker-compose 启动）

### 安装部署

```bash
# 1. 克隆仓库
git clone https://github.com/bohaiqing/LangOps.git
cd LangOps

# 2. 配置环境变量
cp config/.env.example .env
# 必填：LLM_API_KEY、LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY

# 3. 启动依赖服务（Langfuse、ChromaDB、Redis、Postgres）
docker compose up -d

# 4. 创建虚拟环境并安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 5. 初始化知识库（需 ChromaDB 已启动）
python scripts/init_knowledge.py

# 6. 启动 API 服务
python -m langops.server

# 7. 打开 Web 管理界面
open http://localhost:8000/ui
```

### 环境变量（`.env`）

```bash
# LLM
LLM_API_KEY=sk-your-openai-api-key
LLM_MODEL=gpt-4

# Langfuse
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-your-public-key
LANGFUSE_SECRET_KEY=sk-your-secret-key

# Prometheus（K8s 指标采集）
PROMETHEUS_URL=http://localhost:9090

# ChromaDB 向量库
VECTOR_HOST=localhost
VECTOR_PORT=8001

# 阿里云 CMS（可选，用于 ECS/RDS 指标采集）
ALIYUN_ACCESS_KEY_ID=sk-your-access-key
ALIYUN_ACCESS_KEY_SECRET=your-secret-key
ALIYUN_REGION=cn-hangzhou
ALIYUN_CMS_ENDPOINT=metrics.aliyuncs.com

# 通知（告警分析完成后推送）
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxxxx
```

完整模板见 [config/.env.example](config/.env.example) 与根目录 [.env.example](.env.example)。

### 验证安装

```bash
# 健康检查
curl http://localhost:8000/health

# API 文档
open http://localhost:8000/docs

# Web 管理界面
open http://localhost:8000/ui

# 运行测试
pytest tests/ -q
```

## 📖 API 使用

### 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/api/v1/alerts/health` | 告警模块健康检查 |
| POST | `/api/v1/alerts` | 接收告警并触发 AI 分析 |
| POST | `/api/v1/query` | 自然语言查询（NL2PromQL） |
| POST | `/api/v1/predict` | 容量趋势预测（预测性运维） |
| GET | `/ui` | Web 管理界面 |
| GET | `/docs` | Swagger API 文档 |

### 发送测试告警

```bash
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CPU使用率过高",
    "description": "order-service Pod CPU使用率超过90%",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "kubernetes",
      "system": "prod-cluster",
      "namespace": "production",
      "pod_name": "order-service-abc123"
    },
    "metric_data": {
      "cpu_usage_percent": 95.5
    }
  }'
```

成功时返回 `AnalysisResponse`：`success`、`data`（含 `trace_id`、`root_cause`、`suggestion`）或 `error`。

配置 `FEISHU_WEBHOOK` / `DINGTALK_WEBHOOK` 后，分析成功会自动推送通知。

### 自然语言查询（NL2PromQL）

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "过去1小时哪些 Pod CPU 使用率最高？"}'
```

返回 `answer`（解读）、`promql`（生成的查询）及原始 `data`。

### 容量预测（预测性运维）

```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "resource_type": "kubernetes",
    "namespace": "production",
    "pod_name": "order-service-abc123",
    "horizon_hours": 24
  }'
```

返回 `overall_risk`、`forecasts`（趋势/预测值）及 `recommendation`。告警分析流程中也会自动写入 `impact_prediction` 字段。

### 查看 Langfuse Trace

访问 http://localhost:3000 ，使用响应中的 `trace_id` 检索完整分析链路。

## 📁 项目结构

```
LangOps/
├── AGENTS.md                   # AI Agent 开发规范
├── config/
│   └── .env.example            # 环境变量模板（LLM_ / LANGFUSE_ 前缀）
├── docker-compose.yml          # Langfuse、ChromaDB、Redis、Postgres
├── docs/
│   ├── architecture/           # 系统设计文档
│   └── examples/
│       └── sample-alert.json   # API 请求示例
├── scripts/
│   └── init_knowledge.py       # 知识库初始化
├── src/langops/                # Python 包
│   ├── core/                   # 配置、日志、异常
│   ├── models/                 # Alert、AnalysisResult 等
│   ├── collectors/             # Prometheus 采集器
│   ├── agent/                  # AlertProcessor、RCAEngine、PredictiveEngine
│   ├── services/               # 飞书/钉钉通知
│   ├── knowledge/              # ChromaDB VectorStore
│   └── web/                    # FastAPI 应用
│       ├── static/             # Web UI 静态资源
│       ├── main.py
│       ├── dependencies.py
│       └── api/alerts.py
├── tests/
│   ├── unit/                   # 单元测试
│   └── integration/            # 集成测试
├── pyproject.toml
├── requirements.txt
└── README.md
```

## 🔧 核心组件示例

### AlertProcessor 流水线

```python
from langfuse import Langfuse
from langops.agent import AlertProcessor, RCAEngine
from langops.collectors import PrometheusCollector
from langops.knowledge import VectorStore
from langops.models import Alert, AlertSeverity, AlertCategory, AlertSource

processor = AlertProcessor(
    langfuse=Langfuse(),
    rca_engine=RCAEngine(api_key="sk-...", model="gpt-4"),
    vector_store=VectorStore(host="localhost", port=8001),
    prometheus_collector=PrometheusCollector({"url": "http://localhost:9090"}),
)

alert = Alert(
    id="alert-001",
    title="CPU使用率过高",
    description="Pod CPU > 90%",
    severity=AlertSeverity.CRITICAL,
    category=AlertCategory.RESOURCE,
    source=AlertSource(
        type="kubernetes",
        system="prod-cluster",
        namespace="production",
        pod_name="order-pod",
    ),
)

result = await processor.process(alert)
print(result.trace_id, result.root_cause.description, result.suggestion.summary)
```

### 向量知识库

```python
from langops.knowledge import VectorStore

store = VectorStore(host="localhost", port=8001)

case_id = await store.add_case(
    title="MySQL 连接数耗尽",
    description="数据库连接池耗尽导致服务不可用",
    category="resource",
    service="order-db",
    root_cause="连接未正确释放",
    solution="调整连接池配置，添加连接超时",
)

results = await store.search(query="数据库连接问题", top_k=3)
```

## 🛠️ 开发

### 本地命令

```bash
source venv/bin/activate
pip install -e ".[dev]"

# 测试
pytest tests/ -v

# 代码检查
black src/ tests/
isort src/ tests/
mypy src/langops
```

### Git Worktree 工作流

每个 MVP Task 在独立 worktree + 功能分支开发，完成后合并 `main` 并推送。详见 [AGENTS.md §5.1](AGENTS.md#51-实施-mvp-计划)。

```bash
git checkout main && git pull
git worktree add .worktrees/feat-taskN-xxx -b feat/taskN-xxx
cd .worktrees/feat-taskN-xxx
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -q
```

## 🛣️ 路线图

### Phase 1: MVP（已完成）

- [x] 项目脚手架与依赖（pyproject、docker-compose）
- [x] 核心配置与 Pydantic 数据模型
- [x] Prometheus K8s 指标采集
- [x] LLM 根因分析与修复建议（RCAEngine）
- [x] ChromaDB 知识库检索
- [x] AlertProcessor + Langfuse 追踪
- [x] FastAPI 告警 API
- [x] 服务启动入口（`server.py`）
- [x] 端到端集成测试
- [x] 知识库初始化脚本

### Phase 2: 增强（已完成）

- [x] 阿里云 CMS 集成
- [x] 自然语言查询（NL2PromQL）
- [x] 飞书/钉钉通知
- [x] Web UI

### Phase 3: 智能化

- [x] 预测性运维
- [ ] 告警降噪
- [ ] 自动修复建议执行（需人工审批）

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🙏 致谢

- [Langfuse](https://langfuse.com/) - LLM 可观测性平台
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架
- [ChromaDB](https://www.trychroma.com/) - 向量数据库
