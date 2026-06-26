# Prometheus AlertManager Webhook Adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `POST /api/v1/webhooks/alertmanager` that accepts AlertManager v4 payloads, maps them to `AlertCreate`, and runs the existing alert pipeline with audit logging, optional coalesce, and API docs.

**Architecture:** Concrete `AlertmanagerAdapter` maps AM JSON → `list[AlertCreate]`. Shared `process_one_alert` in `web/_alert_flow.py` serves both `/api/v1/alerts` and webhooks. `AuditLogger` writes to a dedicated rotating file (7-day retention). Coalesce is in-process, disabled when `workers > 1`.

**Tech Stack:** FastAPI, Pydantic v2, asyncio, prometheus_client, stdlib `logging.handlers`. No new dependencies.

**Design spec:** `docs/superpowers/specs/2026-06-26-prometheus-webhook-adapter-design.md` (Approved 2026-06-26)

**Worktree:** Create before starting (AGENTS.md §5.1):

```bash
git checkout main && git pull origin main
git worktree add .worktrees/feat-webhook-alertmanager -b feat/webhook-alertmanager
cd .worktrees/feat-webhook-alertmanager
uv sync --dev
export LLM_API_KEY=sk-test LANGFUSE_PUBLIC_KEY=pk-test LANGFUSE_SECRET_KEY=sk-lf-test
pytest tests/ -q   # baseline must be green
```

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/langops/core/config.py` | MODIFY | Add `WebhookSettings`, wire into `Settings` |
| `src/langops/core/audit.py` | CREATE | `AuditLogger` with `TimedRotatingFileHandler` |
| `src/langops/models/webhook.py` | CREATE | AM payload models + `WebhookBatchResponse` |
| `src/langops/models/__init__.py` | MODIFY | Export new models |
| `src/langops/adapters/__init__.py` | CREATE | Package marker |
| `src/langops/adapters/alertmanager.py` | CREATE | `AlertmanagerAdapter` |
| `src/langops/web/_alert_flow.py` | CREATE | `process_one_alert` |
| `src/langops/web/_coalesce.py` | CREATE | `CoalesceBuffer`, `parse_coalesce_duration` |
| `src/langops/web/api/alerts.py` | MODIFY | Delegate to `process_one_alert` |
| `src/langops/web/api/webhooks.py` | CREATE | Webhook route |
| `src/langops/web/dependencies.py` | MODIFY | DI for adapter, audit, coalesce |
| `src/langops/web/main.py` | MODIFY | Register webhooks router |
| `src/langops/web/metrics.py` | MODIFY | Webhook counters/histograms |
| `.env.example` | MODIFY | Webhook env vars |
| `docs/api-reference.md` | MODIFY | New §5 + renumber |
| `docs/architecture/system-design.md` | MODIFY | External Alert Sources subsection |
| `tests/unit/test_core/test_audit.py` | CREATE | AuditLogger tests |
| `tests/unit/test_models/test_webhook_payload.py` | CREATE | Payload model tests |
| `tests/unit/test_adapters/test_alertmanager_adapter.py` | CREATE | Adapter mapping tests |
| `tests/unit/test_web/test_alert_flow.py` | CREATE | process_one_alert tests |
| `tests/unit/test_web/test_coalesce_buffer.py` | CREATE | Coalesce tests |
| `tests/integration/test_webhook_alertmanager.py` | CREATE | End-to-end webhook tests |

---

### Task 1: WebhookSettings

**Files:**
- Modify: `src/langops/core/config.py`
- Test: `tests/unit/test_core/test_config.py`

- [ ] **Step 1: Write failing test**

Add to `tests/unit/test_core/test_config.py`:

```python
def test_webhook_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    from langops.core.config import Settings

    s = Settings()
    assert s.webhook.max_payload_bytes == 1_048_576
    assert s.webhook.max_alerts_per_batch == 100
    assert s.webhook.audit_log_path == "logs/langops-audit.log"
    assert s.webhook.audit_log_retention_days == 7
    assert s.webhook.coalesce_max_buffered_alerts == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_core/test_config.py::test_webhook_settings_defaults -v`
Expected: FAIL — `Settings` has no `webhook` attribute

- [ ] **Step 3: Implement WebhookSettings**

In `src/langops/core/config.py`, add before `class Settings`:

```python
class WebhookSettings(BaseSettings):
    """Webhook receiver configuration."""

    model_config = _env_config("WEBHOOK_")

    max_payload_bytes: int = Field(default=1_048_576, ge=1024, description="Max webhook body size")
    max_alerts_per_batch: int = Field(default=100, ge=1, le=1000, description="Max alerts per callback")
    audit_log_path: str = Field(default="logs/langops-audit.log", description="Audit log file path")
    audit_log_retention_days: int = Field(default=7, ge=1, le=90, description="Audit log retention days")
    coalesce_max_buffered_alerts: int = Field(default=500, ge=10, le=10_000, description="Coalesce buffer cap")
