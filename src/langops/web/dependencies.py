"""FastAPI dependencies."""

from functools import lru_cache

from langfuse import Langfuse

from langops.agent.nl_query_engine import NLQueryEngine
from langops.agent.predictive_engine import PredictiveEngine
from langops.agent import AlertProcessor, RCAEngine
from langops.collectors import AliyunCmsCollector, PrometheusCollector
from langops.core import settings
from langops.knowledge import VectorStore
from langops.services import NotificationService


@lru_cache
def get_langfuse() -> Langfuse:
    """Get Langfuse client (cached)."""
    return Langfuse(
        public_key=settings.langfuse.public_key,
        secret_key=settings.langfuse.secret_key,
        host=settings.langfuse.host,
        release=settings.langfuse.release,
    )


@lru_cache
def get_vector_store() -> VectorStore:
    """Get vector store (cached)."""
    return VectorStore(
        collection_name=settings.vector_store.collection_name,
        host=settings.vector_store.host,
        port=settings.vector_store.port,
        persist_directory=settings.vector_store.persist_directory,
    )


def get_prometheus_collector() -> PrometheusCollector | None:
    """Get Prometheus collector if configured."""
    if not settings.prometheus.url:
        return None

    return PrometheusCollector(
        {
            "url": settings.prometheus.url,
            "timeout": settings.prometheus.timeout,
        }
    )


def get_aliyun_collector() -> AliyunCmsCollector | None:
    """Get Aliyun CMS collector if credentials are configured."""
    if not settings.aliyun.access_key_id or not settings.aliyun.access_key_secret:
        return None

    return AliyunCmsCollector(
        {
            "access_key_id": settings.aliyun.access_key_id,
            "access_key_secret": settings.aliyun.access_key_secret,
            "region": settings.aliyun.region,
            "endpoint": settings.aliyun.cms_endpoint,
        }
    )


@lru_cache
def get_rca_engine() -> RCAEngine:
    """Get RCA engine (cached)."""
    return RCAEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        temperature=settings.llm.temperature,
    )


def get_notification_service() -> NotificationService | None:
    """Get notification service if any webhook is configured."""
    if not settings.feishu.webhook and not settings.dingtalk.webhook:
        return None

    return NotificationService(
        feishu_webhook=settings.feishu.webhook,
        dingtalk_webhook=settings.dingtalk.webhook,
    )


def get_predictive_engine() -> PredictiveEngine:
    """Get predictive operations engine."""
    return PredictiveEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
    )


def get_nl_query_engine() -> NLQueryEngine:
    """Get natural language query engine."""
    return NLQueryEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        prometheus_collector=get_prometheus_collector(),
    )


def get_alert_processor() -> AlertProcessor:
    """Get alert processor with all dependencies."""
    return AlertProcessor(
        langfuse=get_langfuse(),
        rca_engine=get_rca_engine(),
        vector_store=get_vector_store(),
        prometheus_collector=get_prometheus_collector(),
        aliyun_collector=get_aliyun_collector(),
        notification_service=get_notification_service(),
        predictive_engine=get_predictive_engine(),
    )
