"""FastAPI dependencies."""

from functools import lru_cache
from typing import cast

from langfuse import Langfuse

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.adapters.aliyun_cms import AliyunCmsWebhookAdapter
from langops.agent import AlertProcessor, RCAEngine
from langops.agent.nl_query_engine import NLQueryEngine
from langops.agent.predictive_engine import PredictiveEngine
from langops.collectors import AliyunCmsCollector, PrometheusCollector
from langops.core import get_logger, settings
from langops.core.audit import AuditLogger
from langops.knowledge import EnhancedRetriever, QueryRewriter, Reranker, VectorStore
from langops.services import (
    AlertNoiseReducer,
    JiraService,
    NotificationService,
    RemediationExecutor,
    RemediationRegistry,
)
from langops.storage import get_storage
from fastapi import Request

from langops.web._coalesce import CoalesceBuffer

logger = get_logger(__name__)


@lru_cache
def get_langfuse() -> Langfuse:
    return Langfuse(
        public_key=settings.langfuse.public_key,
        secret_key=settings.langfuse.secret_key,
        host=settings.langfuse.host,
        release=settings.langfuse.release,
    )


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore(
        collection_name=settings.vector_store.collection_name,
        host=settings.vector_store.host,
        port=settings.vector_store.port,
        persist_directory=settings.vector_store.persist_directory,
    )


@lru_cache
def get_enhanced_retriever() -> EnhancedRetriever | None:
    """Get enhanced retriever with HyDE and reranking if enabled."""
    # If both features disabled, return None to use basic vector store
    if not settings.rag.hyde_enabled and not settings.rag.rerank_enabled:
        return None
    
    vector_store = get_vector_store()
    
    # Create query rewriter if HyDE enabled
    query_rewriter = None
    if settings.rag.hyde_enabled:
        from openai import AsyncOpenAI
        llm_client = AsyncOpenAI(
            api_key=settings.llm.api_key,
            base_url=settings.llm.base_url,
        )
        query_rewriter = QueryRewriter(
            llm_client=llm_client,
            model=settings.llm.model,
            temperature=0.3,
            max_tokens=500,
        )
    
    # Create reranker if enabled
    reranker = None
    if settings.rag.rerank_enabled:
        reranker = Reranker(model_name=settings.rag.rerank_model)
    
    return EnhancedRetriever(
        vector_store=vector_store,
        query_rewriter=query_rewriter,
        reranker=reranker,
        hyde_enabled=settings.rag.hyde_enabled,
        rerank_enabled=settings.rag.rerank_enabled,
        rerank_fetch_k=settings.rag.rerank_fetch_k,
    )


def get_prometheus_collector() -> PrometheusCollector | None:
    if not settings.prometheus.url:
        return None
    return PrometheusCollector(
        {"url": settings.prometheus.url, "timeout": settings.prometheus.timeout}
    )


def get_aliyun_collector() -> AliyunCmsCollector | None:
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
    return RCAEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        base_url=settings.llm.base_url,
    )


async def get_alert_dedup() -> AlertNoiseReducer:
    storage = await get_storage()
    return AlertNoiseReducer(
        repo=storage.dedup,
        window_seconds=settings.alert_dedup.window_seconds,
        enabled=settings.alert_dedup.enabled,
    )


async def get_remediation_registry() -> RemediationRegistry:
    storage = await get_storage()
    return RemediationRegistry(repo=storage.remediations)


def get_remediation_executor() -> RemediationExecutor:
    return RemediationExecutor(execution_enabled=settings.remediation.execution_enabled)


def get_jira_service() -> JiraService:
    return JiraService(
        url=settings.jira.url,
        username=settings.jira.username,
        api_token=settings.jira.api_token,
        project=settings.jira.project,
        enabled=settings.jira.enabled,
        timeout=settings.jira.timeout,
    )


@lru_cache
def get_notification_service() -> NotificationService | None:
    if (
        not settings.feishu.webhook
        and not settings.dingtalk.webhook
        and not settings.wechat_work.webhook
    ):
        return None
    return NotificationService(
        feishu_webhook=settings.feishu.webhook,
        dingtalk_webhook=settings.dingtalk.webhook,
        wechat_work_webhook=settings.wechat_work.webhook,
    )


async def close_notification_service() -> None:
    """Close the cached notification service session (best-effort)."""
    svc = get_notification_service.cache_info().hits  # noqa: only if cached
    svc = get_notification_service()  # returns cached singleton or None
    if svc is not None:
        await svc.close()


def get_predictive_engine() -> PredictiveEngine:
    return PredictiveEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        base_url=settings.llm.base_url,
    )


def get_nl_query_engine() -> NLQueryEngine:
    return NLQueryEngine(
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        prometheus_collector=get_prometheus_collector(),
        base_url=settings.llm.base_url,
    )


def get_alert_processor() -> AlertProcessor:
    return AlertProcessor(
        langfuse=get_langfuse(),
        rca_engine=get_rca_engine(),
        vector_store=get_vector_store(),
        prometheus_collector=get_prometheus_collector(),
        aliyun_collector=get_aliyun_collector(),
        notification_service=get_notification_service(),
        predictive_engine=get_predictive_engine(),
        enhanced_retriever=get_enhanced_retriever(),
    )


async def persist_alert_and_result(alert, result) -> None:
    try:
        storage = await get_storage()
        await storage.alerts.save(alert)
        await storage.analyses.save(result)
    except Exception as e:
        logger.warning("Failed to persist alert", error=str(e), alert_id=alert.id)


# ─── Webhook DI factories ───────────────────────────────────────────────


@lru_cache
def get_audit_logger() -> AuditLogger:
    """Process-wide AuditLogger singleton (file-based, rotating)."""
    return AuditLogger(
        path=settings.webhook.audit_log_path,
        retention_days=settings.webhook.audit_log_retention_days,
    )


@lru_cache
def get_alertmanager_adapter() -> AlertmanagerAdapter:
    """Stateless AlertManager payload adapter."""
    return AlertmanagerAdapter()


@lru_cache
def get_aliyun_cms_adapter() -> AliyunCmsWebhookAdapter:
    """Stateless Aliyun Cloud Monitor callback adapter."""
    return AliyunCmsWebhookAdapter()


def get_coalesce_buffer(request: Request) -> CoalesceBuffer:
    """Return the CoalesceBuffer instance stored on ``app.state`` by lifespan.

    Tests inject their own buffer via ``app.dependency_overrides``; in production
    the lifespan handler in ``main.py`` sets ``app.state.coalesce_buffer`` once.
    """
    return cast(CoalesceBuffer, request.app.state.coalesce_buffer)
