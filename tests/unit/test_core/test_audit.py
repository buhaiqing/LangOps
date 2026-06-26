"""Tests for audit logger."""

import json
import logging.handlers
from pathlib import Path

import pytest

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


# ─── robustness & contract ─────────────────────────────────────────────


def test_audit_logger_never_raises_on_write_failure(tmp_path: Path) -> None:
    """A write failure (parent is a file) must NOT propagate — audit is best-effort."""
    # Construct a path whose parent is a file, not a directory. mkdir(parents=True)
    # inside the constructor will fail, but the constructor doesn't catch — so
    # we construct the logger at a valid path first, then make the path unwritable
    # by replacing the log file with a directory (causes TimedRotatingFileHandler
    # emit to fail).
    import os

    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    # First, write succeeds and we verify the logger is wired
    audit.info("webhook.received", ok=True)

    # Now make the file unreadable/unwritable for appends — POSIX chmod 0o000.
    # On macOS the file is still owned by us, so chmod 0o000 denies even write.
    if hasattr(os, "chmod"):
        try:
            os.chmod(log_file, 0o000)
        except (PermissionError, OSError):
            pytest.skip("chmod 0o000 not effective on this filesystem")
        try:
            # Must NOT raise even if the underlying handler can't open
            audit.info("webhook.received", should_not_raise=True)
        finally:
            os.chmod(log_file, 0o644)

    # Even if all writes failed, no exception escaped
    audit.close()


def test_audit_logger_does_not_leak_secrets_pattern(tmp_path: Path) -> None:
    """AuditLogger does NOT auto-redact; values are recorded as-is.

    This documents the current contract: callers are responsible for not
    passing raw secrets. If we want auto-redaction, that's a separate feature.
    """
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=7)
    audit.info(
        "user.login",
        api_key="sk-secret-12345",
        password="hunter2",
        token="tkn-abc",
        secret="hidden",
    )
    audit.close()

    contents = log_file.read_text(encoding="utf-8")
    # Contract: values are written verbatim (no auto-redaction)
    assert "sk-secret-12345" in contents
    assert "hunter2" in contents
    assert "tkn-abc" in contents
    assert "hidden" in contents


def test_audit_logger_retention_backupcount_matches_setting(tmp_path: Path) -> None:
    """TimedRotatingFileHandler.backupCount must equal retention_days."""
    log_file = tmp_path / "audit.log"
    audit = AuditLogger(path=str(log_file), retention_days=14)
    handler = audit._logger.handlers[0]
    assert isinstance(handler, logging.handlers.TimedRotatingFileHandler)
    assert handler.backupCount == 14
    audit.close()
