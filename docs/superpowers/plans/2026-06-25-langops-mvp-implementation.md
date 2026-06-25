# LangOps MVP 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 LangOps MVP 版本，实现核心告警处理流程：接收告警 → 数据采集 → LLM 根因分析 → 输出结果，集成 Langfuse 全链路追踪。

**Architecture:** FastAPI 后端 + 模块化 Agent 设计，支持 Prometheus 和阿里云 CMS 数据源，使用 ChromaDB 作为向量存储，Langfuse 作为观测中枢。

**Tech Stack:** Python 3.11+, FastAPI, Langfuse, OpenAI API, ChromaDB, Redis, Docker Compose

**Estimated Duration:** 2-3 周 (按顺序执行，无并行任务依赖)

---

## 文件结构规划

```
src/
├── __init__.py
├── core/                       # 核心基础设施
│   ├── __init__.py
│   ├── config.py              # Pydantic Settings 配置管理
│   ├── exceptions.py          # 自定义异常类
│   └── logging.py             # 日志配置
├── models/                     # 数据模型 (Pydantic)
│   ├── __init__.py
│   ├── alert.py               # Alert, AlertSource, AlertSeverity
│   └── analysis.py            # AnalysisResult, RootCause, etc.
├── collectors/                 # 数据采集器
│   ├── __init__.py
│   ├── base.py                # BaseCollector 抽象基类
│   └── prometheus_collector.py # Prometheus 实现
├── agent/                      # AI Agent 核心
│   ├── __init__.py
│   ├── alert_processor.py     # 主处理器 (带 @observe 装饰器)
│   ├── rca_engine.py          # 根因分析引擎
│   └── prompts.py             # LLM 提示词模板
├── knowledge/                  # 知识库 (简化版)
│   ├── __init__.py
│   └── vector_store.py        # ChromaDB 封装
├── web/                        # Web 服务
│   ├── __init__.py
│   ├── main.py                # FastAPI 应用
│   ├── api/
│   │   ├── __init__.py
│   │   └── alerts.py          # 告警相关路由
│   └── dependencies.py        # FastAPI 依赖注入
tests/
├── conftest.py                # pytest fixtures
├── unit/
│   ├── test_core/
│   ├── test_models/
│   ├── test_collectors/
│   └── test_agent/
└── integration/
    └── test_api/
config/
├── application.yaml           # 主配置
└── .env.example               # 环境变量模板
docker-compose.yml             # 依赖服务
requirements.txt               # Python 依赖
pytest.ini                     # pytest 配置
```

---

## Task 1: 项目初始化与依赖配置

**Files:**
- Create: `pyproject.toml`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `docker-compose.yml`

**Context:** 建立 Python 项目基础结构，配置开发环境所需的依赖服务 (Langfuse, ChromaDB, Redis)。

- [ ] **Step 1.1: 创建 pyproject.toml**

```toml
[project]
name = "langops"
version = "0.1.0"
description = "AI-powered intelligent operations platform"
requires-python = ">=3.11"
dependencies = [
    # Web Framework
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.9",
    
    # Configuration
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "pyyaml>=6.0.1",
    
    # Observability
    "langfuse>=2.20.0",
    "prometheus-client>=0.19.0",
    
    # Data & ML
    "chromadb>=0.4.22",
    "openai>=1.12.0",
    "numpy>=1.26.0",
    
    # HTTP Clients
    "aiohttp>=3.9.0",
    "httpx>=0.26.0",
    
    # Utilities
    "structlog>=24.1.0",
    "tenacity>=8.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "black>=24.1.0",
    "isort>=5.13.0",
    "flake8>=7.0.0",
    "mypy>=1.8.0",
]

[tool.black]
line-length = 100
target-version = ['py311']

[tool.isort]
profile = "black"
line_length = 100

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

- [ ] **Step 1.2: 创建 requirements.txt**

```txt
# Core
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
pydantic-settings>=2.1.0
pyyaml>=6.0.1

# Observability
langfuse>=2.20.0
prometheus-client>=0.19.0

# AI & Vector DB
openai>=1.12.0
chromadb>=0.4.22
numpy>=1.26.0

# HTTP & Async
aiohttp>=3.9.0
httpx>=0.26.0

# Utilities
structlog>=24.1.0
tenacity>=8.2.0
python-multipart>=0.0.9
```

- [ ] **Step 1.3: 创建 docker-compose.yml**

```yaml
version: "3.8"

services:
  langfuse-server:
    image: ghcr.io/langfuse/langfuse:latest
    container_name: langops-langfuse
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/langfuse
      - NEXTAUTH_SECRET=local-dev-secret-change-in-production
      - SALT=local-dev-salt-change-in-production
      - NEXTAUTH_URL=http://localhost:3000
      - TELEMETRY_ENABLED=false
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - langops-network

  postgres:
    image: postgres:15-alpine
    container_name: langops-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=langfuse
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - langops-network

  chromadb:
    image: chromadb/chroma:latest
    container_name: langops-chromadb
    restart: unless-stopped
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/chroma
    environment:
      - IS_PERSISTENT=TRUE
      - PERSIST_DIRECTORY=/chroma/chroma
      - ANONYMIZED_TELEMETRY=FALSE
    networks:
      - langops-network

  redis:
    image: redis:7-alpine
    container_name: langops-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - langops-network

volumes:
  postgres_data:
  chroma_data:
  redis_data:

networks:
  langops-network:
    driver: bridge
```

- [ ] **Step 1.4: 创建 .gitignore**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/
.venv/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Environment variables
.env
.env.local
.env.*.local

# Data files
data/
*.db
*.sqlite3

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db

# Test coverage
.coverage
htmlcov/
.pytest_cache/

# MyPy
.mypy_cache/
.dmypy.json
dmypy.json
```

- [ ] **Step 1.5: 安装依赖并验证**

```bash
cd /Users/bohaiqing/opensource/git/LangOps
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 验证安装
python -c "import fastapi; import langfuse; import chromadb; print('All dependencies installed!')"
```

- [ ] **Step 1.6: 启动依赖服务**

```bash
docker-compose up -d

# 等待服务就绪
sleep 10
docker-compose ps

# 验证 Langfuse
curl http://localhost:3000/api/public/health
```

- [ ] **Step 1.7: Commit**

```bash
git add pyproject.toml requirements.txt docker-compose.yml .gitignore
git commit -m "chore: initialize project with dependencies and docker-compose"
```

---

## Task 2: 核心配置与日志系统

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/config.py`
- Create: `src/core/exceptions.py`
- Create: `src/core/logging.py`
- Create: `config/.env.example`

**Context:** 建立配置管理系统，支持环境变量和 YAML 配置文件，配置结构化日志。

- [ ] **Step 2.1: 创建 src/core/config.py**

```python
"""Configuration management using Pydantic Settings."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM configuration."""
    
    model_config = SettingsConfigDict(env_prefix="LLM_")
    
    provider: str = Field(default="openai", description="LLM provider")
    model: str = Field(default="gpt-4", description="Model name")
    api_key: str = Field(..., description="API key")
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=2000, ge=1)
    timeout: int = Field(default=30, ge=1)


class LangfuseSettings(BaseSettings):
    """Langfuse configuration."""
    
    model_config = SettingsConfigDict(env_prefix="LANGFUSE_")
    
    host: str = Field(default="http://localhost:3000")
    public_key: str = Field(..., description="Public key")
    secret_key: str = Field(..., description="Secret key")
    release: Optional[str] = Field(default=None)


class PrometheusSettings(BaseSettings):
    """Prometheus configuration."""
    
    model_config = SettingsConfigDict(env_prefix="PROMETHEUS_")
    
    url: str = Field(default="http://localhost:9090")
    timeout: int = Field(default=10)
    scrape_interval: int = Field(default=15)


