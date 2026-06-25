"""JIRA integration service tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from langops.services.jira_integration import JiraService, _build_description


class TestBuildDescription:
    """Tests for the _build_description helper."""

    def test_includes_all_sections(self) -> None:
        desc = _build_description(
            alert_id="alert-001",
            severity="critical",
            category="resource",
            source_type="kubernetes",
            system="prod-cluster",
            resource="order-pod",
            root_cause="CPU 使用率过高",
            confidence=0.92,
            evidence=["CPU > 90%", "OOMKilled x3"],
            summary="扩容 Pod 资源限制",
            risk_level="low",
            steps=["kubectl set resources", "kubectl rollout restart"],
            trace_id="trace-abc",
            remediation_plan_id="plan-001",
        )
        assert "Alert ID" in desc
        assert "order-pod" in desc
        assert "trace-abc" in desc
        assert "plan-001" in desc
        assert "CPU" in desc
        assert "92" in desc
        assert "kubectl" in desc
        assert "panic" not in desc

    def test_no_resource_omits_row(self) -> None:
        desc = _build_description(
            alert_id="alert-002",
            severity="high",
            category="performance",
            source_type="prometheus",
            system="prod",
            resource=None,
            root_cause="慢查询",
            confidence=0.8,
            evidence=[],
            summary="优化索引",
            risk_level="medium",
            steps=[],
            trace_id="trace-xyz",
        )
        assert "| Resource |" not in desc
        assert "trace-xyz" in desc

    def test_no_remediation_plan_omits_link(self) -> None:
        desc = _build_description(
            alert_id="alert-003",
            severity="low",
            category="availability",
            source_type="aliyun",
            system="staging",
            resource="i-abc",
            root_cause="磁盘空间不足",
            confidence=0.75,
            evidence=["disk > 90%"],
            summary="清理日志",
            risk_level="low",
            steps=["cleanup"],
            trace_id="trace-def",
            remediation_plan_id=None,
        )
        assert "Remediation Plan" not in desc
        assert "trace-def" in desc


@pytest.mark.asyncio
async def test_create_ticket_disabled_returns_none() -> None:
    service = JiraService(
        url="https://jira.example.com",
        username="u",
        api_token="t",
        enabled=False,
    )
    result = await service.create_ticket(
        alert_id="a",
        severity="critical",
        category="resource",
        source_type="k8s",
        system="p",
        resource=None,
        root_cause="cpu",
        confidence=0.9,
        evidence=[],
        summary="fix",
        risk_level="low",
        steps=[],
        trace_id="t",
    )
    assert result is None


@pytest.mark.asyncio
async def test_create_ticket_not_configured_returns_none() -> None:
    service = JiraService(
        url="",
        username="",
        api_token="",
        enabled=True,
    )
    result = await service.create_ticket(
        alert_id="a",
        severity="critical",
        category="resource",
        source_type="k8s",
        system="p",
        resource=None,
        root_cause="cpu",
        confidence=0.9,
        evidence=[],
        summary="fix",
        risk_level="low",
        steps=[],
        trace_id="t",
    )
    assert result is None


@pytest.mark.asyncio
async def test_create_ticket_success_returns_key() -> None:
    service = JiraService(
        url="https://jira.example.com",
        username="admin",
        api_token="token",
        enabled=True,
    )
    mock_response = AsyncMock()
    mock_response.status = 201
    mock_response.json = AsyncMock(return_value={"key": "ALERTS-42", "id": "1001"})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.return_value = mock_response
    service._get_session = AsyncMock(return_value=mock_session)

    issue_key = await service.create_ticket(
        alert_id="alert-001",
        severity="critical",
        category="resource",
        source_type="kubernetes",
        system="prod",
        resource="order-pod",
        root_cause="CPU 过高",
        confidence=0.9,
        evidence=["cpu > 90%"],
        summary="扩容",
        risk_level="low",
        steps=["kubectl scale"],
        trace_id="trace-abc",
        remediation_plan_id="plan-001",
    )

    assert issue_key == "ALERTS-42"
    args = mock_session.post.call_args
    assert args[0][0] == "https://jira.example.com/rest/api/2/issue"

    payload = args[1]["json"]
    assert payload["fields"]["project"]["key"] == "ALERTS"
    assert payload["fields"]["summary"].startswith("[critical]")
    assert "langops" in payload["fields"]["labels"]


@pytest.mark.asyncio
async def test_create_ticket_api_error_returns_none() -> None:
    service = JiraService(
        url="https://jira.example.com",
        username="admin",
        api_token="token",
        enabled=True,
    )
    mock_response = AsyncMock()
    mock_response.status = 400
    mock_response.text = AsyncMock(return_value='{"errorMessages":["bad request"]}')
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.return_value = mock_response
    service._get_session = AsyncMock(return_value=mock_session)

    issue_key = await service.create_ticket(
        alert_id="alert-002",
        severity="high",
        category="performance",
        source_type="kubernetes",
        system="prod",
        resource="pod-1",
        root_cause="慢查询",
        confidence=0.8,
        evidence=[],
        summary="优化",
        risk_level="medium",
        steps=[],
        trace_id="trace-xyz",
    )
    assert issue_key is None


@pytest.mark.asyncio
async def test_create_ticket_network_error_returns_none() -> None:
    import aiohttp

    service = JiraService(
        url="https://jira.example.com",
        username="admin",
        api_token="token",
        enabled=True,
    )
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post.side_effect = aiohttp.ClientConnectionError("connection refused")
    service._get_session = AsyncMock(return_value=mock_session)

    issue_key = await service.create_ticket(
        alert_id="alert-003",
        severity="critical",
        category="resource",
        source_type="kubernetes",
        system="prod",
        resource="pod-2",
        root_cause="OOM",
        confidence=0.95,
        evidence=[],
        summary="升配",
        risk_level="low",
        steps=[],
        trace_id="trace-456",
    )
    assert issue_key is None


@pytest.mark.asyncio
async def test_close_releases_session() -> None:
    session = AsyncMock()
    session.closed = False
    service = JiraService(
        url="https://jira.example.com",
        username="u",
        api_token="t",
        enabled=True,
    )
    service._session = session
    await service.close()
    session.close.assert_awaited_once()
