"""JIRA integration service.

Creates and manages JIRA issues from alert analysis results.
All calls are best-effort — failures are logged, never propagated.
"""

import asyncio
import json
from typing import Any

import aiohttp

from langops.core import get_logger

logger = get_logger(__name__)


def _build_description(
    *,
    alert_id: str,
    severity: str,
    category: str,
    source_type: str,
    system: str,
    resource: str | None,
    root_cause: str,
    confidence: float,
    evidence: list[str],
    summary: str,
    risk_level: str,
    steps: list[str],
    trace_id: str,
    remediation_plan_id: str | None = None,
) -> str:
    """Build a JIRA description with structured fields from analysis results."""
    steps_text = "\n".join(f" - {s}" for s in steps[:10]) if steps else "(none)"
    evidence_text = "\n".join(f" - {e}" for e in evidence[:5]) if evidence else "(none)"

    parts: list[str] = [
        "h2. Alert Information\n",
        f"| *Field* | *Value* |",
        f"| Alert ID | {alert_id} |",
        f"| Severity | {severity} |",
        f"| Category | {category} |",
        f"| Source | {source_type} |",
        f"| System | {system} |",
    ]
    if resource:
        parts.append(f"| Resource | {resource} |")

    parts += [
        "",
        "h2. Root Cause Analysis",
        "",
        root_cause,
        "",
        f"*Confidence*: {confidence:.0%}",
        "",
        "h2. Key Evidence",
        "",
        evidence_text,
        "",
        "h2. Remediation",
        "",
        f"*Summary*: {summary}",
        f"*Risk Level*: {risk_level}",
        "",
        "*Steps*:",
        steps_text,
    ]
    if remediation_plan_id:
        parts += [
            "",
            "h2. Links",
            "",
            f"- LangOps Remediation Plan: /api/v1/remediation/{remediation_plan_id}",
        ]
    parts += [f"- Langfuse Trace ID: {trace_id}"]

    return "\n".join(parts)


class JiraService:
    """Create and manage JIRA issues from alert analysis results."""

    def __init__(
        self,
        url: str,
        username: str,
        api_token: str,
        project: str = "ALERTS",
        enabled: bool = True,
        timeout: int = 10,
    ) -> None:
        self._url = url.rstrip("/")
        self._username = username
        self._api_token = api_token
        self._project = project
        self.enabled = enabled
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    @property
    def _configured(self) -> bool:
        return bool(self._url and self._username and self._api_token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def create_ticket(
        self,
        *,
        alert_id: str,
        severity: str,
        category: str,
        source_type: str,
        system: str,
        resource: str | None,
        root_cause: str,
        confidence: float,
        evidence: list[str],
        summary: str,
        risk_level: str,
        steps: list[str],
        trace_id: str,
        remediation_plan_id: str | None = None,
    ) -> str | None:
        """Create a JIRA issue from an analysis result.

        Returns the issue key (e.g. ``ALERTS-42``) on success, or ``None`` when
        the service is disabled, unconfigured, or the API call fails.
        """
        if not self.enabled:
            return None
        if not self._configured:
            logger.warning("JIRA integration is not configured (missing url/username/api_token)")
            return None

        description = _build_description(
            alert_id=alert_id,
            severity=severity,
            category=category,
            source_type=source_type,
            system=system,
            resource=resource,
            root_cause=root_cause,
            confidence=confidence,
            evidence=evidence,
            summary=summary,
            risk_level=risk_level,
            steps=steps,
            trace_id=trace_id,
            remediation_plan_id=remediation_plan_id,
        )

        # JIRA Cloud REST API v2 payload
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": self._project},
                "summary": f"[{severity}] {summary}",
                "description": description,
                "issuetype": {"name": "Task"},
                "labels": ["langops", severity, category],
            }
        }

        try:
            session = await self._get_session()
            auth = aiohttp.BasicAuth(self._username, self._api_token)
            async with session.post(
                f"{self._url}/rest/api/2/issue",
                json=payload,
                auth=auth,
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        "JIRA create_ticket failed",
                        status=resp.status,
                        body=body[:500],
                    )
                    return None

                data = await resp.json()
                issue_key: str = data.get("key", "")
                logger.info(
                    "JIRA ticket created",
                    issue_key=issue_key,
                    alert_id=alert_id,
                )
                return issue_key

        except (aiohttp.ClientError, json.JSONDecodeError, asyncio.TimeoutError) as exc:
            logger.warning(
                "JIRA create_ticket network error",
                error=str(exc),
                alert_id=alert_id,
            )
            return None

    async def close(self) -> None:
        """Release the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
