# LangOps - AI 智能化运维平台

> 基于 Langfuse 的云原生智能运维解决方案

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Langfuse](https://img.shields.io/badge/Langfuse-2.0+-orange.svg)](https://langfuse.com/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## 🎯 项目定位

LangOps 是一个开源的 AI 智能化运维平台，专注于：

- ☁️ **云资源巡检**：阿里云 ECS、RDS、SLB 等资源监控与分析
- 🚢 **Kubernetes 巡检**：K8s 集群健康度、Pod 状态、性能分析
- 🧠 **智能根因分析**：利用 LLM 自动分析告警根因
- 📚 **知识沉淀**：故障案例自动归档，支持 RAG 检索

## ✨ 核心特性

| 特性 | 描述 | 价值 |
|-----|------|------|
| 🤖 **智能 RCA** | 多维度数据聚合 + LLM 推理 | 减少 MTTR 50%+ |
| 🔍 **RAG 知识库** | 向量检索历史案例 | 经验复用，新人快速上手 |
| 💬 **自然语言查询** | NL2PromQL，问即所得 | 降低运维门槛 |
| 📊 **全链路观测** | Langfuse 追踪每个 AI 决策 | 可解释、可优化 |
| 🔔 **智能通知** | 飞书/钉钉/Slack 集成 | 及时触达 |

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LangOps 分层架构                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│   │    Web UI    │    │   告警通知   │    │   API 服务   │                  │
│   │   (React)    │    │ (飞书/钉钉)  │    │  (FastAPI)   │                  │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│          │                    │                   │                          │
│          └────────────────────┼───────────────────┘                          │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     AI Agent Core (智能层)                          │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │   根因分析   │  │   知识检索   │  │   修复建议   │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                     数据层 (Data Layer)                             │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │   Langfuse   │  │  Vector DB   │  │    Redis     │              │   │
│   │  │  (观测中枢)   │  │(ChromaDB)   │  │   (缓存)     │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                               │                                              │
│                               ▼                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                   接入层 (Integration)                              │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │   │
│   │  │  Prometheus  │  │  阿里云 CMS  │  │  Kubernetes  │              │   │
│   │  └──────────────┘  └──────────────┘  └──────────────┘              │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Docker & Docker Compose
- Kubernetes 集群（可选）
- OpenAI API Key 或其他 LLM 服务

### 安装部署

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/langops.git
cd langops

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填写必要的配置

# 3. 启动依赖服务（Langfuse, ChromaDB, Redis）
docker-compose up -d

# 4. 安装 Python 依赖
pip install -r requirements.txt

# 5. 启动服务
python -m langops.server
```

### 配置文件

```yaml
# config/application.yaml
langops:
  langfuse:
    host: "http://localhost:3000"
    public_key: "${LANGFUSE_PUBLIC_KEY}"
    secret_key: "${LANGFUSE_SECRET_KEY}"
  
  llm:
    # OpenAI（默认）
    provider: "openai"
    model: "gpt-4"
    api_key: "${OPENAI_API_KEY}"
    # 或使用 OpenAI 兼容接口的模型（Qwen / DeepSeek 等）
    # model: "qwen-plus"  # 通义千问
    # model: "deepseek-chat"  # DeepSeek
    # base_url: "https://api.deepseek.com/v1"  # DeepSeek
    # base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 通义千问
  
  collectors:
    prometheus:
      url: "http://prometheus:9090"
      # auth:  # Prometheus 需要认证时启用
      #   type: "basic"  # basic 或 bearer
      #   username: "${PROMETHEUS_USER}"
      #   password: "${PROMETHEUS_PASSWORD}"
    aliyun:
      access_key_id: "${ALIYUN_ACCESS_KEY_ID}"
      access_key_secret: "${ALIYUN_ACCESS_KEY_SECRET}"
      region: "${ALIYUN_REGION}"  # 如 "cn-hangzhou"
```

### 使用 Qwen / DeepSeek

LangOps 基于 LangChain 的 OpenAI 兼容接口，支持所有提供 OpenAI API 兼容端点的 LLM 服务。

**通义千问（Qwen）配置示例：**

```yaml
langops:
  llm:
    provider: "openai"
    model: "qwen-plus"  # 或 qwen-turbo, qwen-max 等
    api_key: "${DASHSCOPE_API_KEY}"
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

**DeepSeek 配置示例：**

```yaml
langops:
  llm:
    provider: "openai"
    model: "deepseek-chat"  # 或 deepseek-coder 等
    api_key: "${DEEPSEEK_API_KEY}"
    base_url: "https://api.deepseek.com/v1"
```

环境变量示例：

```bash
# 通义千问
export DASHSCOPE_API_KEY="sk-xxxxxxxx"

# DeepSeek
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
```

## 📖 使用指南

### 1. 接收告警

```bash
# 发送测试告警
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CPU使用率过高",
    "description": "order-service Pod CPU使用率超过90%",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "kubernetes",
      "namespace": "production",
      "pod_name": "order-service-xxx"
    }
  }'
```

### 2. 自然语言查询

```bash
# 查询过去24小时的性能问题
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "过去24小时哪些服务的CPU使用率超过80%？"
  }'
```

### 3. 查看分析结果

访问 Langfuse UI: http://localhost:3000

查看完整的 Trace 链路：
- 数据收集耗时
- LLM 调用详情
- Token 消耗
- 分析结果

## 📁 项目结构

```
LangOps/
├── docs/                       # 文档
│   ├── architecture/           # 架构文档
│   ├── api/                    # API 文档
│   └── deployment/             # 部署文档
├── src/                        # 源代码
│   ├── agent/                  # AI Agent 核心
│   │   ├── alert_processor.py  # 告警处理器
│   │   ├── rca_engine.py       # 根因分析引擎
│   │   └── suggestion_engine.py # 建议生成引擎
│   ├── collectors/             # 数据采集器
│   │   ├── prometheus_collector.py
│   │   ├── aliyun_collector.py
│   │   └── k8s_collector.py
│   ├── knowledge/              # 知识库
│   │   ├── vector_store.py     # 向量存储
│   │   └── case_manager.py     # 案例管理
│   ├── web/                    # Web 服务
│   │   ├── api.py              # FastAPI 路由
│   │   └── models.py           # 数据模型
│   └── models/                 # 核心数据模型
│       ├── alert.py
│       └── analysis.py
├── tests/                      # 测试
├── config/                     # 配置文件
├── scripts/                    # 工具脚本
├── deployment/                 # K8s 部署文件
├── docker-compose.yml          # 本地开发环境
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明
```

## 🔧 核心组件

### AI Agent

```python
from langops.agent import AlertProcessor

# 初始化处理器
processor = AlertProcessor(
    langfuse=langfuse_client,
    llm=openai_client,
    vector_store=chroma_store
)

# 处理告警
result = await processor.process_alert(alert)

print(f"根因: {result.root_cause.description}")
print(f"置信度: {result.root_cause.confidence}")
print(f"建议: {result.suggestion.summary}")
```

### 向量知识库

```python
from langops.knowledge import VectorStore

# 添加案例
await store.add_case(FailureCase(
    title="MySQL 连接数耗尽",
    description="数据库连接池耗尽导致服务不可用",
    root_cause="连接未正确释放",
    solution="调整连接池配置，添加连接超时"
))

# 搜索相似案例
cases = await store.search(
    query="数据库连接问题",
    top_k=3
)
```

## 📊 监控指标

LangOps 暴露了以下 Prometheus 指标：

```
# 告警处理数量
langops_alerts_processed_total{category="resource", severity="critical"}

# 分析耗时
langops_analysis_duration_seconds{stage="rca"}

# LLM Token 消耗
langops_llm_tokens_total{model="gpt-4", operation="rca"}

# 知识库案例数
langops_knowledge_cases_total{category="database"}
```

## 🛣️ 路线图

### Phase 1: MVP (2-4 周)

- [x] Prometheus 数据采集
- [x] 基础根因分析
- [x] Langfuse 集成
- [x] Webhook 告警接收
- [ ] 飞书通知

### Phase 2: 增强 (4-6 周)

- [ ] 阿里云 CMS 集成
- [ ] RAG 知识库
- [ ] 自然语言查询
- [ ] Web UI
- [ ] JIRA 工单集成

### Phase 3: 智能化 (6-8 周)

- [ ] 预测性运维
- [ ] 告警降噪
- [ ] 自动修复
- [ ] 多租户支持

## 🤝 贡献指南

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与项目。

### 开发流程

```bash
# 1. Fork 并克隆仓库
git clone https://github.com/your-username/langops.git

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 3. 安装开发依赖
pip install -r requirements-dev.txt

# 4. 创建分支
git checkout -b feature/your-feature

# 5. 提交更改
git commit -m "feat: add your feature"

# 6. 推送并创建 PR
git push origin feature/your-feature
```

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 🙏 致谢

- [Langfuse](https://langfuse.com/) - LLM 可观测性平台
- [FastAPI](https://fastapi.tiangolo.com/) - 现代 Web 框架
- [ChromaDB](https://www.trychroma.com/) - 向量数据库

---

<p align="center">
  Made with ❤️ by LangOps Team
</p>
