# LangOps 快速参考指南

## 架构总览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Prometheus │     │  阿里云 CMS │     │ Kubernetes  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
              ┌─────────────────────┐
              │   数据标准化层       │
              │  (AlertContext)     │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │     AI Agent        │
              │  ┌───────────────┐  │
              │  │ 1. 数据聚合    │  │
              │  │ 2. 根因分析    │  │  ◄── Langfuse Trace
              │  │ 3. 知识检索    │  │
              │  │ 4. 修复建议    │  │
              │  └───────────────┘  │
              └──────────┬──────────┘
                         ▼
              ┌─────────────────────┐
              │   结果输出层        │
              │  Web UI / 通知      │
              └─────────────────────┘
```

## 核心数据流

```
告警触发 ──▶ 数据收集 ──▶ LLM 根因分析 ──▶ 向量检索 ──▶ 建议生成 ──▶ 结果输出
    │           │              │              │             │           │
    │           │              │              │             │           │
    ▼           ▼              ▼              ▼             ▼           ▼
┌───────┐  ┌────────┐    ┌──────────┐   ┌──────────┐  ┌──────────┐ ┌──────────┐
│Webhook│  │Prometheus│   │ GPT-4    │   │ChromaDB  │  │ GPT-4    │ │飞书/钉钉 │
│定时任务│  │阿里云    │   │ Claude   │   │向量搜索   │  │ 建议生成  │ │JIRA      │
└───────┘  └────────┘    └──────────┘   └──────────┘  └──────────┘ └──────────┘
                              │                                              │
                              ▼                                              ▼
                        ┌──────────┐                                   ┌──────────┐
                        │ Langfuse │                                   │ 用户反馈  │
                        │ 观测中枢  │                                   │ 评分入库  │
                        └──────────┘                                   └──────────┘
```

## 关键类与接口

### 1. AlertProcessor - 告警处理核心

```python
class AlertProcessor:
    """告警处理器 - 主入口"""
    
    async def process_alert(self, alert: Alert) -> AnalysisResult:
        """
        处理告警的主流程
        
        Pipeline:
        1. collect_context()     - 收集多维度数据
        2. analyze_root_cause()  - LLM 根因分析
        3. retrieve_similar_cases() - 向量检索
        4. generate_remediation()   - 生成建议
        """
        pass
```

### 2. 数据模型

```python
# Alert - 输入
@dataclass
class Alert:
    id: str
    title: str
    description: str
    severity: AlertSeverity      # critical/high/medium/low
    category: AlertCategory      # resource/availability/performance
    source: AlertSource          # prometheus/aliyun/kubernetes
    metric_data: Dict[str, Any]
    timestamp: datetime

# AnalysisResult - 输出
@dataclass
class AnalysisResult:
    alert_id: str
    trace_id: str                # Langfuse Trace ID
    root_cause: RootCause        # 根因分析结果
    similar_cases: List[SimilarCase]  # 相似历史案例
    suggestion: RemediationSuggestion   # 修复建议
```

### 3. API 端点

```python
# 告警处理
POST /api/v1/alerts           # 接收告警并触发分析
GET  /api/v1/alerts           # 查询告警列表
GET  /api/v1/alerts/{id}      # 获取告警详情

# 自然语言查询
POST /api/v1/query            # 自然语言查询运维数据

# 知识库管理
GET    /api/v1/knowledge/cases     # 搜索案例
POST   /api/v1/knowledge/cases     # 添加案例
DELETE /api/v1/knowledge/cases/{id} # 删除案例

# Trace 查询
GET /api/v1/traces/{trace_id}  # 获取 Langfuse Trace 详情
```

## 配置速查

### 最小配置 (application.yaml)

```yaml
langops:
  # LLM 配置
  llm:
    provider: openai
    model: gpt-4
    api_key: ${OPENAI_API_KEY}
  
  # Langfuse 配置
  langfuse:
    host: http://localhost:3000
    public_key: ${LANGFUSE_PUBLIC_KEY}
    secret_key: ${LANGFUSE_SECRET_KEY}
  
  # 数据源配置
  collectors:
    prometheus:
      url: http://prometheus:9090
    aliyun:
      access_key_id: ${ALIYUN_ACCESS_KEY_ID}
      access_key_secret: ${ALIYUN_ACCESS_KEY_SECRET}
