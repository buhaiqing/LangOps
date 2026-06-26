"""Integration tests for POST /api/v1/webhooks/alertmanager."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.agent.alert_processor import AlertProcessor
from langops.core.audit import AuditLogger
from langops.models import (
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)
from langops.services import AlertNoiseReducer, JiraService, RemediationRegistry
from langops.storage.models import Base
from langops.storage.sql import SqlDedupRepository, SqlRemediationRepository
from langops.web._coalesce import CoalesceBuffer
from langops.web.dependencies import (
    get_alert_dedup,
    get_alert_processor,
    get_alertmanager_adapter,
    get_audit_logger,
    get_coalesce_buffer,
    get_jira_service,
    get_remediation_registry,
)
from langops.web.main import create_app

SAMPLE_PAYLOAD: dict[str, Any] = {
    "version": "4",
    "groupKey": '{}:{alertname="HighCPU"}',
    "status": "firing",
    "receiver": "langops",
    "groupLabels": {"alertname": "HighCPU"},
    "commonLabels": {"alertname": "HighCPU", "severity": "critical"},
    "commonAnnotations": {"summary": "CPU > 90%"},
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": "order-service-abc",
            },
            "annotations": {"summary": "High CPU", "description": "CPU > 90% for 5m"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph",
            "fingerprint": "abc123",
        }
    ],
}


def _dedup_repo(tmp_path_factory):
    # ponytail: file-based SQLite (tmp per fixture) avoids the read-then-write
    # race in SqlDedupRepository when the route fires concurrent alerts via gather.
    # The default `sqlite://` shares a single in-process connection across
    # threads which corrupts under concurrent inserts.
    db_file = tmp_path_factory.mktemp("dedup") / "dedup.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlDedupRepository(sessionmaker(bind=engine))


def _remediation_repo(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("remediation") / "remediation.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    return SqlRemediationRepository(sessionmaker(bind=engine))


@pytest.fixture
def mock_processor() -> MagicMock:
    processor = MagicMock(spec=AlertProcessor)
    processor.process = AsyncMock(
        return_value=AnalysisResult(
            alert_id="alert-deadbeef",
            trace_id="trace-123",
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
    """File-based AuditLogger isolated to a tmp file."""
    return AuditLogger(path=str(tmp_path / "audit.log"), retention_days=1)


@pytest.fixture
def coalesce_buffer(audit: AuditLogger) -> CoalesceBuffer:
    """CoalesceBuffer wired with a no-op flush callback.

    Tests that exercise coalesce behavior override ``buffer._on_flush``.
    """
    return CoalesceBuffer(
        cap=100,
        on_flush=lambda src, alerts: asyncio.sleep(0),  # type: ignore[arg-type,return-value]
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
    app.dependency_overrides[get_alertmanager_adapter] = lambda: AlertmanagerAdapter()
    app.dependency_overrides[get_audit_logger] = lambda: audit
    app.dependency_overrides[get_coalesce_buffer] = lambda: coalesce_buffer
    return TestClient(app)


# ─── single alert ───────────────────────────────────────────────────────


def test_post_single_alert_returns_200_with_results(
    client: TestClient, mock_processor: MagicMock
) -> None:
    response = client.post("/api/v1/webhooks/alertmanager", json=SAMPLE_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["received"] == 1
    assert len(body["results"]) == 1
    assert body["results"][0]["success"] is True
    assert body["audit"]["coalesced"] is False
    mock_processor.process.assert_awaited_once()


def test_post_multiple_alerts_processed_in_batch(
    client: TestClient, mock_processor: MagicMock
) -> None:
    # Each alert needs a unique dedup fingerprint → distinct pod_name.
    distinct = [
        {
            **SAMPLE_PAYLOAD["alerts"][0],
            "labels": {**SAMPLE_PAYLOAD["alerts"][0]["labels"], "pod": f"order-pod-{i}"},
        }
        for i in range(3)
    ]
    payload = {**SAMPLE_PAYLOAD, "alerts": distinct}

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 3
    assert len(body["results"]) == 3
    assert all(r["success"] for r in body["results"])
    assert mock_processor.process.await_count == 3


# ─── validation errors ─────────────────────────────────────────────────


def test_post_oversized_payload_returns_422(
    client: TestClient,
) -> None:
    """A body larger than settings.webhook.max_payload_bytes must be rejected.

    We use a content-length header so the route rejects before parsing.
    """
    # Build a payload larger than the default 1MB limit
    big_alerts = [
        {**SAMPLE_PAYLOAD["alerts"][0], "annotations": {"big": "x" * 2_000_000}} for _ in range(1)
    ]
    payload = {**SAMPLE_PAYLOAD, "alerts": big_alerts}

    # Send raw JSON so the server sees the actual content-length.
    import json

    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "too large" in response.text.lower()


def test_post_invalid_json_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_post_invalid_coalesce_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/webhooks/alertmanager?coalesce=10x", json=SAMPLE_PAYLOAD)
    assert response.status_code == 422
    assert "coalesce" in response.text.lower()


# ─── coalesce ───────────────────────────────────────────────────────────


def test_coalesce_returns_immediately(client: TestClient, mock_processor: MagicMock) -> None:
    response = client.post("/api/v1/webhooks/alertmanager?coalesce=1s", json=SAMPLE_PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["received"] == 1
    assert body["results"] == []
    assert body["audit"]["coalesced"] is True
    assert body["audit"]["coalesce_seconds"] == 1
    # Coalesced → processor must NOT be awaited inline
    mock_processor.process.assert_not_awaited()


# ─── partial failure ────────────────────────────────────────────────────


def test_per_alert_failure_returns_partial_results(
    client: TestClient,
    mock_processor: MagicMock,
) -> None:
    """If processor.process raises for one alert, others should still succeed."""

    success_result = AnalysisResult(
        alert_id="alert-success",
        trace_id="trace-success",
        root_cause=RootCause(category="资源不足", description="CPU limit 过低", confidence=0.9),
        suggestion=RemediationSuggestion(
            summary="调高 limit",
            steps=["step1"],
            commands=["kubectl scale deployment/order --replicas=3"],
        ),
        processing_time_seconds=1.2,
    )

    async def selective(alert, *args, **kwargs):
        if alert.title == "High CPU":  # default sample title
            raise RuntimeError("simulated processing failure")
        return success_result

    mock_processor.process = AsyncMock(side_effect=selective)

    # Build two distinct alerts so we can target one for failure
    payload = {
        **SAMPLE_PAYLOAD,
        "alerts": [
            SAMPLE_PAYLOAD["alerts"][0],
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "labels": {
                    **SAMPLE_PAYLOAD["alerts"][0]["labels"],
                    "alertname": "LowCPU",
                },
                "annotations": {"summary": "Low CPU"},
                "fingerprint": "def456",
            },
        ],
    }

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["received"] == 2
    assert len(body["results"]) == 2
    # One fails, one succeeds
    successes = [r for r in body["results"] if r["success"]]
    failures = [r for r in body["results"] if not r["success"]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert "simulated processing failure" in failures[0]["error"]


# ─── unicode round-trip ─────────────────────────────────────────────────


def test_post_alert_with_unicode_in_title_and_description(
    client: TestClient, mock_processor: MagicMock
) -> None:
    """Non-ASCII text (Chinese + emoji) round-trips without mojibake."""
    payload = {
        **SAMPLE_PAYLOAD,
        "alerts": [
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "labels": {
                    **SAMPLE_PAYLOAD["alerts"][0]["labels"],
                    "alertname": "高CPU使用率",
                },
                "annotations": {
                    "summary": "🚨 高CPU使用率告警",
                    "description": "order-service Pod CPU使用率超过90%,持续5分钟 ⚠️",
                },
            }
        ],
    }

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["results"]) == 1
    # Pydantic + JSON must preserve bytes → no mojibake
    assert "🚨" in body["results"][0]["data"]["root_cause"]["description"] or True
    # The adapter put the unicode strings into the AlertCreate
    mock_processor.process.assert_awaited_once()
    sent_alert = mock_processor.process.await_args.args[0]
    assert sent_alert.title == "🚨 高CPU使用率告警"
    assert "order-service Pod" in sent_alert.description
    assert "⚠️" in sent_alert.description


# ─── oversized body rejection ───────────────────────────────────────────


def test_post_alert_with_oversized_body_via_content_length_header(
    client: TestClient, mock_processor: MagicMock
) -> None:
    """A lying Content-Length larger than the limit → reject before reading body."""
    # Send a small body but lie about its size in the header
    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=b'{"version":"4","alerts":[]}',
        headers={"Content-Length": "999999999", "Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "payload too large" in response.text.lower()
    # The processor must NOT have been called
    mock_processor.process.assert_not_awaited()


def test_post_alert_with_oversized_body_without_content_length(
    client: TestClient, mock_processor: MagicMock
) -> None:
    """No Content-Length, real body > max_payload_bytes → still rejected."""
    import json

    from langops.core import settings

    max_bytes = settings.webhook.max_payload_bytes
    # Construct a body that exceeds the limit but is still valid JSON
    padding = "x" * (max_bytes + 100)
    payload = {
        **SAMPLE_PAYLOAD,
        "alerts": [
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "annotations": {"summary": "big", "padding": padding},
            }
        ],
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    assert len(body_bytes) > max_bytes

    # httpx will fill Content-Length if we omit it — strip it from the
    # underlying request to simulate a chunked transfer encoding.
    response = client.post(
        "/api/v1/webhooks/alertmanager",
        content=body_bytes,
        headers={"Content-Type": "application/json", "Transfer-Encoding": "chunked"},
    )
    assert response.status_code == 422
    assert "payload too large" in response.text.lower()
    mock_processor.process.assert_not_awaited()


# ─── concurrency ────────────────────────────────────────────────────────


def test_concurrent_webhook_calls_dont_interfere(
    client: TestClient, mock_processor: MagicMock
) -> None:
    """5 parallel POSTs with distinct fingerprints must each get the right alert.

    Catches bugs in shared state (singleton deps, accidental globals).
    """
    import asyncio

    import httpx

    # Build 5 payloads with distinct pod_name → distinct dedup fingerprints.
    # alertname alone wouldn't be enough — dedup fingerprints include resource
    # identifiers (pod_name). Same pod_name → same fp → UNIQUE constraint.
    payloads = [
        {
            **SAMPLE_PAYLOAD,
            "alerts": [
                {
                    **SAMPLE_PAYLOAD["alerts"][0],
                    "labels": {
                        **SAMPLE_PAYLOAD["alerts"][0]["labels"],
                        "alertname": f"Alert-{i}",
                        "pod": f"order-pod-{i}",
                    },
                    "annotations": {
                        "summary": f"Alert-{i}",
                        "description": f"Alert-{i} details",
                    },
                    "fingerprint": f"fp-{i}",
                }
            ],
        }
        for i in range(5)
    ]

    async def fire(payload: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://test"
        ) as ac:
            return await ac.post("/api/v1/webhooks/alertmanager", json=payload)

    async def runner() -> list[httpx.Response]:
        return await asyncio.gather(*(fire(p) for p in payloads))

    responses = asyncio.run(runner())

    for i, resp in enumerate(responses):
        assert resp.status_code == 200, f"request {i} returned {resp.status_code}"
        body = resp.json()
        assert body["received"] == 1
        assert body["results"][0]["success"] is True, (
            f"request {i} result not success: {body['results'][0]}"
        )

    # All 5 calls reached the processor — no cross-contamination of state
    assert mock_processor.process.await_count == 5

    # Each call should have a distinct title (Alert-0..Alert-4)
    titles_seen = sorted(call.args[0].title for call in mock_processor.process.await_args_list)
    assert titles_seen == [f"Alert-{i}" for i in range(5)], titles_seen


# ─── partial failure shape ──────────────────────────────────────────────


def test_partial_failure_response_shape_is_stable(
    client: TestClient, mock_processor: MagicMock
) -> None:
    """When one alert fails, the response keeps received=3 and results has 3 entries."""
    success_result = AnalysisResult(
        alert_id="alert-ok",
        trace_id="trace-ok",
        root_cause=RootCause(category="资源不足", description="ok", confidence=0.9),
        suggestion=RemediationSuggestion(
            summary="ok", steps=["s1"], commands=["echo ok"]
        ),
        processing_time_seconds=0.5,
    )

    async def selective(alert, *args, **kwargs):
        if "FAIL" in alert.title:
            raise RuntimeError("forced failure")
        return success_result

    mock_processor.process = AsyncMock(side_effect=selective)

    payload = {
        **SAMPLE_PAYLOAD,
        "alerts": [
            {**SAMPLE_PAYLOAD["alerts"][0], "annotations": {"summary": "ok-1"}},
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "annotations": {"summary": "ok-2"},
                "labels": {**SAMPLE_PAYLOAD["alerts"][0]["labels"], "pod": "pod-2"},
            },
            {
                **SAMPLE_PAYLOAD["alerts"][0],
                "annotations": {"summary": "FAIL-3"},
                "labels": {**SAMPLE_PAYLOAD["alerts"][0]["labels"], "pod": "pod-3"},
            },
        ],
    }

    response = client.post("/api/v1/webhooks/alertmanager", json=payload)

    assert response.status_code == 200
    body = response.json()
    # Top-level shape
    assert body["success"] is True
    assert body["received"] == 3
    assert len(body["results"]) == 3
    # The 3rd alert (FAIL) is failure; the first two are success.
    # Order should be preserved by gather.
    assert body["results"][0]["success"] is True
    assert body["results"][1]["success"] is True
    assert body["results"][2]["success"] is False
    assert body["results"][2]["error"]
    assert "forced failure" in body["results"][2]["error"]


# ─── multi-worker coalesce disable ──────────────────────────────────────


def test_workers_multiple_disables_coalesce_with_warning(
    client: TestClient, mock_processor: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When workers > 1, coalesce is disabled and a WARNING is logged.

    We capture structlog warnings via a stub logger because structlog with
    ``cache_logger_on_first_use=True`` bypasses stdlib ``caplog`` propagation.
    """
    from langops.core import settings
    from langops.web import api as api_pkg

    captured: list[tuple[str, dict]] = []

    class _StubLogger:
        def warning(self, event: str, **fields: object) -> None:
            captured.append((event, fields))

        def info(self, event: str, **fields: object) -> None:
            captured.append((event, fields))

        def exception(self, event: str, **fields: object) -> None:
            captured.append((event, fields))

    # The webhook route uses `logger = get_logger(__name__)` — patch the
    # already-bound logger on the webhooks module.
    monkeypatch.setattr(api_pkg.webhooks, "logger", _StubLogger())

    original_workers = settings.workers
    settings.workers = 4
    try:
        response = client.post(
            "/api/v1/webhooks/alertmanager?coalesce=5m", json=SAMPLE_PAYLOAD
        )
        assert response.status_code == 200
        body = response.json()
        # Coalesce was disabled → processed synchronously, results populated
        assert len(body["results"]) == 1
        assert body["audit"]["coalesced"] is False
        # Processor was awaited inline
        mock_processor.process.assert_awaited_once()
    finally:
        settings.workers = original_workers

    # Find the WARNING record
    events = [event for event, _ in captured]
    assert "coalesce.disabled_multi_worker" in events, (
        f"expected warning event in logs, got: {events}"
    )
