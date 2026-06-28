"""Integration tests for POST /api/v1/webhooks/aliyun-cms (阿里云云监控回调).

流程测试报告说明
────────────────
每条测试方法名使用 test_<场景>_<期望行为> 格式，运行 pytest -v 可清晰查看
每条回调流程的覆盖路径：CMS 推送 → 适配器映射 → AlertCreate → 分析流水线。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from langops.adapters.aliyun_cms import AliyunCmsWebhookAdapter
from langops.agent.alert_processor import AlertProcessor
from langops.core.audit import AuditLogger
from langops.models import (
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)
from langops.models.webhook import AliyunCmsCallbackPayload
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web._coalesce import CoalesceBuffer
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_aliyun_cms_adapter,
    get_audit_logger,
    get_coalesce_buffer,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.main import create_app

# ─── CMS 回调模拟数据 ─────────────────────────────────────────────────────

SAMPLE_ECS_CALLBACK: dict[str, Any] = {
    "alertName": "CPU使用率过高",
    "alertState": "ALERT",
    "curValue": "95.5",
    "dimensions": '{"instanceId":"i-bp1abcd1234"}',
    "expression": "Average > 90",
    "instanceName": "web-server-01",
    "metricName": "CPUUtilization",
    "namespace": "acs_ecs_dashboard",
    "regionId": "cn-hangzhou",
    "timestamp": "1705300000000",
    "userId": "123456789",
    "level": "critical",
}

SAMPLE_RDS_CALLBACK: dict[str, Any] = {
    **SAMPLE_ECS_CALLBACK,
    "alertName": "RDS连接数过高",
    "namespace": "acs_rds_dashboard",
    "metricName": "ConnectionUsage",
    "level": "warning",
    "dimensions": '{"instanceId":"rm-bp1efgh5678"}',
}


def _dedup_repo(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("cms_dedup") / "dedup.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlDedupRepository(sessionmaker(bind=engine))


def _remediation_repo(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("cms_remediation") / "remediation.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


@pytest.fixture
def mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-cms-test",
            trace_id="trace-cms",
            root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
            suggestion=RemediationSuggestion(
                summary="调高 limit",
                steps=["step1"],
                commands=["kubectl scale deployment/order --replicas=3"],
            ),
            processing_time_seconds=1.2,
        )
    )
    return processor


@pytest.fixture
def dedup(tmp_path_factory) -> AlertNoiseReducer:
    return AlertNoiseReducer(repo=_dedup_repo(tmp_path_factory), window_seconds=900, enabled=True)


@pytest.fixture
def remediation_registry(tmp_path_factory) -> RemediationRegistry:
    return RemediationRegistry(repo=_remediation_repo(tmp_path_factory))


@pytest.fixture
def jira() -> JiraService:
    return JiraService(url="", username="", api_token="", enabled=False)


@pytest.fixture
def audit(tmp_path) -> AuditLogger:
    return AuditLogger(path=str(tmp_path / "cms_audit.log"), retention_days=1)


@pytest.fixture
def coalesce_buffer(audit: AuditLogger) -> CoalesceBuffer:
    return CoalesceBuffer(
        cap=100,
        on_flush=lambda src, alerts: None,  # type: ignore[arg-type,return-value]
        window_seconds=5.0,
        audit=audit,
    )


@pytest.fixture
def client(
    mock_processor: MagicMock,
    dedup: AlertNoiseReducer,
    remediation_registry: RemediationRegistry,
    jira: JiraService,
    audit: AuditLogger,
    coalesce_buffer: CoalesceBuffer,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_alert_processor] = lambda: mock_processor
    app.dependency_overrides[get_alert_dedup] = lambda: dedup
    app.dependency_overrides[get_remediation_registry] = lambda: remediation_registry
    app.dependency_overrides[get_jira_service] = lambda: jira
    app.dependency_overrides[get_aliyun_cms_adapter] = lambda: AliyunCmsWebhookAdapter()
    app.dependency_overrides[get_audit_logger] = lambda: audit
    app.dependency_overrides[get_coalesce_buffer] = lambda: coalesce_buffer
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 测试报告：CMS ECS 告警回调流程
# ═══════════════════════════════════════════════════════════════════════════


class TestCmsEcsAlert:
    """阿里云 CMS → ECS 告警回调：ECS CPU 超限场景"""

    def test_ecs_cpu_callback_returns_200_with_result(
        self, client: TestClient, mock_processor: MagicMock
    ) -> None:
        """流程: CMS推送ECS告警 → 200 + processor被调用 + AlertCreate数据正确"""
        response = client.post("/api/v1/webhooks/aliyun-cms", json=SAMPLE_ECS_CALLBACK)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["received"] == 1
        assert len(body["results"]) == 1
        assert body["results"][0]["success"] is True
        mock_processor.process.assert_awaited_once()

        # 验证 CMS → AlertCreate 映射的正确性
        sent = mock_processor.process.await_args.args[0]
        assert sent.title == "CPU使用率过高"
        assert sent.source.type == "aliyun"
        assert sent.source.resource_type == "ecs"
        assert sent.source.instance_id == "i-bp1abcd1234"
        assert sent.severity.value == "critical"
        assert sent.category.value == "resource"

    def test_ecs_metric_context_is_preserved(
        self, client: TestClient, mock_processor: MagicMock
    ) -> None:
        """流程: CMS上下文完整透传 → context中包含metricName/expression等字段"""
        response = client.post("/api/v1/webhooks/aliyun-cms", json=SAMPLE_ECS_CALLBACK)
        assert response.status_code == 200

        sent = mock_processor.process.await_args.args[0]
        assert sent.context["metric_name"] == "CPUUtilization"
        assert sent.context["namespace"] == "acs_ecs_dashboard"
        assert sent.context["cur_value"] == "95.5"
        assert sent.context["expression"] == "Average > 90"
        assert sent.context["alert_state"] == "ALERT"
        assert sent.context["region_id"] == "cn-hangzhou"

    def test_ecs_alert_with_unicode(self, client: TestClient, mock_processor: MagicMock) -> None:
        """流程: 中文告警名 + 特殊字符 → 无乱码穿越"""
        payload = {
            **SAMPLE_ECS_CALLBACK,
            "alertName": "ECS 🚨 CPU使用率超过99%",
        }
        response = client.post("/api/v1/webhooks/aliyun-cms", json=payload)
        assert response.status_code == 200

        sent = mock_processor.process.await_args.args[0]
        assert "🚨" in sent.title
        assert "99%" in sent.title


# ═══════════════════════════════════════════════════════════════════════════
# 测试报告：CMS RDS 告警回调流程
# ═══════════════════════════════════════════════════════════════════════════


class TestCmsRdsAlert:
    """阿里云 CMS → RDS 告警回调：RDS 连接数/磁盘场景"""

    def test_rds_callback_returns_200(
        self, client: TestClient, mock_processor: MagicMock
    ) -> None:
        """流程: CMS推送RDS告警 → 200 + resource_type=rds"""
        response = client.post("/api/v1/webhooks/aliyun-cms", json=SAMPLE_RDS_CALLBACK)
        assert response.status_code == 200

        sent = mock_processor.process.await_args.args[0]
        assert sent.source.resource_type == "rds"
        assert sent.source.instance_id == "rm-bp1efgh5678"

    def test_rds_warning_severity_mapped(
        self, client: TestClient, mock_processor: MagicMock
    ) -> None:
        """流程: level=warning → severity=high"""
        response = client.post("/api/v1/webhooks/aliyun-cms", json=SAMPLE_RDS_CALLBACK)
        assert response.status_code == 200

        sent = mock_processor.process.await_args.args[0]
        assert sent.severity.value == "high"


# ═══════════════════════════════════════════════════════════════════════════
# 测试报告：CMS 恢复通知 / 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestCmsResolution:
    """CMS 恢复通知与异常处理"""

    def test_ok_state_skips_processing(self, client: TestClient, mock_processor: MagicMock) -> None:
        """流程: alertState=OK(恢复通知) → 200 + 跳过processor"""
        payload = {**SAMPLE_ECS_CALLBACK, "alertState": "OK"}
        response = client.post("/api/v1/webhooks/aliyun-cms", json=payload)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        # 恢复通知不触发分析流水线
        mock_processor.process.assert_not_awaited()

    def test_invalid_json_returns_422(self, client: TestClient, mock_processor: MagicMock) -> None:
        """流程: 无效JSON → 422"""
        response = client.post(
            "/api/v1/webhooks/aliyun-cms",
            content=b"{bad-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        mock_processor.process.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════
# 测试报告：Adapter 单元测试 — CMS → AlertCreate 映射逻辑
# ═══════════════════════════════════════════════════════════════════════════


class TestAliyunCmsAdapterUnit:
    """CMS Adapter 映射规则：severity / category / dimensions 解析"""

    def _make_payload(self, **overrides: Any) -> AliyunCmsCallbackPayload:
        return AliyunCmsCallbackPayload(**{**SAMPLE_ECS_CALLBACK, **overrides})

    def test_severity_critical_maps_to_critical(self) -> None:
        """severity映射: level=critical → AlertSeverity.CRITICAL"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(level="critical"))
        assert result.severity.value == "critical"

    def test_severity_info_maps_to_info(self) -> None:
        """severity映射: level=info → AlertSeverity.INFO"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(level="info"))
        assert result.severity.value == "info"

    def test_namespace_ecs_infers_resource_category(self) -> None:
        """分类推断: acs_ecs_dashboard → 自动归类为 resource"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(namespace="acs_ecs_dashboard"))
        assert result.category.value == "resource"

    def test_namespace_rds_infers_resource_category(self) -> None:
        """分类推断: acs_rds_dashboard → resource"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(namespace="acs_rds_dashboard"))
        assert result.category.value == "resource"

    def test_namespace_slb_infers_performance_category(self) -> None:
        """分类推断: acs_slb_dashboard → performance"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(namespace="acs_slb_dashboard"))
        assert result.category.value == "performance"

    def test_dimensions_parsed_correctly(self) -> None:
        """dimensions JSON解析: JSON字符串 → dict"""
        adapter = AliyunCmsWebhookAdapter()
        dims = '{"instanceId":"i-test123","host":"web-01"}'
        result = adapter.to_alert_create(self._make_payload(dimensions=dims))
        assert result.source.instance_id == "i-test123"
        assert result.context["dimensions"] == {"instanceId": "i-test123", "host": "web-01"}

    def test_empty_dimensions_returns_empty(self) -> None:
        """dimensions为空: 空字符串 → 空dict, instance_id为空"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload(dimensions=""))
        assert result.source.instance_id == ""

    def test_description_includes_expression_and_value(self) -> None:
        """description构建: 拼接 expression + curValue"""
        adapter = AliyunCmsWebhookAdapter()
        result = adapter.to_alert_create(self._make_payload())
        assert "Average > 90" in result.description
        assert "95.5" in result.description
