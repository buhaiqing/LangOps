"""Remediation API tests."""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from langops.models import RemediationPlan, RemediationStatus
from langops.services.remediation_executor import RemediationExecutor, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlRemediationRepository
from langops.web.dependencies import get_remediation_executor, get_remediation_registry
from langops.web.main import create_app


def _repo():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


def test_execute_remediation_plan_dry_run() -> None:
    registry = RemediationRegistry(repo=_repo())
    executor = RemediationExecutor(execution_enabled=False)
    app = create_app()
    app.dependency_overrides[get_remediation_registry] = lambda: registry
    app.dependency_overrides[get_remediation_executor] = lambda: executor
    client = TestClient(app)

    response = client.post(
        "/api/v1/remediation/nonexistent/execute",
        json={"approved_by": "ops-user", "confirm": True, "dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False


def test_reject_remediation_plan() -> None:
    registry = RemediationRegistry(repo=_repo())
    app = create_app()
    app.dependency_overrides[get_remediation_registry] = lambda: registry
    app.dependency_overrides[get_remediation_executor] = lambda: RemediationExecutor()
    client = TestClient(app)

    response = client.post(
        "/api/v1/remediation/nonexistent/reject",
        json={"rejected_by": "ops-lead", "reason": "窗口期禁止变更"},
    )

    assert response.status_code == 200