class VectorStoreSettings(BaseSettings):
    """Vector store configuration."""
    
    model_config = SettingsConfigDict(env_prefix="VECTOR_")
    
    type: str = Field(default="chromadb")
    host: str = Field(default="localhost")
    port: int = Field(default=8001)
    collection_name: str = Field(default="ops_knowledge")
    persist_directory: Optional[str] = Field(default=None)


class RedisSettings(BaseSettings):
    """Redis configuration."""
    
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    url: str = Field(default="redis://localhost:6379")


class Settings(BaseSettings):
    """Application settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Application
    app_name: str = Field(default="LangOps")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    # Server
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=1)
    
    # Sub-configs
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    prometheus: PrometheusSettings = Field(default_factory=PrometheusSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
```

- [ ] **Step 2.2: 创建 src/core/exceptions.py**

```python
"""Custom exceptions for LangOps."""


class LangOpsException(Exception):
    """Base exception for LangOps."""
    pass


class ConfigurationError(LangOpsException):
    """Configuration error."""
    pass


class CollectorError(LangOpsException):
    """Data collector error."""
    
    def __init__(self, message: str, source: str = None):
        super().__init__(message)
        self.source = source


class LLMError(LangOpsException):
    """LLM service error."""
    
    def __init__(self, message: str, model: str = None):
        super().__init__(message)
        self.model = model


class VectorStoreError(LangOpsException):
    """Vector store error."""
    pass


class AnalysisError(LangOpsException):
    """Analysis processing error."""
    pass
```

- [ ] **Step 2.3: 创建 src/core/logging.py**

```python
"""Structured logging configuration."""

import sys
from typing import Any, Dict

import structlog

from langops.core.config import settings


def configure_logging() -> None:
    """Configure structured logging."""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if not settings.debug else structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    import logging
    
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger."""
    return structlog.get_logger(name)
```

- [ ] **Step 2.4: 创建 src/core/__init__.py**

```python
"""Core module."""

from langops.core.config import Settings, get_settings, settings
from langops.core.exceptions import (
    AnalysisError,
    CollectorError,
    ConfigurationError,
    LangOpsException,
    LLMError,
    VectorStoreError,
)
from langops.core.logging import configure_logging, get_logger

__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "LangOpsException",
    "ConfigurationError",
    "CollectorError",
    "LLMError",
    "VectorStoreError",
    "AnalysisError",
    "configure_logging",
    "get_logger",
]
```

- [ ] **Step 2.5: 创建 config/.env.example**

```bash
# LangOps Environment Configuration
# Copy this file to .env and fill in your values

# Application
DEBUG=false
LOG_LEVEL=INFO

# LLM (OpenAI)
LLM_API_KEY=sk-your-openai-api-key
LLM_MODEL=gpt-4
LLM_TEMPERATURE=0.2

# Langfuse
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-your-public-key
LANGFUSE_SECRET_KEY=sk-your-secret-key

# Prometheus
PROMETHEUS_URL=http://localhost:9090

# Vector Store (ChromaDB)
VECTOR_HOST=localhost
VECTOR_PORT=8001

# Redis
REDIS_URL=redis://localhost:6379

# Aliyun (Optional for MVP)
# ALIYUN_ACCESS_KEY_ID=your-access-key
# ALIYUN_ACCESS_KEY_SECRET=your-secret-key
```

- [ ] **Step 2.6: 验证配置加载**

```bash
cd /Users/bohaiqing/opensource/git/LangOps
source venv/bin/activate

# 创建测试脚本
cat > test_config.py << 'EOF'
import os
os.chdir('/Users/bohaiqing/opensource/git/LangOps')

import sys
sys.path.insert(0, 'src')

from langops.core.config import settings
print(f"App name: {settings.app_name}")
print(f"Log level: {settings.log_level}")
print(f"LLM model: {settings.llm.model}")
print("Config loaded successfully!")
EOF

python test_config.py
rm test_config.py
```

- [ ] **Step 2.7: Commit**

```bash
git add src/core/ config/.env.example
git commit -m "feat(core): add configuration management and logging"
```

---

## Task 3: 数据模型定义

**Files:**
- Create: `src/models/__init__.py`
- Create: `src/models/alert.py`
- Create: `src/models/analysis.py`

**Context:** 定义核心业务数据模型，使用 Pydantic v2 进行数据验证和序列化。

- [ ] **Step 3.1: 创建 src/models/alert.py**

```python
"""Alert data models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertCategory(str, Enum):
    """Alert categories."""
    RESOURCE = "resource"           # CPU, memory, disk
    AVAILABILITY = "availability"   # Service down, pod crash
    PERFORMANCE = "performance"     # Latency, throughput
    SECURITY = "security"           # Security events


class AlertSource(BaseModel):
    """Alert source information."""
    
    type: str = Field(..., description="Source type: prometheus, aliyun, kubernetes")
    system: str = Field(..., description="System or cluster name")
    service: Optional[str] = Field(default=None, description="Service name")
    namespace: Optional[str] = Field(default=None, description="K8s namespace")
    pod_name: Optional[str] = Field(default=None, description="Pod name")
    instance_id: Optional[str] = Field(default=None, description="Cloud instance ID")
    resource_type: Optional[str] = Field(default=None, description="Resource type: ecs, rds, slb")
    
    model_config = {"extra": "allow"}


class Alert(BaseModel):
    """Standardized alert model."""
    
    id: str = Field(..., description="Unique alert identifier")
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Alert description")
    severity: AlertSeverity = Field(..., description="Alert severity")
    category: AlertCategory = Field(..., description="Alert category")
    source: AlertSource = Field(..., description="Alert source")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Alert timestamp")
    metric_data: Dict[str, Any] = Field(default_factory=dict, description="Raw metric data")
    log_snippets: List[str] = Field(default_factory=list, description="Related log snippets")
    related_events: List[str] = Field(default_factory=list, description="Related event IDs")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    
    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v):
        """Normalize severity string to enum."""
        if isinstance(v, str):
            v = v.lower()
            mapping = {
                "critical": AlertSeverity.CRITICAL,
                "high": AlertSeverity.HIGH,
                "medium": AlertSeverity.MEDIUM,
                "low": AlertSeverity.LOW,
                "info": AlertSeverity.INFO,
                "warning": AlertSeverity.MEDIUM,  # Map warning to medium
            }
            return mapping.get(v, AlertSeverity.INFO)
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "alert-001",
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
                    "cpu_usage_percent": 95.5,
                    "memory_usage_percent": 78.2
                }
            }
        }
    }


class AlertCreate(BaseModel):
    """Alert creation request."""
    
    title: str
    description: str
    severity: AlertSeverity
    category: AlertCategory
    source: AlertSource
    metric_data: Dict[str, Any] = Field(default_factory=dict)
    log_snippets: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)


class AlertContext(BaseModel):
    """Enriched alert context for analysis."""
    
    alert: Alert
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Collected metrics")
    logs: List[str] = Field(default_factory=list, description="Collected logs")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="Related events")
    time_range_minutes: int = Field(default=30, description="Context time range")
```

- [ ] **Step 3.2: 创建 src/models/analysis.py**

```python
"""Analysis result models."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RootCause(BaseModel):
    """Root cause analysis result."""
    
    category: str = Field(..., description="Root cause category")
    description: str = Field(..., description="Detailed description")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence")
    related_metrics: List[str] = Field(default_factory=list, description="Related metrics")
    impact_analysis: Optional[str] = Field(default=None, description="Impact analysis")


class SimilarCase(BaseModel):
    """Similar historical case."""
    
    case_id: str = Field(..., description="Case identifier")
    similarity_score: float = Field(..., ge=0, le=1, description="Similarity score")
    title: str = Field(..., description="Case title")
    root_cause: str = Field(..., description="Root cause summary")
    solution: str = Field(..., description="Solution applied")
    resolution_time: Optional[int] = Field(default=None, description="Resolution time in minutes")


