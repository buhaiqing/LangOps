"""Alert noise reduction via time-window deduplication."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from langops.core import get_logger
from langops.models import Alert, DedupInfo

logger = get_logger(__name__)


def _normalize_title(title: str) -> str:
    """Normalize alert title for stable grouping."""
    text = title.strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\d+%?", "#", text)
    return text


@dataclass
class _DedupRecord:
    fingerprint: str
    first_seen: datetime
    last_seen: datetime
    count: int = 1


@dataclass
class AlertNoiseReducer:
    """Suppress duplicate alerts within a sliding time window.

    ponytail: in-process memory store; upgrade path = Redis for multi-worker.
    """

    window_seconds: int = 900
    enabled: bool = True
    _records: dict[str, _DedupRecord] = field(default_factory=dict)

    def fingerprint(self, alert: Alert) -> str:
        """Build a stable fingerprint for alert grouping."""
        resource = (
            alert.source.pod_name
            or alert.source.instance_id
            or alert.source.service
            or ""
        )
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

    def evaluate(self, alert: Alert, now: datetime | None = None) -> DedupInfo:
        """Decide whether to process or suppress an alert."""
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

        self._purge_expired(current)
        record = self._records.get(fp)

        if record is None:
            self._records[fp] = _DedupRecord(
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

        record.count += 1
        record.last_seen = current
        logger.info(
            "Duplicate alert suppressed",
            fingerprint=fp,
            alert_id=alert.id,
            occurrence_count=record.count,
        )
        return DedupInfo(
            action="suppress",
            fingerprint=fp,
            occurrence_count=record.count,
            window_seconds=self.window_seconds,
            message=(
                f"重复告警已降噪（{self.window_seconds // 60} 分钟内第 {record.count} 次），"
                "跳过 LLM 分析以降低告警疲劳"
            ),
        )

    def stats(self) -> dict[str, int]:
        """Return basic dedup store statistics."""
        return {"active_groups": len(self._records), "window_seconds": self.window_seconds}

    def _purge_expired(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.window_seconds)
        expired = [fp for fp, record in self._records.items() if record.last_seen < cutoff]
        for fp in expired:
            del self._records[fp]
