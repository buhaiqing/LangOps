"""Notification services for Feishu, DingTalk, and WeChat Work."""

from typing import Any

import aiohttp

from langops.core import get_logger
from langops.models import Alert, AnalysisResult

logger = get_logger(__name__)


class NotificationService:
    """Send analysis notifications to Feishu, DingTalk, and WeChat Work webhooks."""

    def __init__(
        self,
        feishu_webhook: str = "",
        dingtalk_webhook: str = "",
        wechat_work_webhook: str = "",
        timeout: int = 10,
    ) -> None:
        self.feishu_webhook = feishu_webhook.strip()
        self.dingtalk_webhook = dingtalk_webhook.strip()
        self.wechat_work_webhook = wechat_work_webhook.strip()
        self.timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.feishu_webhook or self.dingtalk_webhook or self.wechat_work_webhook)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            )
        return self._session

    async def notify_analysis(self, alert: Alert, result: AnalysisResult) -> dict[str, bool]:
        """Send analysis result to configured channels."""
        message = self._format_analysis_message(alert, result)
        outcomes: dict[str, bool] = {}

        if self.feishu_webhook:
            outcomes["feishu"] = await self.send_feishu(message)
        if self.dingtalk_webhook:
            outcomes["dingtalk"] = await self.send_dingtalk(message)
        if self.wechat_work_webhook:
            outcomes["wechat_work"] = await self.send_wechat_work(message)

        return outcomes

    async def send_feishu(self, text: str) -> bool:
        """Send text message to Feishu webhook."""
        if not self.feishu_webhook:
            return False

        payload = {"msg_type": "text", "content": {"text": text}}
        return await self._post_webhook(self.feishu_webhook, payload, channel="feishu")

    async def send_dingtalk(self, text: str) -> bool:
        """Send markdown message to DingTalk webhook."""
        if not self.dingtalk_webhook:
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": "LangOps 告警分析",
                "text": text,
            },
        }
        return await self._post_webhook(self.dingtalk_webhook, payload, channel="dingtalk")

    async def send_wechat_work(self, text: str) -> bool:
        """Send markdown message to WeChat Work (企业微信) webhook."""
        if not self.wechat_work_webhook:
            return False

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": text,
            },
        }
        return await self._post_webhook(self.wechat_work_webhook, payload, channel="wechat_work")

    async def _post_webhook(self, url: str, payload: dict[str, Any], channel: str) -> bool:
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        "Notification webhook failed",
                        channel=channel,
                        status=resp.status,
                        body=body[:200],
                    )
                    return False

                data = await resp.json(content_type=None)
                if isinstance(data, dict) and data.get("errcode", 0) not in (0, None):
                    logger.warning("Notification API error", channel=channel, response=data)
                    return False

                logger.info("Notification sent", channel=channel)
                return True
        except Exception as exc:
            logger.warning("Notification send failed", channel=channel, error=str(exc))
            return False

    def _format_analysis_message(self, alert: Alert, result: AnalysisResult) -> str:
        """Format analysis result as markdown/text."""
        steps = "\n".join(f"- {step}" for step in result.suggestion.steps[:5])
        return (
            f"**LangOps 告警分析**\n\n"
            f"**告警**: {alert.title}\n"
            f"**严重程度**: {alert.severity.value}\n"
            f"**根因**: {result.root_cause.description}\n"
            f"**置信度**: {result.root_cause.confidence:.0%}\n"
            f"**建议**: {result.suggestion.summary}\n"
            f"**步骤**:\n{steps or '- 暂无'}\n"
            f"**Trace ID**: {result.trace_id}"
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