class RemediationSuggestion(BaseModel):
    """Remediation suggestion."""
    
    summary: str = Field(..., description="Suggestion summary")
    steps: List[str] = Field(default_factory=list, description="Action steps")
    commands: List[str] = Field(default_factory=list, description="CLI commands")
    risks: List[str] = Field(default_factory=list, description="Potential risks")
    rollback_plan: Optional[str] = Field(default=None, description="Rollback plan")
    estimated_time: str = Field(default="unknown", description="Estimated fix time")


class AnalysisResult(BaseModel):
    """Complete analysis result."""
    
    alert_id: str = Field(..., description="Reference to original alert")
    trace_id: str = Field(..., description="Langfuse trace ID")
    root_cause: RootCause = Field(..., description="Root cause analysis")
    similar_cases: List[SimilarCase] = Field(default_factory=list, description="Similar cases")
    suggestion: RemediationSuggestion = Field(..., description="Remediation suggestion")
    impact_prediction: Dict[str, Any] = Field(default_factory=dict, description="Impact prediction")
    processing_time_seconds: float = Field(..., description="Total processing time")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Analysis timestamp")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_id": "alert-001",
                "trace_id": "trace-abc123",
                "root_cause": {
                    "category": "资源不足",
                    "description": "Pod CPU 资源不足，导致性能下降",
                    "confidence": 0.92,
                    "evidence": ["CPU使用率95%", "无CPU limit配置"]
                },
                "suggestion": {
                    "summary": "增加 Pod CPU limit 或扩容",
                    "steps": ["检查当前资源配置", "修改 deployment CPU limit"],
                    "commands": ["kubectl set resources deployment/order-service --limits=cpu=1000m"]
                }
            }
        }
    }


class AnalysisResponse(BaseModel):
    """API response for analysis."""
    
    success: bool = Field(..., description="Whether analysis was successful")
    data: Optional[AnalysisResult] = Field(default=None, description="Analysis result")
    error: Optional[str] = Field(default=None, description="Error message if failed")
```

- [ ] **Step 3.3: 创建 src/models/__init__.py**

```python
"""Data models module."""

from langops.models.alert import (
    Alert,
    AlertCategory,
    AlertContext,
    AlertCreate,
    AlertSeverity,
    AlertSource,
)
from langops.models.analysis import (
    AnalysisResponse,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
    SimilarCase,
)

__all__ = [
    "Alert",
    "AlertCategory",
    "AlertContext",
    "AlertCreate",
    "AlertSeverity",
    "AlertSource",
    "AnalysisResponse",
    "AnalysisResult",
    "RemediationSuggestion",
    "RootCause",
    "SimilarCase",
]
```

- [ ] **Step 3.4: 验证模型**

```bash
cat > test_models.py << 'EOF'
import sys
sys.path.insert(0, 'src')

from langops.models import Alert, AlertCreate, AlertSeverity, AlertCategory, AlertSource

# 测试 Alert 创建
alert = Alert(
    id="test-001",
    title="Test Alert",
    description="Test description",
    severity=AlertSeverity.HIGH,
    category=AlertCategory.RESOURCE,
    source=AlertSource(type="prometheus", system="prod")
)
print(f"Alert created: {alert.id}, severity: {alert.severity}")

# 测试从字符串解析 severity
alert2 = Alert(
    id="test-002",
    title="Test Alert 2",
    description="Test",
    severity="CRITICAL",  # 字符串输入
    category="performance",  # 字符串输入
    source={"type": "k8s", "system": "cluster-1"}
)
print(f"Alert2 severity: {alert2.severity}, category: {alert2.category}")
print("Models validated successfully!")
EOF

python test_models.py
rm test_models.py
```

- [ ] **Step 3.5: Commit**

```bash
git add src/models/
git commit -m "feat(models): add alert and analysis data models"
```

---

## Task 4: Prometheus 数据采集器

**Files:**
- Create: `src/collectors/__init__.py`
- Create: `src/collectors/base.py`
- Create: `src/collectors/prometheus_collector.py`

**Context:** 实现 Prometheus 指标采集器，支持查询 Pod/Service 相关指标。

- [ ] **Step 4.1: 创建 src/collectors/base.py**

```python
"""Base collector interface."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List

from langops.models import Alert, AlertContext


class BaseCollector(ABC):
    """Abstract base class for data collectors."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    @abstractmethod
    async def collect(self, alert: Alert, time_window: timedelta = timedelta(minutes=30)) -> Dict[str, Any]:
        """
        Collect data related to an alert.
        
        Args:
            alert: The alert to collect data for
            time_window: Time window for historical data
            
        Returns:
            Dictionary of collected data
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the collector is healthy."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Collector name."""
        pass