```

Add to `Settings`:
```python
webhook: WebhookSettings = Field(default_factory=WebhookSettings)
```

Add `WebhookSettings` to `nested_factories` list and `_factory_to_field_name` mapping (`"webhook"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core/test_config.py::test_webhook_settings_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/langops/core/config.py tests/unit/test_core/test_config.py
git commit -m "feat(config): add WebhookSettings for alertmanager webhook receiver"
```

---

### Task 2: AuditLogger

**Files:**
- Create: `src/langops/core/audit.py`
- Test: `tests/unit/test_core/test_audit.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_core/test_audit.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_core/test_audit.py -v`
Expected: FAIL — `AuditLogger` not defined

- [ ] **Step 3: Implement AuditLogger**

Create `src/langops/core/audit.py`:

```python
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

    def _emit(self, level: int, event: str, **fields: Any) -> None:
        safe_fields = {
            k: (v if not isinstance(v, str) or len(v) <= _MAX_FIELD_LEN else v[:_MAX_FIELD_LEN] + "…")
            for k, v in fields.items()
        }
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_core/test_audit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/langops/core/audit.py tests/unit/test_core/test_audit.py
git commit -m "feat(audit): add AuditLogger with TimedRotatingFileHandler retention"
```

---

### Task 3: AlertManager Payload Models

**Files:**
- Create: `src/langops/models/webhook.py`
- Modify: `src/langops/models/__init__.py`
- Test: `tests/unit/test_models/test_webhook_payload.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_models/test_webhook_payload.py`:

```python
"""AlertManager webhook payload model tests."""

import pytest
from pydantic import ValidationError

from langops.models.webhook import AlertmanagerAlert, AlertmanagerWebhookPayload

SAMPLE_PAYLOAD = {
    "version": "4",
    "groupKey": '{}:{alertname="HighCPU"}',
    "status": "firing",
    "receiver": "langops",
    "groupLabels": {"alertname": "HighCPU"},
    "commonLabels": {"alertname": "HighCPU", "severity": "critical"},
    "commonAnnotations": {"summary": "CPU > 90%"},
    "externalURL": "http://alertmanager:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": "order-service-abc",
            },
            "annotations": {"summary": "High CPU", "description": "CPU > 90% for 5m"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "http://prometheus:9090/graph",
            "fingerprint": "abc123",
        }
    ],
}


def test_parses_am_v4_payload() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(SAMPLE_PAYLOAD)
    assert payload.version == "4"
    assert len(payload.alerts) == 1
    assert payload.alerts[0].labels["alertname"] == "HighCPU"


def test_rejects_missing_alerts() -> None:
    bad = {**SAMPLE_PAYLOAD, "alerts": []}
    with pytest.raises(ValidationError):
        AlertmanagerWebhookPayload.model_validate(bad)


def test_ignores_unknown_fields() -> None:
    extended = {**SAMPLE_PAYLOAD, "futureField": "ok"}
    payload = AlertmanagerWebhookPayload.model_validate(extended)
    assert payload.receiver == "langops"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models/test_webhook_payload.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement models**

Create `src/langops/models/webhook.py`:

```python
"""Webhook payload and response models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from langops.models.analysis import AnalysisResult


class AlertmanagerAlert(BaseModel):
    """Single alert inside an AlertManager webhook payload."""

    model_config = ConfigDict(extra="ignore")

    status: str
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str = ""
    endsAt: str = ""
    generatorURL: str = ""
    fingerprint: str = ""


class AlertmanagerWebhookPayload(BaseModel):
    """AlertManager v4 webhook payload."""

    model_config = ConfigDict(extra="ignore")

    version: str = "4"
    groupKey: str = ""
    status: str = ""
    receiver: str = ""
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    alerts: list[AlertmanagerAlert] = Field(..., min_length=1)


class WebhookAlertResult(BaseModel):
    """Per-alert result inside a webhook batch response."""

    alert_id: str | None = None
    success: bool
    data: AnalysisResult | None = None
    error: str | None = None
    dedup: dict[str, Any] | None = None
    remediation_plan_id: str | None = None


class WebhookBatchResponse(BaseModel):
    """Response for POST /api/v1/webhooks/{source}."""

    success: bool
    received: int
    results: list[WebhookAlertResult] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
```