```

### 环境变量

```bash
# LLM
export OPENAI_API_KEY="sk-..."

# Langfuse
export LANGFUSE_PUBLIC_KEY="pk-..."
export LANGFUSE_SECRET_KEY="sk-..."

# 阿里云
export ALIYUN_ACCESS_KEY_ID="LTAI..."
export ALIYUN_ACCESS_KEY_SECRET="..."

# 通知
export FEISHU_WEBHOOK="https://open.feishu.cn/..."
```

## 常用命令

```bash
# 启动依赖服务
docker-compose up -d

# 启动开发服务器
python -m langops.server --reload

# 运行测试
pytest tests/unit -v
pytest tests/integration -v

# 代码检查
black src/
isort src/
flake8 src/
mypy src/

# 查看 Langfuse UI
open http://localhost:3000

# 查看 API 文档
open http://localhost:8000/docs
open http://localhost:8000/redoc
```

## 调试技巧

### 查看 Langfuse Trace

```python
# 获取 Trace ID
result = await processor.process_alert(alert)
print(f"Trace ID: {result.trace_id}")

# 在 Langfuse UI 中查看
# http://localhost:3000/project/{project_id}/traces/{trace_id}
```

### 手动测试 API

```bash
# 发送测试告警
curl -X POST http://localhost:8000/api/v1/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "title": "CPU使用率过高",
    "description": "order-service CPU > 90%",
    "severity": "critical",
    "category": "resource",
    "source": {
      "type": "kubernetes",
      "namespace": "production",
      "pod_name": "order-service-xxx"
    }
  }'

# 自然语言查询
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "昨天有哪些告警？"}'
```

## 故障排查

### 常见问题

| 问题 | 可能原因 | 解决方案 |
|-----|---------|---------|
| Langfuse 连接失败 | 服务未启动 | `docker-compose up -d langfuse` |
| LLM 调用超时 | 网络问题 | 检查代理配置，增加 timeout |
| 向量检索无结果 | 知识库为空 | 运行初始化脚本添加案例 |
| Prometheus 查询失败 | 配置错误 | 检查 `PROMETHEUS_URL` |

### 日志查看

```bash
# 查看应用日志
docker-compose logs -f langops

# 查看 Langfuse 日志
docker-compose logs -f langfuse

# 查看详细 Debug 日志
LOG_LEVEL=DEBUG python -m langops.server
```

## 性能优化

### 缓存策略

```python
# Redis 缓存热点数据
@cache.redis(ttl=300)
async def get_pod_metrics(pod_name: str):
    return await prometheus.query(...)

# 本地缓存配置
@cache.local(maxsize=1000)
def parse_promql(query: str):
    return nl2promql(query)
```

### 异步优化

```python
# 并行采集数据
async def collect_context(alert):
    # 并行执行多个采集任务
    results = await asyncio.gather(
        collect_prometheus_metrics(alert),
        collect_aliyun_metrics(alert),
        collect_k8s_events(alert),
        collect_logs(alert)
    )
    return merge_results(results)
```

## 扩展开发

### 添加新的采集器

```python
# 1. 继承基类
from langops.collectors.base import BaseCollector

class CustomCollector(BaseCollector):
    async def collect(self, alert: Alert) -> Dict:
        # 实现采集逻辑
        pass

# 2. 注册到工厂
from langops.collectors import register_collector
register_collector("custom", CustomCollector)

# 3. 配置中使用
collectors:
  custom:
    enabled: true
    param1: value1
```

### 添加新的分析器

```python
# 自定义根因分析器
class CustomRCAEngine:
    async def analyze(self, context: AlertContext) -> RootCause:
        # 自定义分析逻辑
        pass

# 替换默认引擎
processor.rca_engine = CustomRCAEngine()
```

## 参考资源

- [系统设计文档](./system-design.md)
- [目录结构说明](./directory-structure.md)
- [API 文档](../api/openapi.yaml)
- [部署指南](../deployment/kubernetes.md)

---

**提示**: 本文档为快速参考，详细内容请查阅对应模块的完整文档。