```

- [ ] **Step 4.2: 创建 src/collectors/prometheus_collector.py**

```python
"""Prometheus metrics collector."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from langops.collectors.base import BaseCollector
from langops.core import get_logger
from langops.models import Alert

logger = get_logger(__name__)


class PrometheusCollector(BaseCollector):
    """Collector for Prometheus metrics."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config.get("url", "http://localhost:9090")
        self.timeout = config.get("timeout", 10)
        self._session: Optional[aiohttp.ClientSession] = None
    
    @property
    def name(self) -> str:
        return "prometheus"
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def health_check(self) -> bool:
        """Check Prometheus health."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/-/healthy") as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning("Prometheus health check failed", error=str(e))
            return False
    
    async def collect(self, alert: Alert, time_window: timedelta = timedelta(minutes=30)) -> Dict[str, Any]:
        """
        Collect Prometheus metrics for an alert.
        
        For Kubernetes alerts, collects pod metrics.
        For service alerts, collects service-level metrics.
        """
        results = {}
        
        try:
            if alert.source.type == "kubernetes":
                results = await self._collect_k8s_metrics(alert, time_window)
            else:
                # Generic metric collection
                results = await self._collect_generic_metrics(alert, time_window)
                
        except Exception as e:
            logger.error("Failed to collect Prometheus metrics", 
                        alert_id=alert.id, error=str(e))
            results["error"] = str(e)
        
        return results
    
    async def _collect_k8s_metrics(
        self, 
        alert: Alert, 
        time_window: timedelta
    ) -> Dict[str, Any]:
        """Collect Kubernetes pod metrics."""
        namespace = alert.source.namespace
        pod_name = alert.source.pod_name
        
        if not namespace or not pod_name:
            return {"error": "Missing namespace or pod_name for K8s metrics"}
        
        end_time = datetime.utcnow()
        start_time = end_time - time_window
        
        queries = {
            "cpu_usage": f"""
                sum(rate(container_cpu_usage_seconds_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m])) by (container)
            """,
            "memory_usage": f"""
                container_memory_usage_bytes{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "memory_limit": f"""
                container_spec_memory_limit_bytes{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "restart_count": f"""
                kube_pod_container_status_restarts_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}
            """,
            "network_receive_errors": f"""
                sum(rate(container_network_receive_errors_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m]))
            """,
            "network_transmit_errors": f"""
                sum(rate(container_network_transmit_errors_total{{
                    namespace="{namespace}",
                    pod="{pod_name}"
                }}[5m]))
            """
        }
        
        results = {}
        for metric_name, query in queries.items():
            try:
                data = await self._query_range(query, start_time, end_time)
                results[metric_name] = self._parse_metric_data(data)
            except Exception as e:
                logger.warning(f"Failed to query {metric_name}", error=str(e))
                results[metric_name] = {"error": str(e)}
        
        return results
    
    async def _collect_generic_metrics(
        self, 
        alert: Alert, 
        time_window: timedelta
    ) -> Dict[str, Any]:
        """Collect generic metrics based on alert labels."""
        # Placeholder for generic metric collection
        # Can be extended based on alert source labels
        return {"note": "Generic metric collection not yet implemented"}
    
    async def _query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = "15s"
    ) -> List[Dict]:
        """Execute PromQL range query."""
        session = await self._get_session()
        
        params = {
            "query": query.strip(),
            "start": start.timestamp(),
            "end": end.timestamp(),
            "step": step
        }
        
        url = f"{self.base_url}/api/v1/query_range"
        
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Prometheus query failed: {resp.status} - {text}")
            
            data = await resp.json()
            
            if data.get("status") != "success":
                raise Exception(f"Prometheus error: {data.get('error', 'Unknown')}")
            
            return data.get("data", {}).get("result", [])
    
    def _parse_metric_data(self, result: List[Dict]) -> Dict[str, Any]:
        """Parse Prometheus query result into readable format."""
        if not result:
            return {"status": "no_data"}
        
        parsed = {
            "status": "success",
            "series_count": len(result),
            "series": []
        }
        
        for series in result:
            metric_info = {
                "metric": series.get("metric", {}),
                "values": []
            }
            
            # Convert timestamp-value pairs
            for value in series.get("values", []):
                timestamp, val = value
                metric_info["values"].append({
                    "timestamp": float(timestamp),
                    "value": val
                })
            
            # Add latest value if available
            if metric_info["values"]:
                latest = metric_info["values"][-1]
                metric_info["current_value"] = latest["value"]
                metric_info["current_timestamp"] = latest["timestamp"]
            
            parsed["series"].append(metric_info)
        
        return parsed
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
```

- [ ] **Step 4.3: 创建 src/collectors/__init__.py**

```python
"""Collectors module."""

from langops.collectors.base import BaseCollector
from langops.collectors.prometheus_collector import PrometheusCollector

__all__ = [
    "BaseCollector",
    "PrometheusCollector",
]
```

- [ ] **Step 4.4: 测试 Collector**

```bash
# 创建测试
cat > test_collector.py << 'EOF'
import asyncio
import sys
sys.path.insert(0, 'src')

from langops.collectors import PrometheusCollector
from langops.models import Alert, AlertSource, AlertSeverity, AlertCategory

async def test_collector():
    config = {"url": "http://localhost:9090", "timeout": 5}
    collector = PrometheusCollector(config)
    
    # 测试健康检查
    healthy = await collector.health_check()
    print(f"Prometheus healthy: {healthy}")
    
    # 创建测试告警
    alert = Alert(
        id="test-001",
        title="Test",
        description="Test",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=AlertSource(
            type="kubernetes",
            system="test-cluster",
            namespace="default",
            pod_name="test-pod"
        )
    )
    
    # 测试采集（如果没有 Prometheus，会返回错误）
    try:
        from datetime import timedelta
        data = await collector.collect(alert, timedelta(minutes=5))
        print(f"Collected data keys: {list(data.keys())}")
    except Exception as e:
        print(f"Collection failed (expected if no Prometheus): {e}")
    
    await collector.close()
    print("Collector test completed!")

asyncio.run(test_collector())
EOF

python test_collector.py
rm test_collector.py
```

- [ ] **Step 4.5: Commit**

```bash
git add src/collectors/
git commit -m "feat(collectors): add Prometheus collector with K8s metrics support"
```

---

## Task 5: LLM 提示词模板

**Files:**
- Create: `src/agent/prompts.py`

**Context:** 定义 LLM 提示词模板，用于根因分析和修复建议生成。

- [ ] **Step 5.1: 创建 src/agent/prompts.py**

```python
"""LLM prompt templates for LangOps."""

import json
from typing import Dict, List, Any


# System prompts
SYSTEM_PROMPT_RCA = """你是一个专业的运维专家，擅长分析系统告警并找出根因。

你的任务是：
1. 分析告警信息和相关数据
2. 找出问题的根本原因
3. 提供证据支持你的结论
4. 评估问题的影响范围

输出必须严格遵循 JSON 格式。"""

SYSTEM_PROMPT_REMEDIATION = """你是一个专业的运维专家，擅长提供可操作的修复建议。

你的任务是：
1. 基于根因分析结果，提供具体的修复步骤
2. 提供可执行的命令（如 kubectl、docker 等）
3. 评估修复操作的风险
4. 提供回滚方案

输出必须严格遵循 JSON 格式。"""


def build_rca_prompt(
    alert_title: str,
    alert_description: str,
    severity: str,
    category: str,
    source: Dict[str, Any],
    metrics: Dict[str, Any],
    logs: List[str],
    events: List[Dict]
) -> str:
    """
    Build prompt for root cause analysis.
    
    Args:
        alert_title: Alert title
        alert_description: Alert description
        severity: Alert severity
        category: Alert category
        source: Alert source info
        metrics: Collected metrics
        logs: Related logs
        events: Related events
        
    Returns:
        Formatted prompt string
    """
    # Truncate long content to fit in context window
    max_logs = 10
    logs_str = "\n".join(logs[:max_logs]) if logs else "无相关日志"
    
    max_events = 5
    events_str = json.dumps(events[:max_events], ensure_ascii=False, indent=2) if events else "无相关事件"
    
    # Format metrics for readability
    metrics_str = json.dumps(metrics, ensure_ascii=False, indent=2) if metrics else "无指标数据"
    
    prompt = f"""请分析以下告警的根因：

## 告警信息

- 标题: {alert_title}
- 描述: {alert_description}
- 严重程度: {severity}
- 类别: {category}
- 来源: {json.dumps(source, ensure_ascii=False)}

## 指标数据

```json
{metrics_str}
```

## 相关日志 (最近{max_logs}条)

```
{logs_str}
```

## 相关事件 (最近{max_events}条)

```json
{events_str}
```

## 分析要求

1. 根因分类必须是以下之一：资源不足、配置错误、依赖故障、代码缺陷、外部因素、未知
2. 置信度范围 0-1，基于证据的充分程度
3. 关键证据必须引用具体的数据点
4. 影响分析需说明对业务和系统的影响

## 输出格式

请输出严格的 JSON 格式，不要包含其他内容：

{{
  "root_cause_category": "根因分类",
  "description": "详细的根因描述，2-3句话",
  "confidence": 0.85,
  "key_evidence": ["证据1：具体数据", "证据2：具体数据"],
  "related_metrics": ["关联指标1", "关联指标2"],
  "impact_analysis": "影响范围分析"
}}
"""
    return prompt


def build_remediation_prompt(
    root_cause: Dict[str, Any],
    similar_cases: List[Dict[str, Any]],
    alert_context: Dict[str, Any]
) -> str:
    """
    Build prompt for remediation suggestion.
    
    Args:
        root_cause: Root cause analysis result
        similar_cases: Similar historical cases
        alert_context: Alert context information
        
    Returns:
        Formatted prompt string
    """
    similar_cases_str = ""
    if similar_cases:
        similar_cases_str = "## 历史相似案例\n\n"
        for i, case in enumerate(similar_cases[:3], 1):
            similar_cases_str += f"""案例{i}:
- 标题: {case.get('title', 'N/A')}
- 根因: {case.get('root_cause', 'N/A')}
- 解决方案: {case.get('solution', 'N/A')}
- 解决时间: {case.get('resolution_time', '未知')} 分钟

"""
    else:
        similar_cases_str = "## 历史相似案例\n\n无历史相似案例。\n\n"
    
    prompt = f"""基于以下根因分析结果，提供修复建议：

## 根因分析

- 分类: {root_cause.get('category', 'N/A')}
- 描述: {root_cause.get('description', 'N/A')}
- 置信度: {root_cause.get('confidence', 0)}
- 关键证据: {json.dumps(root_cause.get('evidence', []), ensure_ascii=False)}

{similar_cases_str}
## 告警上下文

- 服务: {alert_context.get('service', 'N/A')}
- 命名空间: {alert_context.get('namespace', 'N/A')}
- 资源类型: {alert_context.get('resource_type', 'N/A')}

## 输出要求

请输出严格的 JSON 格式：