Update `src/langops/models/__init__.py` to export:
`AlertmanagerWebhookPayload`, `AlertmanagerAlert`, `WebhookBatchResponse`, `WebhookAlertResult`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models/test_webhook_payload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/langops/models/webhook.py src/langops/models/__init__.py tests/unit/test_models/test_webhook_payload.py
git commit -m "feat(models): add AlertManager webhook payload and batch response models"
```

---

### Task 4: AlertmanagerAdapter

**Files:**
- Create: `src/langops/adapters/__init__.py`
- Create: `src/langops/adapters/alertmanager.py`
- Test: `tests/unit/test_adapters/test_alertmanager_adapter.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_adapters/test_alertmanager_adapter.py`:

```python
"""AlertmanagerAdapter mapping tests."""

from langops.adapters.alertmanager import AlertmanagerAdapter
from langops.models import AlertCategory, AlertSeverity
from langops.models.webhook import AlertmanagerWebhookPayload

SAMPLE = {
    "version": "4",
    "status": "firing",
    "receiver": "langops",
    "externalURL": "http://alertmanager.prod:9093",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPU",
                "severity": "critical",
                "namespace": "production",
                "pod": "order-abc",
            },
            "annotations": {"summary": "High CPU"},
            "startsAt": "2024-01-15T10:30:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
        }
    ],
}


def test_maps_to_alert_create() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(SAMPLE)
    results = AlertmanagerAdapter().to_alert_creates(payload)
    assert len(results) == 1
    ac = results[0]
    assert ac.title == "High CPU"
    assert ac.description == "High CPU"  # fallback: summary when no description
    assert ac.severity == AlertSeverity.CRITICAL
    assert ac.category == AlertCategory.RESOURCE
    assert ac.source.type == "prometheus"
    assert ac.source.system == "alertmanager.prod"
    assert ac.source.namespace == "production"
    assert ac.source.pod_name == "order-abc"
    assert ac.context["alertmanager_status"] == "firing"


