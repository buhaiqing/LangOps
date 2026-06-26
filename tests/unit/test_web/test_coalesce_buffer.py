"""Tests for CoalesceBuffer — webhook time-window aggregation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from langops.core.audit import AuditLogger
from langops.models import AlertCategory, AlertCreate, AlertSeverity, AlertSource
from langops.web._coalesce import CoalesceBuffer, parse_coalesce_duration


def _make_alert(idx: int = 0) -> AlertCreate:
    return AlertCreate(
        title=f"alert-{idx}",
        description=f"description-{idx}",
        severity=AlertSeverity.HIGH,
        category=AlertCategory.RESOURCE,
        source=AlertSource(type="prometheus", system="prod"),
    )


# ─── parse_coalesce_duration ────────────────────────────────────────────


def test_parse_coalesce_duration_valid_formats() -> None:
    assert parse_coalesce_duration("30s") == 30
    assert parse_coalesce_duration("5m") == 300
    assert parse_coalesce_duration("1h") == 3600
    assert parse_coalesce_duration("0s") == 0
    assert parse_coalesce_duration("0m") == 0


def test_parse_coalesce_duration_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_coalesce_duration("5x")
    with pytest.raises(ValueError):
        parse_coalesce_duration("abc")
    with pytest.raises(ValueError):
        parse_coalesce_duration("")
    with pytest.raises(ValueError):
        parse_coalesce_duration("5")


# ─── CoalesceBuffer ─────────────────────────────────────────────────────


def test_buffer_pushes_to_bucket() -> None:
    """First push: no flush yet."""
    flushed: list[tuple[str, list[AlertCreate]]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append((source, alerts))

    async def runner() -> None:
        buf = CoalesceBuffer(cap=10, on_flush=on_flush, window_seconds=10)
        await buf.push("alertmanager", _make_alert(0))
        # Give the event loop a tick — the timer is pending and should NOT fire
        await asyncio.sleep(0.05)
        assert flushed == []

    asyncio.run(runner())


def test_buffer_flushes_after_window() -> None:
    """Push then sleep past the window → on_flush called with the alert."""
    flushed: list[tuple[str, list[AlertCreate]]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append((source, list(alerts)))

    async def runner() -> None:
        buf = CoalesceBuffer(cap=10, on_flush=on_flush, window_seconds=0.1)
        await buf.push("alertmanager", _make_alert(0))
        await asyncio.sleep(0.2)
        assert len(flushed) == 1
        assert flushed[0][0] == "alertmanager"
        assert len(flushed[0][1]) == 1
        assert flushed[0][1][0].title == "alert-0"

    asyncio.run(runner())


def test_buffer_overflow_flushes_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cap+1 alerts → flush triggered with `cap` alerts (not all); WARNING logged."""
    from langops.web import _coalesce

    flushed: list[tuple[str, list[AlertCreate]]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append((source, list(alerts)))

    warnings: list[tuple[str, dict]] = []
    info: list[tuple[str, dict]] = []

    class _StubLogger:
        def warning(self, event: str, **fields: object) -> None:
            warnings.append((event, fields))

        def info(self, event: str, **fields: object) -> None:
            info.append((event, fields))

        def exception(self, event: str, **fields: object) -> None:
            warnings.append((event, fields))

        def bind(self, **fields: object) -> _StubLogger:  # pragma: no cover
            return self

    monkeypatch.setattr(_coalesce, "logger", _StubLogger())

    async def runner() -> None:
        buf = CoalesceBuffer(cap=2, on_flush=on_flush, window_seconds=10)
        await buf.push("alertmanager", _make_alert(0))
        await buf.push("alertmanager", _make_alert(1))
        await buf.push("alertmanager", _make_alert(2))  # overflow
        assert len(flushed) == 1
        assert flushed[0][1][0].title == "alert-0"
        assert flushed[0][1][1].title == "alert-1"

    asyncio.run(runner())

    assert any(event == "coalesce buffer overflow" for event, _ in warnings)


def test_buffer_resets_window_on_new_push() -> None:
    """Last-received-wins: push resets the timer."""
    flushed: list[list[AlertCreate]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append(list(alerts))

    async def runner() -> None:
        # window = 0.2s. Push at t=0, push at t=0.1s, expect flush ~ t=0.3s.
        buf = CoalesceBuffer(cap=10, on_flush=on_flush, window_seconds=0.2)
        await buf.push("alertmanager", _make_alert(0))
        await asyncio.sleep(0.1)
        await buf.push("alertmanager", _make_alert(1))
        # Wait long enough for the first timer to have fired (it would have
        # at t=0.2 — already past) but the reset timer fires at t=0.3.
        await asyncio.sleep(0.25)
        assert len(flushed) == 1, f"expected 1 flush, got {len(flushed)}"
        assert [a.title for a in flushed[0]] == ["alert-0", "alert-1"]

    asyncio.run(runner())


def test_buffer_audit_events(tmp_path: Path) -> None:
    """coalesce.opened on window open, coalesce.flushed on flush."""
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)

    flushed: list[list[AlertCreate]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append(list(alerts))

    async def runner() -> None:
        buf = CoalesceBuffer(cap=10, on_flush=on_flush, window_seconds=0.1, audit=audit)
        await buf.push("alertmanager", _make_alert(7))
        await asyncio.sleep(0.2)
        assert len(flushed) == 1

    asyncio.run(runner())
    audit.close()

    events = [
        json.loads(line) for line in log_file.read_text(encoding="utf-8").strip().splitlines()
    ]
    event_names = [e["event"] for e in events]
    assert "coalesce.opened" in event_names
    assert "coalesce.flushed" in event_names
    opened = next(e for e in events if e["event"] == "coalesce.opened")
    assert opened["webhook_source"] == "alertmanager"
    assert opened["first_alert_id"] == "alertmanager:alert-7"
    flushed_event = next(e for e in events if e["event"] == "coalesce.flushed")
    assert flushed_event["webhook_source"] == "alertmanager"
    assert flushed_event["alert_count"] == 1


def test_shutdown_flushes_all_pending() -> None:
    """shutdown() drains every open window immediately."""
    flushed: list[tuple[str, list[AlertCreate]]] = []

    async def on_flush(source: str, alerts: list[AlertCreate]) -> None:
        flushed.append((source, list(alerts)))

    async def runner() -> None:
        buf = CoalesceBuffer(cap=10, on_flush=on_flush, window_seconds=10)
        await buf.push("alertmanager", _make_alert(0))
        await buf.push("prometheus", _make_alert(1))
        await buf.shutdown()
        assert len(flushed) == 2
        sources = {s for s, _ in flushed}
        assert sources == {"alertmanager", "prometheus"}

    asyncio.run(runner())