{{
  "summary": "修复建议摘要，1句话",
  "steps": [
    "步骤1：具体操作",
    "步骤2：具体操作"
  ],
  "commands": [
    "可执行的命令1",
    "可执行的命令2"
  ],
  "risks": [
    "风险1及应对措施",
    "风险2及应对措施"
  ],
  "rollback_plan": "如果修复失败，如何回滚（如有）",
  "estimated_time": "预计修复时间，如：10分钟"
}}

注意：
1. commands 中的命令必须是可执行的，优先使用 kubectl 命令
2. 如果无法提供具体命令，commands 可以为空数组
3. risks 必须包含每个风险的应对措施
4. 如果修复不可逆，rollback_plan 填写 "无"
"""
    return prompt


def build_nl_query_prompt(user_query: str, available_metrics: List[str]) -> str:
    """
    Build prompt for natural language to PromQL conversion.
    
    Args:
        user_query: User's natural language query
        available_metrics: List of available metric names
        
    Returns:
        Formatted prompt string
    """
    metrics_str = "\n".join([f"- {m}" for m in available_metrics[:20]])
    
    prompt = f"""将以下自然语言查询转换为 PromQL：

用户查询: {user_query}

可用的指标（部分）：
{metrics_str}

输出 JSON 格式：
{{
  "promql": "生成的 PromQL 查询",
  "time_range": "时间范围，如：1h, 24h, 7d",
  "explanation": "查询解释",
  "requires_aggregation": true/false
}}

注意：
1. 如果无法转换为有效的 PromQL，promql 字段返回 null
2. time_range 默认为 1h
3. 对于复杂的分析需求，requires_aggregation 设为 true
"""
    return prompt
```

- [ ] **Step 5.2: Commit**

```bash
git add src/agent/prompts.py
git commit -m "feat(agent): add LLM prompt templates for RCA and remediation"
```

---

## Task 6: 向量存储 (简化版)

**Files:**
- Create: `src/knowledge/__init__.py`
- Create: `src/knowledge/vector_store.py`

**Context:** 实现基于 ChromaDB 的向量存储，支持案例的添加和相似度搜索。

- [ ] **Step 6.1: 创建 src/knowledge/vector_store.py**

```python
"""Vector store implementation using ChromaDB."""

import hashlib
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings

from langops.core import get_logger
from langops.core.exceptions import VectorStoreError

logger = get_logger(__name__)


class SearchResult:
    """Vector search result."""
    
    def __init__(self, id: str, score: float, document: str, metadata: Dict):
        self.id = id
        self.score = score
        self.document = document
        self.metadata = metadata
    
    def __repr__(self):
        return f"SearchResult(id={self.id}, score={self.score:.3f})"


class VectorStore:
    """
    Vector store for knowledge base.
    
    Uses ChromaDB for storage and retrieval of failure cases.
    """
    
    def __init__(
        self,
        collection_name: str = "ops_knowledge",
        host: str = "localhost",
        port: int = 8001,
        persist_directory: Optional[str] = None
    ):
        self.collection_name = collection_name
        self.host = host
        self.port = port
        
        # Initialize ChromaDB client
        if persist_directory:
            # Local persistent mode
            self.client = chromadb.Client(Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_directory
            ))
        else:
            # HTTP client mode
            self.client = chromadb.HttpClient(
                host=host,
                port=port
            )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Operations knowledge base"}
        )
        
        logger.info("Vector store initialized", 
                   collection=collection_name, host=host, port=port)
    
    async def add_case(
        self,
        title: str,
        description: str,
        category: str,
        service: str,
        root_cause: str,
        solution: str,
        resolution_time: Optional[int] = None,
        timestamp: Optional[str] = None,
        case_id: Optional[str] = None
    ) -> str:
        """
        Add a failure case to the knowledge base.
        
        Args:
            title: Case title
            description: Problem description
            category: Problem category
            service: Affected service
            root_cause: Root cause analysis
            solution: Solution applied
            resolution_time: Time to resolve in minutes
            timestamp: Case timestamp (ISO format)
            case_id: Optional custom case ID
            
        Returns:
            The case ID
        """
        # Generate ID if not provided
        if case_id is None:
            content = f"{title}{description}{timestamp or ''}"
            case_id = hashlib.md5(content.encode()).hexdigest()
        
        # Create document for embedding
        document = f"""
