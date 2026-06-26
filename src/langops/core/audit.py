"""Dedicated audit logger with rotating file retention."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

_MAX_FIELD_LEN = 200


class AuditLogger:
    """Write structured audit events to a dedicated rotating log file."""

    def __init__(self, path: str, retention_days: int) -> None:
        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger(f"langops.audit.{path}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = TimedRotatingFileHandler(
                filename=str(log_path),
                when="midnight",
                interval=1,
                backupCount=retention_days,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def _truncate_value(self, value: Any) -> Any:
        if isinstance(value, str) and len(value) > _MAX_FIELD_LEN:
            return value[: _MAX_FIELD_LEN - 1] + "…"
        return value

    def _emit(self, level: int, event: str, **fields: Any) -> None:
        safe_fields = {k: self._truncate_value(v) for k, v in fields.items()}
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **safe_fields,
        }
        try:
            self._logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            logging.getLogger(__name__).error("Audit log write failed", exc_info=True)

    def info(self, event: str, **fields: Any) -> None:
        self._emit(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit(logging.WARNING, event, **fields)

    def close(self) -> None:
        for handler in self._logger.handlers[:]:
            handler.close()
            self._logger.removeHandler(handler)
