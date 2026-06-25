"""Alert noise reduction via time-window deduplication."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

from langops.core import get_logger
from langops.models import Alert, DedupInfo
from langops.storage.base import DedupRepository

logger = get_logger(__name__)


def _normalize_title(title: str) -> str:
    text = title.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\d+%?", "#", text)
    return text


class AlertNoiseReducer:
    """Suppress duplicate alerts within a sliding time window."""

    def __init__(
        self, repo: DedupRepository, window_seconds: int = 900, enabled: bool = True
    ) -> None:
        self._repo = repo
        self.window_seconds = window_seconds
        self.enabled = enabled

    def fingerprint(self, alert: Alert) -> str:
        resource = alert.source.pod_name or alert.source.instance_id or alert.source.service or ""
        parts = [
            alert.category.value,
            alert.severity.value,
            alert.source.type,
            alert.source.system,
            alert.source.namespace or "",
            resource,
            _normalize_title(alert.title),
        ]
        digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
        return digest[:16]

    async def evaluate(self, alert: Alert, now: datetime | None = None) -> DedupInfo:
        current = now or datetime.now(UTC)
        fp = self.fingerprint(alert)

        if not self.enabled:
            return DedupInfo(
                action="process",
                fingerprint=fp,
                occurrence_count=1,
                window_seconds=self.window_seconds,
                message="告警降噪未启用",
            )

        cutoff = current - timedelta(seconds=self.window_seconds)
        await self._repo.purge_expired(cutoff)

        record = await self._repo.get(fp)

        if record is None:
            await self._repo.upsert(
                fingerprint=fp,
                first_seen=current,
                last_seen=current,
                count=1,
            )
            logger.info("New alert group", fingerprint=fp, alert_id=alert.id)
            return DedupInfo(
                action="process",
                fingerprint=fp,
                occurrence_count=1,
                window_seconds=self.window_seconds,
                message="首次告警，执行完整分析",
            )

        new_count = record["count"] + 1
        await self._repo.upsert(
            fingerprint=fp,
            first_seen=datetime.fromisoformat(record["first_seen"]),
            last_seen=current,
            count=new_count,
        )
        logger.info(
            "Duplicate alert suppressed",
            fingerprint=fp,
            alert_id=alert.id,
            occurrence_count=new_count,
        )
        return DedupInfo(
            action="suppress",
            fingerprint=fp,
            occurrence_count=new_count,
            window_seconds=self.window_seconds,
            message=(
                f"重复告警已降噪（{self.window_seconds // 60} 分钟内第 {new_count} 次），"
                "跳过 LLM 分析以降低告警疲劳"
            ),
        )

    async def stats(self) -> dict[str, int]:
        count = await self._repo.count()
        return {"active_groups": count, "window_seconds": self.window_seconds}