故障: {title}
描述: {description}
根因: {root_cause}
解决方案: {solution}
        """.strip()
        
        # ChromaDB will automatically embed using its default embedding function
        # For production, you may want to use a specific embedding model
        try:
            self.collection.add(
                ids=[case_id],
                documents=[document],
                metadatas=[{
                    "title": title,
                    "category": category,
                    "service": service,
                    "root_cause": root_cause,
                    "solution": solution,
                    "resolution_time": resolution_time,
                    "timestamp": timestamp,
                    "resolved": True
                }]
            )
            
            logger.info("Case added to knowledge base", 
                       case_id=case_id, title=title)
            
            return case_id
            
        except Exception as e:
            logger.error("Failed to add case", error=str(e))
            raise VectorStoreError(f"Failed to add case: {e}")
    
    async def search(
        self,
        query: str,
        top_k: int = 3,
        filter_category: Optional[str] = None,
        filter_service: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Search for similar cases.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filter_category: Filter by category
            filter_service: Filter by service
            
        Returns:
            List of search results
        """
        # Build filter
        where_filter = {"resolved": True}
        if filter_category:
            where_filter["category"] = filter_category
        if filter_service:
            where_filter["service"] = filter_service
        
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where_filter if len(where_filter) > 1 else None
            )
            
            search_results = []
            for i in range(len(results["ids"][0])):
                # Convert distance to similarity score (ChromaDB returns distances)
                # Lower distance = higher similarity
                distance = results["distances"][0][i]
                similarity = 1 / (1 + distance)  # Convert to 0-1 range
                
                search_results.append(SearchResult(
                    id=results["ids"][0][i],
                    score=similarity,
                    document=results["documents"][0][i],
                    metadata=results["metadatas"][0][i]
                ))
            
            logger.info("Knowledge search completed", 
                       query=query[:50], results=len(search_results))
            
            return search_results
            
        except Exception as e:
            logger.error("Search failed", error=str(e))
            raise VectorStoreError(f"Search failed: {e}")
    
    async def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific case by ID."""
        try:
            result = self.collection.get(ids=[case_id])
            if result and result["ids"]:
                return {
                    "id": result["ids"][0],
                    "document": result["documents"][0],
                    "metadata": result["metadatas"][0]
                }
            return None
        except Exception as e:
            logger.error("Failed to get case", case_id=case_id, error=str(e))
            return None
    
    async def delete_case(self, case_id: str) -> bool:
        """Delete a case from the knowledge base."""
        try:
            self.collection.delete(ids=[case_id])
            logger.info("Case deleted", case_id=case_id)
            return True
        except Exception as e:
            logger.error("Failed to delete case", case_id=case_id, error=str(e))
            return False
    
    async def count(self) -> int:
        """Get total number of cases in the knowledge base."""
        try:
            return self.collection.count()
        except Exception as e:
            logger.error("Failed to count cases", error=str(e))
            return 0
```

- [ ] **Step 6.2: 创建 src/knowledge/__init__.py**

```python
"""Knowledge base module."""

from langops.knowledge.vector_store import SearchResult, VectorStore

__all__ = [
    "VectorStore",
    "SearchResult",
]
```

- [ ] **Step 6.3: Commit**

```bash
git add src/knowledge/
git commit -m "feat(knowledge): add vector store with ChromaDB integration"
```

---

## Task 7: AI Agent 核心 - AlertProcessor

**Files:**
- Create: `src/agent/__init__.py`
- Create: `src/agent/rca_engine.py`
- Create: `src/agent/alert_processor.py`

**Context:** 实现核心的 AlertProcessor，整合所有组件，使用 Langfuse 进行全链路追踪。

- [ ] **Step 7.1: 创建 src/agent/rca_engine.py**

```python
"""Root Cause Analysis Engine."""

import json
from typing import Any, Dict, List

import openai

from langops.agent.prompts import build_rca_prompt, build_remediation_prompt
from langops.core import get_logger
from langops.core.exceptions import LLMError
from langops.models import RemediationSuggestion, RootCause, SimilarCase

logger = get_logger(__name__)


class RCAEngine:
    """Root Cause Analysis Engine using LLM."""
    
    def __init__(self, api_key: str, model: str = "gpt-4", temperature: float = 0.2):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model
        self.temperature = temperature
    
    async def analyze(
        self,
        alert_title: str,
        alert_description: str,
        severity: str,
        category: str,
        source: Dict[str, Any],
        metrics: Dict[str, Any],
        logs: List[str],
        events: List[Dict]
    ) -> RootCause:
        """
        Perform root cause analysis.
        
        Returns:
            RootCause object with analysis results
        """
        prompt = build_rca_prompt(
            alert_title=alert_title,
            alert_description=alert_description,
            severity=severity,
            category=category,
            source=source,
            metrics=metrics,
            logs=logs,
            events=events
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return RootCause(
                category=result.get("root_cause_category", "未知"),
                description=result.get("description", "无法分析根因"),
                confidence=result.get("confidence", 0.0),
                evidence=result.get("key_evidence", []),
                related_metrics=result.get("related_metrics", []),
                impact_analysis=result.get("impact_analysis")
            )
            
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response as JSON", error=str(e))
            raise LLMError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            logger.error("LLM analysis failed", error=str(e))
            raise LLMError(f"LLM analysis failed: {e}")
    
    async def generate_remediation(
        self,
        root_cause: RootCause,
        similar_cases: List[SimilarCase],
        alert_context: Dict[str, Any]
    ) -> RemediationSuggestion:
        """
        Generate remediation suggestion.
        
        Returns:
            RemediationSuggestion object
        """
        # Convert SimilarCase list to dict for prompt
        similar_cases_dict = [
            {
                "title": case.title,
                "root_cause": case.root_cause,
                "solution": case.solution,
                "resolution_time": case.resolution_time
            }
            for case in similar_cases
        ]
        
        root_cause_dict = {
            "category": root_cause.category,
            "description": root_cause.description,
            "confidence": root_cause.confidence,
            "evidence": root_cause.evidence
        }
        
        prompt = build_remediation_prompt(
            root_cause=root_cause_dict,
            similar_cases=similar_cases_dict,
            alert_context=alert_context
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个专业的运维专家。输出严格的 JSON 格式。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json.loads(content)
            
            return RemediationSuggestion(
                summary=result.get("summary", "暂无修复建议"),
                steps=result.get("steps", []),
                commands=result.get("commands", []),
                risks=result.get("risks", []),
                rollback_plan=result.get("rollback_plan"),
                estimated_time=result.get("estimated_time", "unknown")
            )
            
        except Exception as e:
            logger.error("Failed to generate remediation", error=str(e))
            # Return a fallback suggestion
            return RemediationSuggestion(
                summary="无法生成具体修复建议，请参考根因分析",
                steps=["查看详细根因分析", "根据分类查找相关文档"],
                commands=[],
                risks=["自动修复失败，需要人工介入"],
                rollback_plan=None,
                estimated_time="unknown"
            )
```

- [ ] **Step 7.2: 创建 src/agent/alert_processor.py**

```python
"""Alert Processor - Main orchestrator for alert analysis."""

import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe

from langops.agent.rca_engine import RCAEngine
from langops.collectors import PrometheusCollector
from langops.core import get_logger, settings
from langops.core.exceptions import AnalysisError
from langops.knowledge import VectorStore
from langops.models import (
    Alert,
    AlertContext,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
    SimilarCase,
)

logger = get_logger(__name__)


class AlertProcessor:
    """
    Main alert processor that orchestrates the analysis pipeline.
    
    Pipeline:
    1. Collect context data from various sources
    2. Perform root cause analysis using LLM
    3. Retrieve similar cases from knowledge base
    4. Generate remediation suggestions
    5. Track everything in Langfuse
    """
    
    def __init__(
        self,
        langfuse: Langfuse,
        rca_engine: RCAEngine,
        vector_store: VectorStore,
        prometheus_collector: Optional[PrometheusCollector] = None
    ):
        self.langfuse = langfuse
        self.rca_engine = rca_engine
        self.vector_store = vector_store
        self.prometheus_collector = prometheus_collector
        
        logger.info("AlertProcessor initialized")
    
    @observe(as_type="processor")
    async def process(self, alert: Alert) -> AnalysisResult:
        """
        Process an alert through the complete analysis pipeline.
        
        Args:
            alert: The alert to process
            
        Returns:
            AnalysisResult with complete analysis
        """
        start_time = time.time()
        
        # Update trace metadata
        langfuse_context.update_current_trace(
            name="alert_analysis",
            user_id=alert.source.system,
            metadata={
                "alert_id": alert.id,
                "alert_title": alert.title,
                "severity": alert.severity.value,
                "category": alert.category.value,
                "source_type": alert.source.type
            }
        )
        
        logger.info("Starting alert processing", 
                   alert_id=alert.id, title=alert.title)
        
        try:
            # Step 1: Collect context data
            context = await self._collect_context(alert)
            
            # Step 2: Root cause analysis
            root_cause = await self._analyze_root_cause(alert, context)
            
            # Step 3: Retrieve similar cases
            similar_cases = await self._retrieve_similar_cases(alert)
            
            # Step 4: Generate remediation suggestion
            suggestion = await self._generate_remediation(
                root_cause, similar_cases, alert, context
            )
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Build result
            result = AnalysisResult(
                alert_id=alert.id,
                trace_id=langfuse_context.get_current_trace_id(),
                root_cause=root_cause,
                similar_cases=similar_cases,
                suggestion=suggestion,
                impact_prediction={"affected_service": alert.source.service},
                processing_time_seconds=processing_time,
            )
            
            logger.info("Alert processing completed",
                       alert_id=alert.id,
                       trace_id=result.trace_id,
                       processing_time=processing_time,
                       confidence=root_cause.confidence)
            
            return result
            
        except Exception as e:
            logger.error("Alert processing failed", 
                        alert_id=alert.id, error=str(e))
            raise AnalysisError(f"Failed to process alert {alert.id}: {e}")
    
    @observe(as_type="span")
    async def _collect_context(self, alert: Alert) -> AlertContext:
        """Collect context data for the alert."""
        context = AlertContext(alert=alert)
        
        # Collect metrics from Prometheus if available
        if self.prometheus_collector and alert.source.type == "kubernetes":
            try:
                metrics = await self.prometheus_collector.collect(
                    alert, 
                    time_window=timedelta(minutes=30)
                )
                context.metrics = metrics
                logger.info("Collected Prometheus metrics", 
                           alert_id=alert.id, 
                           metrics_count=len(metrics))
            except Exception as e:
                logger.warning("Failed to collect Prometheus metrics",
                             alert_id=alert.id, error=str(e))
                context.metrics = {"error": str(e)}
        
        # TODO: Collect logs and events in future iterations
        context.logs = []
        context.events = []
        
        return context
    
    @observe(as_type="generation")
    async def _analyze_root_cause(
        self, 
        alert: Alert, 
        context: AlertContext
    ) -> RootCause:
        """Perform root cause analysis using LLM."""
        logger.info("Starting root cause analysis", alert_id=alert.id)
        
        return await self.rca_engine.analyze(
            alert_title=alert.title,
            alert_description=alert.description,
            severity=alert.severity.value,
            category=alert.category.value,
            source=alert.source.model_dump(),
            metrics=context.metrics,
            logs=context.logs,
            events=context.events
        )
    
    @observe(as_type="span")
    async def _retrieve_similar_cases(
        self, 
        alert: Alert,
        top_k: int = 3
    ) -> List[SimilarCase]:
        """Retrieve similar cases from knowledge base."""
        query = f"{alert.title} {alert.description}"
        
        try:
            results = await self.vector_store.search(
                query=query,
                top_k=top_k,
                filter_category=alert.category.value
            )
            
            similar_cases = [
                SimilarCase(
                    case_id=result.id,
                    similarity_score=result.score,
                    title=result.metadata.get("title", ""),
                    root_cause=result.metadata.get("root_cause", ""),
                    solution=result.metadata.get("solution", ""),
                    resolution_time=result.metadata.get("resolution_time")
                )
                for result in results
            ]
            
            logger.info("Retrieved similar cases",
                       alert_id=alert.id, count=len(similar_cases))
            
            return similar_cases
            
        except Exception as e:
            logger.warning("Failed to retrieve similar cases",
                         alert_id=alert.id, error=str(e))
            return []
    
    @observe(as_type="generation")
    async def _generate_remediation(
        self,
        root_cause: RootCause,
        similar_cases: List[SimilarCase],
        alert: Alert,
        context: AlertContext
    ) -> RemediationSuggestion:
        """Generate remediation suggestion."""
        alert_context = {
            "service": alert.source.service or "unknown",
            "namespace": alert.source.namespace or "unknown",
            "resource_type": alert.source.resource_type or "unknown"
        }
        
        return await self.rca_engine.generate_remediation(
            root_cause=root_cause,
            similar_cases=similar_cases,
            alert_context=alert_context
        )
```

- [ ] **Step 7.3: 创建 src/agent/__init__.py**

```python
"""Agent module."""

from langops.agent.alert_processor import AlertProcessor
from langops.agent.rca_engine import RCAEngine

__all__ = [
    "AlertProcessor",
    "RCAEngine",
]
```

- [ ] **Step 7.4: Commit**

```bash
git add src/agent/
git commit -m "feat(agent): add AlertProcessor with Langfuse tracing and RCA pipeline"
```

---

## Task 8: FastAPI Web 服务

**Files:**
- Create: `src/web/__init__.py`
- Create: `src/web/dependencies.py`
- Create: `src/web/api/alerts.py`
- Create: `src/web/main.py`

**Context:** 创建 FastAPI 应用，提供告警处理 API 接口。

- [ ] **Step 8.1: 创建 src/web/dependencies.py**

```python
"""FastAPI dependencies."""

from functools import lru_cache
from typing import Optional

from fastapi import Request
from langfuse import Langfuse

from langops.agent import AlertProcessor, RCAEngine
from langops.collectors import PrometheusCollector
from langops.core import settings
from langops.knowledge import VectorStore


@lru_cache()
def get_langfuse() -> Langfuse:
    """Get Langfuse client (cached)."""
    return Langfuse(
        public_key=settings.langfuse.public_key,
        secret_key=settings.langfuse.secret_key,
        host=settings.langfuse.host,
        release=settings.langfuse.release
    )


@lru_cache()
def get_vector_store() -> VectorStore:
    """Get vector store (cached)."""
    return VectorStore(
        collection_name=settings.vector_store.collection_name,
        host=settings.vector_store.host,
        port=settings.vector_store.port,
        persist_directory=settings.vector_store.persist_directory
    )


def get_prometheus_collector() -> Optional[PrometheusCollector]:
    """Get Prometheus collector if configured."""
    if not settings.prometheus.url:
        return None
    
    return PrometheusCollector({
        "url": settings.prometheus.url,
        "timeout": settings.prometheus.timeout
    })


@lru_cache()
def get_rca_engine() -> RCAEngine:
    """Get RCA engine (cached)."""
    return RCAEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        temperature=settings.llm.temperature
    )


def get_alert_processor() -> AlertProcessor:
    """Get alert processor with all dependencies."""
    return AlertProcessor(
        langfuse=get_langfuse(),
        rca_engine=get_rca_engine(),
        vector_store=get_vector_store(),
        prometheus_collector=get_prometheus_collector()
    )
```

- [ ] **Step 8.2: 创建 src/web/api/alerts.py**

```python
"""Alert API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from langops.agent import AlertProcessor
from langops.models import Alert, AlertCreate, AnalysisResponse, AnalysisResult
from langops.web.dependencies import get_alert_processor

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post(
    "",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Process an alert",
    description="Receive an alert and trigger AI analysis pipeline."
)
async def create_alert(
    alert_create: AlertCreate,
    processor: AlertProcessor = Depends(get_alert_processor)
) -> AnalysisResponse:
    """
    Process a new alert.
    
    This endpoint:
    1. Receives alert data
    2. Collects additional context
    3. Performs root cause analysis
    4. Retrieves similar historical cases
    5. Generates remediation suggestions
    6. Returns complete analysis with trace ID
    """
    try:
        # Create Alert from AlertCreate (generating ID and timestamp)
        import uuid
        from datetime import datetime
        
        alert = Alert(
            id=f"alert-{uuid.uuid4().hex[:8]}",
            title=alert_create.title,
            description=alert_create.description,
            severity=alert_create.severity,
            category=alert_create.category,
            source=alert_create.source,
            timestamp=datetime.utcnow(),
            metric_data=alert_create.metric_data,
            log_snippets=alert_create.log_snippets,
            related_events=alert_create.related_events,
            context=alert_create.context
        )
        
        # Process the alert
        result = await processor.process(alert)
        
        return AnalysisResponse(
            success=True,
            data=result,
            error=None
        )
        
    except Exception as e:
        return AnalysisResponse(
            success=False,
            data=None,
            error=str(e)
        )