def test_description_fallback_to_alertname() -> None:
    payload = AlertmanagerWebhookPayload.model_validate(
        {
            **SAMPLE,
            "alerts": [
                {
                    "status": "firing",
                    "labels": {"alertname": "DiskFull", "severity": "warning"},
                    "annotations": {},
                    "startsAt": "2024-01-15T10:30:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                }
            ],
        }
    )
    ac = AlertmanagerAdapter().to_alert_creates(payload)[0]
    assert ac.description == "DiskFull: firing"
    assert ac.severity == AlertSeverity.MEDIUM  # warning → medium via enum
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_adapters/test_alertmanager_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement adapter**

Create `src/langops/adapters/__init__.py` (empty or `"""Alert source adapters."""`).

Create `src/langops/adapters/alertmanager.py` with:
- `_infer_category(text: str) -> AlertCategory` — keyword match per spec §4.3
- `_normalize_severity(raw: str | None) -> AlertSeverity` — map `page→critical`, pass through others
- `_description(alert) -> str` — fallback chain: description → summary → message → `f"{alertname}: {status}"`
- `_system(payload, alert) -> str` — parse `externalURL` host, fallback `labels.job` or `"unknown"`
- `AlertmanagerAdapter.to_alert_creates(payload) -> list[AlertCreate]`

Key mapping per spec §4.3 and §4.0 (`source.type="prometheus"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_adapters/test_alertmanager_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/langops/adapters/ tests/unit/test_adapters/
git commit -m "feat(adapters): add AlertmanagerAdapter mapping to AlertCreate"
```

---

### Task 5: process_one_alert Refactor

**Files:**
- Create: `src/langops/web/_alert_flow.py`
- Modify: `src/langops/web/api/alerts.py`
- Test: `tests/unit/test_web/test_alert_flow.py`
- Regression: `tests/unit/test_web/test_api.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_web/test_alert_flow.py` — test that `process_one_alert` returns `AnalysisResponse(success=False)` on processor exception (does not raise).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_web/test_alert_flow.py -v`
Expected: FAIL

- [ ] **Step 3: Extract helper and refactor alerts route**

Move logic from `alerts.py::create_alert` into `process_one_alert(...)` in `_alert_flow.py`. The helper:
- Builds `Alert` from `AlertCreate`
- Runs dedup → processor → persist → remediation → jira
- Records metrics (same as today)
- On exception: returns `AnalysisResponse(success=False, error=str(exc))`
- Optional `audit` + `webhook_source` kwargs emit `alert.processed` audit events

Refactor `create_alert` to:
```python
alerts_received_total.labels(...).inc()
start = time.monotonic()
response = await process_one_alert(alert_create, processor, dedup, remediation_registry, jira)
duration = time.monotonic() - start
alert_processing_duration_seconds.observe(duration)
# keep existing success/failure metric labels based on response.success
return response
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_web/test_alert_flow.py tests/unit/test_web/test_api.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/langops/web/_alert_flow.py src/langops/web/api/alerts.py tests/unit/test_web/test_alert_flow.py
git commit -m "refactor(web): extract process_one_alert shared alert pipeline helper"
```

---

### Task 6: CoalesceBuffer

**Files:**
- Create: `src/langops/web/_coalesce.py`
- Test: `tests/unit/test_web/test_coalesce_buffer.py`

- [ ] **Step 1: Write failing tests**

Test `parse_coalesce_duration("5m") == 300`, `"30s" == 30`, invalid raises `ValueError`.

Test `CoalesceBuffer.push` resets timer, overflow triggers immediate flush callback.

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement**

`parse_coalesce_duration(s: str) -> int` — regex `^(\d+)(s|m|h)$`.

`CoalesceBuffer` — per `webhook_source` bucket, `asyncio.Task` timer, `on_flush(alerts: list[AlertCreate])` callback.

- [ ] **Step 4: Run tests — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/langops/web/_coalesce.py tests/unit/test_web/test_coalesce_buffer.py
git commit -m "feat(web): add CoalesceBuffer for optional webhook time-window aggregation"
```

---

### Task 7: Webhook Metrics

**Files:**
- Modify: `src/langops/web/metrics.py`

- [ ] **Step 1: Add metrics per spec §4.0a**

```python
webhook_received_total = Counter(
    "langops_webhook_received_total",
    "Total webhook callbacks received",
    ["webhook_source", "status"],
)
webhook_duration_seconds = Histogram(
    "langops_webhook_duration_seconds",
    "Webhook handler duration",
    ["webhook_source"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120),
)
webhook_alerts_received_total = Counter(
    "langops_webhook_alerts_received_total",
    "Total alerts received via webhooks",
    ["webhook_source"],
)
```

- [ ] **Step 2: Commit**

```bash
git add src/langops/web/metrics.py
git commit -m "feat(metrics): add webhook receiver counters and histogram"
```

---

### Task 8: Webhook Route + Dependencies

**Files:**
- Create: `src/langops/web/api/webhooks.py`
- Modify: `src/langops/web/dependencies.py`
- Modify: `src/langops/web/main.py`
- Test: `tests/integration/test_webhook_alertmanager.py`

- [ ] **Step 1: Write failing integration test**

Create `tests/integration/test_webhook_alertmanager.py` with fixtures mirroring `test_api.py` (mock processor, dedup repo, etc.).

Test cases:
1. POST valid AM payload → 200, `received=1`, `results[0].success=True`
2. POST 3 alerts → `received=3`
3. Oversized body → 422
4. `?coalesce=1s` → 200, `audit.coalesced=True`, `results=[]`

Sample curl body: use `SAMPLE_PAYLOAD` from Task 3 tests.

- [ ] **Step 2: Run test — expect FAIL**

Run: `uv run pytest tests/integration/test_webhook_alertmanager.py -v`

- [ ] **Step 3: Implement route**

`src/langops/web/api/webhooks.py`:

```python
WEBHOOK_SOURCE = "alertmanager"

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/alertmanager", response_model=WebhookBatchResponse)
async def alertmanager_webhook(
    request: Request,
    coalesce: str | None = None,
    ...
) -> WebhookBatchResponse:
    # 1. Check Content-Length vs max_payload_bytes
    # 2. body = await request.body(); len check
    # 3. json.loads → AlertmanagerWebhookPayload.model_validate
    # 4. len(alerts) vs max_alerts_per_batch
    # 5. audit.info("webhook.received", ...)
    # 6. adapter.to_alert_creates(payload)
    # 7. If coalesce and workers==1: buffer.push; return coalesced response
    # 8. Else: gather process_one_alert for each; build WebhookBatchResponse
```

Add to `dependencies.py`:
- `get_audit_logger()` — singleton `AuditLogger` from settings
- `get_alertmanager_adapter()` — returns `AlertmanagerAdapter()`
- `get_coalesce_buffer()` — app-state singleton

Register in `main.py`:
```python
from langops.web.api import alerts, predict, query, remediation, webhooks
app.include_router(webhooks.router, prefix="/api/v1")
```

Initialize `CoalesceBuffer` in lifespan with flush callback calling `process_one_alert`.

- [ ] **Step 4: Run integration test — expect PASS**

- [ ] **Step 5: Run full unit suite**

Run: `uv run pytest tests/unit -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/langops/web/api/webhooks.py src/langops/web/dependencies.py src/langops/web/main.py tests/integration/test_webhook_alertmanager.py
git commit -m "feat(webhooks): add POST /api/v1/webhooks/alertmanager endpoint"
```

---

### Task 9: Environment Template

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add section**

```bash
# Webhooks (Prometheus AlertManager)
WEBHOOK_MAX_PAYLOAD_BYTES=1048576
WEBHOOK_MAX_ALERTS_PER_BATCH=100
WEBHOOK_AUDIT_LOG_PATH=logs/langops-audit.log
WEBHOOK_AUDIT_LOG_RETENTION_DAYS=7
WEBHOOK_COALESCE_MAX_BUFFERED_ALERTS=500
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs(config): add webhook settings to .env.example"
```

---

### Task 10: API Documentation (REQUIRED)

**Files:**
- Modify: `docs/api-reference.md`
- Modify: `docs/architecture/system-design.md`

- [ ] **Step 1: Update api-reference.md**

1. Add TOC entry: `§5. POST /api/v1/webhooks/alertmanager — Prometheus Webhook`
2. Renumber existing §5–§12 → §6–§13
3. New §5 content:
   - Endpoint description
   - AlertManager configures: `receivers: [{ name: langops, webhook_configs: [{ url: 'http://langops:8000/api/v1/webhooks/alertmanager' }] }]`
   - Request body field table (version, groupKey, status, alerts[], etc.)
   - `?coalesce=5m` query param
   - Response `WebhookBatchResponse` example (sync + coalesced)
   - Error responses (422 payload too large, batch too large)
   - Env var configuration table
   - Troubleshooting bullets:
     - Coalesce ignored when `workers > 1`
     - AM retries on non-2xx — ensure LangOps is reachable
     - Check `logs/langops-audit.log` for decision trail
     - `webhook_source=alertmanager` vs `source.type=prometheus` distinction

- [ ] **Step 2: Update system-design.md**

Add **External Alert Sources** subsection with adapter layer diagram from spec §3.2 and §11 reuse table summary.

- [ ] **Step 3: Commit**

```bash
git add docs/api-reference.md docs/architecture/system-design.md
git commit -m "docs: document AlertManager webhook endpoint and adapter architecture"
```

---

### Task 11: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v --cov=langops --cov-report=term-missing
```

Expected: ALL PASS, new modules ≥80% coverage.

- [ ] **Step 2: Run linters**

```bash
uv run black src/ tests/ && uv run isort src/ tests/ && uv run flake8 src/ && uv run mypy src/
```

Expected: no new errors.

- [ ] **Step 3: Manual smoke test**

```bash
uv run python -m langops.server &
curl -s -X POST http://localhost:8000/api/v1/webhooks/alertmanager \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/am_webhook_sample.json | jq .
```

(Create `tests/fixtures/am_webhook_sample.json` from Task 3 SAMPLE_PAYLOAD if helpful.)

- [ ] **Step 4: Verify audit log**

```bash
tail -5 logs/langops-audit.log
```

Expected: `webhook.received` and `alert.processed` JSON lines.

---

## Plan Self-Review Checklist

| Spec requirement | Task |
|------------------|------|
| POST /api/v1/webhooks/alertmanager | Task 8 |
| AlertmanagerAdapter | Task 4 |
| process_one_alert reuse | Task 5 |
| Audit log + 7d retention | Task 2 |
| ?coalesce=Nm | Task 6 + 8 |
| max_payload_bytes enforcement | Task 8 (§3.6) |
| workers>1 disables coalesce | Task 8 |
| description fallback | Task 4 |
| severity aligns with validator | Task 4 |
| gather partial failure (no raise) | Task 5 |
| webhook_source vs source.type | Task 4 + 8 |
| Prometheus metrics | Task 7 |
| API docs sync | Task 10 |
| .env.example | Task 9 |
| CMS reuse seams (§11) | Tasks 2, 5, 6, 8 |

No TBD/TODO placeholders remain.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-26-prometheus-webhook-adapter.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
