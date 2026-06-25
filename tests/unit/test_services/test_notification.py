"""Notification service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.models import (
    Alert,
    AlertCategory,
    AlertSeverity,
    AlertSource,
    AnalysisResult,
    RemediationSuggestion,
    RootCause,
)
from langops.services import NotificationService


def _analysis_result() -> AnalysisResult:
    return AnalysisResult(
        alert_id="alert-001",
        trace_id="trace-123",
        root_cause=RootCause(category="资源不足", description="CPU 过高", confidence=0.9),
        suggestion=RemediationSuggestion(summary="升配", steps=["调整 limit"]),
        processing_time_seconds=1.0,
    )


def _alert() -> Alert:
    return Alert(
        id="alert-001",
        title="CPU过高",
        description="CPU > 90%",
        severity=AlertSeverity.CRITICAL,
        category=AlertCategory.RESOURCE,
        source=AlertSource(type="kubernetes", system="prod"),
    )


@pytest.mark.asyncio
async def test_notify_analysis_sends_to_configured_channels() -> None:
    service = NotificationService(
        feishu_webhook="https://feishu.example/hook",
        dingtalk_webhook="https://dingtalk.example/hook",
    )
    service.send_feishu = AsyncMock(return_value=True)
    service.send_dingtalk = AsyncMock(return_value=True)

    outcomes = await service.notify_analysis(_alert(), _analysis_result())

    assert outcomes == {"feishu": True, "dingtalk": True}
    service.send_feishu.assert_awaited_once()
    service.send_dingtalk.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_feishu_posts_text_payload() -> None:
    service = NotificationService(feishu_webhook="https://feishu.example/hook")
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"StatusCode": 0})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.return_value = mock_response
    service._get_session = AsyncMock(return_value=mock_session)

    ok = await service.send_feishu("hello")

    assert ok is True
    args = mock_session.post.call_args
    assert args[0][0] == "https://feishu.example/hook"
    assert args[1]["json"]["msg_type"] == "text"


@pytest.mark.asyncio
async def test_send_dingtalk_returns_false_on_http_error() -> None:
    service = NotificationService(dingtalk_webhook="https://dingtalk.example/hook")
    mock_response = AsyncMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="error")
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post.return_value = mock_response
    service._get_session = AsyncMock(return_value=mock_session)

    assert await service.send_dingtalk("hello") is False


def test_enabled_false_without_webhooks() -> None:
    service = NotificationService()
    assert service.enabled is False