@router.get(
    "/health",
    summary="Health check",
    description="Check if the alert service is healthy."
)
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "alerts"}
```

- [ ] **Step 8.3: 创建 src/web/main.py**

```python
"""FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langops.core import configure_logging, get_logger
from langops.web.api import alerts

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    configure_logging()
    logger.info("LangOps starting up", version="0.1.0")
    
    yield
    
    # Shutdown
    logger.info("LangOps shutting down")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(
        title="LangOps",
        description="AI-powered intelligent operations platform",
        version="0.1.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(alerts.router, prefix="/api/v1")
    
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "LangOps",
            "version": "0.1.0",
            "description": "AI-powered intelligent operations platform",
            "docs": "/docs"
        }
    
    return app


app = create_app()
```

- [ ] **Step 8.4: 创建 src/web/__init__.py**

```python
"""Web module."""

from langops.web.main import app, create_app

__all__ = ["app", "create_app"]
```

- [ ] **Step 8.5: 创建 src/web/api/__init__.py**

```python
"""API routes."""

from langops.web.api import alerts

__all__ = ["alerts"]
```

- [ ] **Step 8.6: Commit**

```bash
git add src/web/
git commit -m "feat(web): add FastAPI application with alert processing endpoint"
```

---

## Task 9: 应用入口与启动脚本

**Files:**
- Create: `src/__init__.py`
- Create: `src/server.py`
- Create: `pytest.ini`

**Context:** 创建应用入口点，配置测试环境。

- [ ] **Step 9.1: 创建 src/__init__.py**

```python
"""LangOps - AI-powered intelligent operations platform."""

__version__ = "0.1.0"
__author__ = "LangOps Team"
```

- [ ] **Step 9.2: 创建 src/server.py**

```python
"""Server entry point."""

import uvicorn

from langops.core import settings


def main():
    """Run the server."""
    uvicorn.run(
        "langops.web:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        workers=1 if settings.debug else settings.workers
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 9.3: 创建 pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
env =
    DEBUG=true
    LOG_LEVEL=DEBUG
```

- [ ] **Step 9.4: Commit**

```bash
git add src/__init__.py src/server.py pytest.ini
git commit -m "feat: add server entry point and pytest configuration"
```

---

## Task 10: 端到端测试与验证

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/integration/test_e2e.py`

**Context:** 创建端到端测试，验证完整的告警处理流程。

- [ ] **Step 10.1: 创建 tests/conftest.py**

```python
"""pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient

