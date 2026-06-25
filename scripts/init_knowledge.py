#!/usr/bin/env python3
"""Initialize knowledge base with sample cases.

Requires editable install (``pip install -e .``) and ChromaDB running.
"""

import asyncio

from langops.core import settings
from langops.knowledge import VectorStore

SAMPLE_CASES = [
    {
        "title": "MySQL 连接数耗尽",
        "description": "数据库连接池耗尽，应用无法获取新连接，导致请求超时",
        "category": "resource",
        "service": "user-service",
        "root_cause": "连接池配置过小，连接未及时释放",
        "solution": "1. 增加连接池大小 2. 检查连接泄漏 3. 添加连接超时配置",
        "resolution_time": 30,
    },
    {
        "title": "Pod OOMKilled",
        "description": "Pod 因内存不足被系统 OOM Killer 终止",
        "category": "resource",
        "service": "order-service",
        "root_cause": "内存限制配置过小，无法满足应用需求",
        "solution": "1. 分析内存使用模式 2. 调整 Pod memory limit 3. 优化内存使用",
        "resolution_time": 15,
    },
    {
        "title": "ECS 磁盘空间不足",
        "description": "服务器磁盘使用率超过90%，影响日志写入和临时文件创建",
        "category": "resource",
        "service": "log-collector",
        "root_cause": "日志文件未清理，磁盘空间持续增长",
        "solution": "1. 清理旧日志 2. 配置日志轮转 3. 扩容磁盘",
        "resolution_time": 20,
    },
    {
        "title": "RDS 慢查询导致连接堆积",
        "description": "数据库出现大量慢查询，导致连接数堆积，新请求无法接入",
        "category": "performance",
        "service": "payment-service",
        "root_cause": "缺少关键索引，全表扫描导致查询缓慢",
        "solution": "1. 分析慢查询日志 2. 添加必要索引 3. 优化查询语句",
        "resolution_time": 45,
    },
    {
        "title": "服务依赖超时导致级联故障",
        "description": "下游服务响应缓慢，导致上游服务线程池耗尽",
        "category": "availability",
        "service": "api-gateway",
        "root_cause": "缺少熔断机制，依赖故障扩散",
        "solution": "1. 启用熔断器 2. 配置降级策略 3. 增加超时配置",
        "resolution_time": 25,
    },
]


async def init_knowledge_base() -> None:
    """Initialize knowledge base with sample cases."""
    print("Initializing knowledge base...")

    vs = settings.vector_store
    store = VectorStore(
        collection_name=vs.collection_name,
        host=vs.host,
        port=vs.port,
        persist_directory=vs.persist_directory,
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
                resolution_time=case["resolution_time"],
            )
            print(f"  Added: {case['title']} (ID: {case_id[:8]}...)")
        except Exception as exc:
            print(f"  Failed to add {case['title']}: {exc}")

    count = await store.count()
    print(f"\nKnowledge base initialized with {count} cases")


if __name__ == "__main__":
    asyncio.run(init_knowledge_base())
