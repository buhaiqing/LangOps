"""Tests for audit logger."""

import json
from pathlib import Path

from langops.core.audit import AuditLogger


def test_audit_logger_writes_json_line(tmp_path: Path) -> None:
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    audit.info("webhook.received", webhook_source="alertmanager", alert_count=2)
    audit.close()

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "webhook.received"
    assert record["webhook_source"] == "alertmanager"
    assert record["alert_count"] == 2
    assert "timestamp" in record


def test_audit_logger_truncates_long_values(tmp_path: Path) -> None:
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    audit.info("webhook.received", secret="x" * 500)
    audit.close()

    record = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert len(record["secret"]) <= 200
