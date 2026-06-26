"""In-process webhook time-window aggregation (coalesce buffer)."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from langops.core import get_logger

if TYPE_CHECKING:
    from langops.core.audit import AuditLogger
    from langops.models import AlertCreate

logger = get_logger(__name__)

FlushCallback = Callable[[str, list["AlertCreate"]], Awaitable[None]]

_DURATION_RE = re.compile(r"^(\d+)([smh])$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}


def parse_coalesce_duration(s: str) -> int:
    """Parse ``"30s"`` / ``"5m"`` / ``"1h"`` → seconds.  ``"0s"`` → ``0``.

    Raises ``ValueError`` for any other input.
    """
    if not isinstance(s, str):
        raise ValueError(f"coalesce duration must be a string, got {type(s).__name__}")
    match = _DURATION_RE.match(s)
    if not match:
        raise ValueError(f"invalid coalesce duration: {s!r}")
    value = int(match.group(1))
    unit = match.group(2)
    return value * _UNIT_SECONDS[unit]


def _alert_key(source: str, alert: "AlertCreate") -> str:
    """Logical id for an alert before it gets a real ``Alert.id`` downstream."""
    return f"{source}:{alert.title}"


class _Bucket:
    __slots__ = ("alerts", "timer", "opened_at")

    def __init__(self) -> None:
        self.alerts: list["AlertCreate"] = []
        self.timer: asyncio.Task[None] | None = None
        self.opened_at: float = 0.0


class CoalesceBuffer:
    """Buffer webhook alerts per source and flush after a quiet window.

    ponytail: in-process only — process restart drops pending windows.
    Upgrade path: Redis-backed buffer.
    """

    def __init__(
        self,
        cap: int,
        on_flush: FlushCallback,
        window_seconds: float = 5.0,
        audit: "AuditLogger | None" = None,
    ) -> None:
        if cap <= 0:
            raise ValueError("cap must be > 0")
        if window_seconds < 0:
            raise ValueError("window_seconds must be >= 0")
        self._cap = cap
        self._on_flush = on_flush
        self._window = window_seconds
        self._audit = audit
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def push(self, source: str, alert: "AlertCreate") -> None:
        async with self._lock:
            bucket = self._buckets.get(source)
            is_new_window = bucket is None or bucket.timer is None
            if bucket is None:
                bucket = _Bucket()
                self._buckets[source] = bucket
            bucket.alerts.append(alert)

            if is_new_window:
                bucket.opened_at = time.monotonic()
                if self._audit is not None:
                    self._audit.info(
                        "coalesce.opened",
                        webhook_source=source,
                        coalesce_seconds=self._window,
                        first_alert_id=_alert_key(source, alert),
                    )

            # Cancel any existing timer (last-received-wins)
            if bucket.timer is not None and not bucket.timer.done():
                bucket.timer.cancel()
            # Schedule the new timer
            bucket.timer = asyncio.create_task(self._timer_fire(source), name=f"coalesce:{source}")

            # Overflow check (after append) — flush immediately
            if len(bucket.alerts) >= self._cap:
                logger.warning(
                    "coalesce buffer overflow",
                    source=source,
                    cap=self._cap,
                    alert_count=len(bucket.alerts),
                )
                await self._flush_locked(source)

    async def _timer_fire(self, source: str) -> None:
        me = asyncio.current_task()
        try:
            await asyncio.sleep(self._window)
        except asyncio.CancelledError:
            return
        async with self._lock:
            bucket = self._buckets.get(source)
            if bucket is None or not bucket.alerts:
                return
            # Only flush if this task is still the active timer for the bucket.
            if bucket.timer is not me:
                return
            await self._flush_locked(source)

    async def _flush_locked(self, source: str) -> None:
        bucket = self._buckets.pop(source, None)
        if bucket is None or not bucket.alerts:
            return
        if bucket.timer is not None and not bucket.timer.done():
            bucket.timer.cancel()
        alerts = bucket.alerts
        duration_ms = int((time.monotonic() - bucket.opened_at) * 1000)
        if self._audit is not None:
            self._audit.info(
                "coalesce.flushed",
                webhook_source=source,
                coalesce_seconds=self._window,
                alert_count=len(alerts),
                duration_ms=duration_ms,
            )
        logger.info(
            "coalesce flush",
            source=source,
            alert_count=len(alerts),
            duration_ms=duration_ms,
        )
        try:
            await self._on_flush(source, alerts)
        except Exception:
            logger.exception("coalesce on_flush failed", source=source, exc_info=True)

    async def shutdown(self) -> None:
        async with self._lock:
            sources = list(self._buckets.keys())
            for source in sources:
                await self._flush_locked(source)
