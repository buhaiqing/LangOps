"""Remediation API tests."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from langops.models import RemediationPlan, RemediationStatus
from langops.services.remediation_executor import RemediationExecutor, RemediationRegistry
from langops.web.dependencies import get_remediation_executor, get_remediation_registry
from langops.web.main import create_app


def test_execute_remediation_plan_dry_run() -> None:
    registry = RemediationRegistry()
    plan = RemediationPlan(
        plan_id="plan-test01",
        alert_id="alert-1",
        trace_id="trace-1",
        summary="扩容",
        commands=["kubectl scale deployment/order --replicas=3"],
        risk_level="low",
    )
    registry.save(plan)

    executor = RemediationExecutor(execution_enabled=False)
    app = create_app()
    app.dependency_overrides[get_remediation_registry] = lambda: registry
    app.dependency_overrides[get_remediation_executor] = lambda: executor
    client = TestClient(app)

    response = client.post(
        "/api/v1/remediation/plan-test01/execute",
        json={"approved_by": "ops-user", "confirm": True, "dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["plan"]["status"] == RemediationStatus.DRY_RUN.value


def test_reject_remediation_plan() -> None:
    registry = RemediationRegistry()
    plan = RemediationPlan(
        plan_id="plan-test02",
        alert_id="alert-2",
        trace_id="trace-2",
        summary="扩容",
        commands=["kubectl scale deployment/order --replicas=3"],
        risk_level="low",
    )
    registry.save(plan)

    app = create_app()
    app.dependency_overrides[get_remediation_registry] = lambda: registry
    app.dependency_overrides[get_remediation_executor] = lambda: RemediationExecutor()
    client = TestClient(app)

    response = client.post(
        "/api/v1/remediation/plan-test02/reject",
        json={"rejected_by": "ops-lead", "reason": "窗口期禁止变更"},
    )

    assert response.status_code == 200
    assert response.json()["plan"]["status"] == RemediationStatus.REJECTED.value
