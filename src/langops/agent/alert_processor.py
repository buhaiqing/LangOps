"""Alert Processor - Main orchestrator for alert analysis."""

import time
from datetime import timedelta

from langfuse import Langfuse, observe, propagate_attributes

from langops.agent.predictive_engine import PredictiveEngine
from langops.agent.rca_engine import RCAEngine
from langops.collectors import AliyunCmsCollector, PrometheusCollector
from langops.core import get_logger
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
from langops.services import NotificationService

logger = get_logger(__name__)


class AlertProcessor:
    """Main alert processor that orchestrates the analysis pipeline."""

    def __init__(
        self,
        langfuse: Langfuse,
        rca_engine: RCAEngine,
        vector_store: VectorStore,
        prometheus_collector: PrometheusCollector | None = None,
        aliyun_collector: AliyunCmsCollector | None = None,
        notification_service: NotificationService | None = None,
        predictive_engine: PredictiveEngine | None = None,
    ) -> None:
        self.langfuse = langfuse
        self.rca_engine = rca_engine
        self.vector_store = vector_store
        self.prometheus_collector = prometheus_collector
        self.aliyun_collector = aliyun_collector
        self.notification_service = notification_service
        self.predictive_engine = predictive_engine
        logger.info("AlertProcessor initialized")

    @observe(as_type="agent")
    async def process(self, alert: Alert) -> AnalysisResult:
        """Process an alert through the complete analysis pipeline."""
        start_time = time.time()

        with propagate_attributes(
            user_id=alert.source.system,
            trace_name="alert_analysis",
            metadata={
                "alert_id": alert.id,
                "alert_title": alert.title,
                "severity": alert.severity.value,
                "category": alert.category.value,
                "source_type": alert.source.type,
            },
        ):
            logger.info("Starting alert processing", alert_id=alert.id, title=alert.title)

            try:
                context = await self._collect_context(alert)
                root_cause = await self._analyze_root_cause(alert, context)
                similar_cases = await self._retrieve_similar_cases(alert)
                suggestion = await self._generate_remediation(
                    root_cause,
                    similar_cases,
                    alert,
                )
                impact_prediction = await self._predict_impact(alert, context, root_cause)

                processing_time = time.time() - start_time
                trace_id = self.langfuse.get_current_trace_id() or f"local-{alert.id}"

                result = AnalysisResult(
                    alert_id=alert.id,
                    trace_id=trace_id,
                    root_cause=root_cause,
                    similar_cases=similar_cases,
                    suggestion=suggestion,
                    impact_prediction=impact_prediction,
                    processing_time_seconds=processing_time,
                )

                logger.info(
                    "Alert processing completed",
                    alert_id=alert.id,
                    trace_id=result.trace_id,
                    processing_time=processing_time,
                    confidence=root_cause.confidence,
                )

                if self.notification_service:
                    try:
                        await self.notification_service.notify_analysis(alert, result)
                    except Exception as exc:
                        logger.warning(
                            "Failed to send notification",
                            alert_id=alert.id,
                            error=str(exc),
                        )

                return result

            except AnalysisError:
                raise
            except Exception as exc:
                logger.error("Alert processing failed", alert_id=alert.id, error=str(exc))
                raise AnalysisError(f"Failed to process alert {alert.id}: {exc}") from exc

    @observe(as_type="span")
    async def _collect_context(self, alert: Alert) -> AlertContext:
        """Collect context data for the alert."""
        context = AlertContext(alert=alert)

        if self.prometheus_collector and alert.source.type == "kubernetes":
            try:
                metrics = await self.prometheus_collector.collect(
                    alert,
                    time_window=timedelta(minutes=30),
                )
                context.metrics = metrics
                logger.info(
                    "Collected Prometheus metrics",
                    alert_id=alert.id,
                    metrics_count=len(metrics),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to collect Prometheus metrics",
                    alert_id=alert.id,
                    error=str(exc),
                )
                context.metrics = {"error": str(exc)}

        if self.aliyun_collector and alert.source.type == "aliyun":
            try:
                metrics = await self.aliyun_collector.collect(
                    alert,
                    time_window=timedelta(minutes=30),
                )
                context.metrics = metrics
                logger.info(
                    "Collected Aliyun CMS metrics",
                    alert_id=alert.id,
                    metrics_count=len(metrics),
                )
            except Exception as exc:
                logger.warning(
                    "Failed to collect Aliyun CMS metrics",
                    alert_id=alert.id,
                    error=str(exc),
                )
                context.metrics = {"error": str(exc)}

        context.logs = []
        context.events = []
        return context

    @observe(as_type="generation")
    async def _analyze_root_cause(self, alert: Alert, context: AlertContext) -> RootCause:
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
            events=context.events,
        )

    @observe(as_type="span")
    async def _retrieve_similar_cases(self, alert: Alert, top_k: int = 3) -> list[SimilarCase]:
        """Retrieve similar cases from knowledge base."""
        query = f"{alert.title} {alert.description}"

        try:
            results = await self.vector_store.search(
                query=query,
                top_k=top_k,
                filter_category=alert.category.value,
            )

            similar_cases = [
                SimilarCase(
                    case_id=result.id,
                    similarity_score=result.score,
                    title=str(result.metadata.get("title", "")),
                    root_cause=str(result.metadata.get("root_cause", "")),
                    solution=str(result.metadata.get("solution", "")),
                    resolution_time=result.metadata.get("resolution_time"),
                )
                for result in results
            ]

            logger.info("Retrieved similar cases", alert_id=alert.id, count=len(similar_cases))
            return similar_cases

        except Exception as exc:
            logger.warning("Failed to retrieve similar cases", alert_id=alert.id, error=str(exc))
            return []

    @observe(as_type="generation")
    async def _generate_remediation(
        self,
        root_cause: RootCause,
        similar_cases: list[SimilarCase],
        alert: Alert,
    ) -> RemediationSuggestion:
        """Generate remediation suggestion."""
        alert_context = {
            "service": alert.source.service or "unknown",
            "namespace": alert.source.namespace or "unknown",
            "resource_type": alert.source.resource_type or "unknown",
        }

        return await self.rca_engine.generate_remediation(
            root_cause=root_cause,
            similar_cases=similar_cases,
            alert_context=alert_context,
        )

    @observe(as_type="span")
    async def _predict_impact(
        self,
        alert: Alert,
        context: AlertContext,
        root_cause: RootCause,
    ) -> dict:
        """Predict future impact from metric trends."""
        if self.predictive_engine:
            try:
                prediction = await self.predictive_engine.predict_impact(
                    alert,
                    context,
                    root_cause,
                )
                return prediction.model_dump()
            except Exception as exc:
                logger.warning("Impact prediction failed", alert_id=alert.id, error=str(exc))

        return {"affected_service": alert.source.service, "overall_risk": "unknown"}