from langops.web import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_alert_data():
    """Sample alert data for testing."""
    return {
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
        }
    }
```

- [ ] **Step 10.2: 创建 tests/__init__.py**

```python
"""Tests module."""
```

- [ ] **Step 10.3: 创建 tests/integration/__init__.py**

```python
"""Integration tests."""
```

- [ ] **Step 10.4: 创建 tests/integration/test_e2e.py**

```python
"""End-to-end tests for LangOps."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "LangOps"
        assert "version" in data
    
    def test_health_endpoint(self, client: TestClient):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_alerts_health(self, client: TestClient):
        """Test alerts health endpoint."""
        response = client.get("/api/v1/alerts/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAlertProcessing:
    """Test alert processing API."""
    
    @pytest.mark.asyncio
    async def test_create_alert_success(self, client: TestClient, sample_alert_data):
        """Test creating an alert triggers analysis."""
        # Note: This test requires the full stack to be running
        # including Langfuse, ChromaDB, and OpenAI API key
        
        response = client.post("/api/v1/alerts", json=sample_alert_data)
        
        # Should return 200 even if processing has issues
        assert response.status_code == 200
        
        result = response.json()
        assert "success" in result
        
        if result["success"]:
            assert "data" in result
            assert result["data"]["alert_id"]
            assert result["data"]["trace_id"]
            assert result["data"]["root_cause"]
            assert result["data"]["suggestion"]
        else:
            # If failed, should have error message
            assert "error" in result
    
    def test_create_alert_validation_error(self, client: TestClient):
        """Test alert validation."""
        # Missing required fields
        invalid_data = {
            "title": "Test",
            # Missing description, severity, etc.
        }
        
        response = client.post("/api/v1/alerts", json=invalid_data)
        assert response.status_code == 422  # Validation error
```

- [ ] **Step 10.5: 运行测试**

```bash
# 确保依赖服务在运行
docker-compose ps

# 运行测试
cd /Users/bohaiqing/opensource/git/LangOps
source venv/bin/activate

# 设置测试环境变量
export DEBUG=true
export LOG_LEVEL=DEBUG
export LLM_API_KEY="sk-test"  # 使用测试 key 或 mock

# 运行测试
pytest tests/integration/test_e2e.py -v
```

- [ ] **Step 10.6: Commit**

```bash
git add tests/
git commit -m "test: add integration tests for health endpoints and alert API"
```

---

## Task 11: 初始化脚本与示例数据

**Files:**
- Create: `scripts/init_knowledge.py`
- Create: `docs/examples/sample-alert.json`

**Context:** 创建初始化脚本，添加示例数据到知识库。

- [ ] **Step 11.1: 创建 scripts/init_knowledge.py**

```python
#!/usr/bin/env python3
"""Initialize knowledge base with sample cases."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from langops.knowledge import VectorStore


SAMPLE_CASES = [
    {
        "title": "MySQL 连接数耗尽",
        "description": "数据库连接池耗尽，应用无法获取新连接，导致请求超时",
        "category": "resource",
        "service": "user-service",
        "root_cause": "连接池配置过小，连接未及时释放",
        "solution": "1. 增加连接池大小 2. 检查连接泄漏 3. 添加连接超时配置",
        "resolution_time": 30
    },
    {
        "title": "Pod OOMKilled",
        "description": "Pod 因内存不足被系统 OOM Killer 终止",
        "category": "resource",
        "service": "order-service",
        "root_cause": "内存限制配置过小，无法满足应用需求",
        "solution": "1. 分析内存使用模式 2. 调整 Pod memory limit 3. 优化内存使用",
        "resolution_time": 15
    },
    {
        "title": "ECS 磁盘空间不足",
        "description": "服务器磁盘使用率超过90%，影响日志写入和临时文件创建",
        "category": "resource",
        "service": "log-collector",
        "root_cause": "日志文件未清理，磁盘空间持续增长",
        "solution": "1. 清理旧日志 2. 配置日志轮转 3. 扩容磁盘",
        "resolution_time": 20
    },
    {
        "title": "RDS 慢查询导致连接堆积",
        "description": "数据库出现大量慢查询，导致连接数堆积，新请求无法接入",
        "category": "performance",
        "service": "payment-service",
        "root_cause": "缺少关键索引，全表扫描导致查询缓慢",
        "solution": "1. 分析慢查询日志 2. 添加必要索引 3. 优化查询语句",
        "resolution_time": 45
    },
    {
        "title": "服务依赖超时导致级联故障",
        "description": "下游服务响应缓慢，导致上游服务线程池耗尽",
        "category": "availability",
        "service": "api-gateway",
        "root_cause": "缺少熔断机制，依赖故障扩散",
        "solution": "1. 启用熔断器 2. 配置降级策略 3. 增加超时配置",
        "resolution_time": 25
    }
]


async def init_knowledge_base():
    """Initialize knowledge base with sample cases."""
    print("Initializing knowledge base...")
    
    store = VectorStore(
        host="localhost",
        port=8001,
        collection_name="ops_knowledge"
    )
    
    for case in SAMPLE_CASES:
        try:
            case_id = await store.add_case(
                title=case["title"],
                description=case["description"],
                category=case["category"],
                service=case["service"],
                root_cause=case["root_cause"],
                solution=case["solution"],
                resolution_time=case["resolution_time"]
            )
            print(f"  Added: {case['title']} (ID: {case_id[:8]}...)")
        except Exception as e:
            print(f"  Failed to add {case['title']}: {e}")
    
    count = await store.count()
    print(f"\nKnowledge base initialized with {count} cases")


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
```

- [ ] **Step 11.2: 创建 docs/examples/sample-alert.json**

```json
{
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
    "2024-01-15 10:30:45 ERROR High CPU usage detected",
    "2024-01-15 10:31:00 WARN Thread pool exhaustion"
  ],
  "context": {
    "deployment_version": "v2.3.1",
    "node_name": "node-01"
  }
}
```

- [ ] **Step 11.3: 运行初始化脚本**

```bash
# 确保 ChromaDB 在运行
docker-compose ps chromadb

# 运行初始化
python scripts/init_knowledge.py
```

- [ ] **Step 11.4: 测试 API 调用**

```bash
# 测试告警处理
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d @docs/examples/sample-alert.json
```

- [ ] **Step 11.5: Commit**

```bash
git add scripts/ docs/examples/
git commit -m "feat: add knowledge base initialization script and sample data"
```

---

## 总结

### 已完成的 MVP 功能

| 模块 | 功能 | 状态 |
|-----|------|------|
| Core | 配置管理、日志、异常 | ✅ |
| Models | Alert、Analysis 数据模型 | ✅ |
| Collectors | Prometheus 采集器 | ✅ |
| Agent | AlertProcessor、RCA Engine | ✅ |
| Knowledge | ChromaDB 向量存储 | ✅ |
| Web | FastAPI、告警 API | ✅ |
| Tests | 集成测试 | ✅ |
| Scripts | 知识库初始化 | ✅ |

### 运行项目

```bash
# 1. 启动依赖服务
docker-compose up -d

# 2. 初始化知识库
python scripts/init_knowledge.py

# 3. 配置环境变量
cp config/.env.example .env
# 编辑 .env 填入你的 OpenAI API Key

# 4. 启动服务
python -m langops.server

# 5. 测试 API
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d @docs/examples/sample-alert.json
```

### 访问界面

- **API 文档**: http://localhost:8000/docs
- **Langfuse UI**: http://localhost:3000
- **ChromaDB**: http://localhost:8001

---

**Plan complete!** 实施计划已完成，包含了从项目初始化到完整 MVP 的所有任务。每个任务都有具体的代码和验证步骤。
