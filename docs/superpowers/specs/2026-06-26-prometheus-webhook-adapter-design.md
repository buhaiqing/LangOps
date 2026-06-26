# Prometheus AlertManager Webhook Adapter — Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a webhook endpoint that receives Prometheus AlertManager notifications, maps them to LangOps `AlertCreate`, and feeds them into the existing analysis pipeline. Defer Aliyun CMS to a follow-up spec after we evaluate whether `AlertCreate` needs extension.

**Architecture:** New `webhooks` route group under `/api/v1/webhooks`. A dedicated `AlertmanagerAdapter` class owns payload parsing and field mapping (no global monkey-patching). The handler reuses `AlertProcessor`, `AlertNoiseReducer`, and the existing `/api/v1/alerts` processing flow verbatim — only payload shape changes. Webhook receives N alerts per callback; processing is synchronous per batch with `asyncio.gather`. Optional `?coalesce=Nm` query param enables an in-process time-window buffer for storm scenarios.

**Tech Stack:** FastAPI (existing), Pydantic v2 (existing), asyncio (existing). **No new dependencies.**

---

## 1. Motivation

`POST /api/v1/alerts` currently accepts a hand-built `AlertCreate` JSON. External monitoring systems (Prometheus AlertManager, Aliyun CMS, etc.) do not speak this format — operators must write a translator before they can integrate LangOps. This adapter layer is the translation boundary.

**Why AlertManager first:** It has the most stable, well-documented payload schema (open spec, used by every major monitoring stack). Aliyun CMS uses a different structure and will arrive as a separate spec.

## 2. Scope

### In Scope

1. `POST /api/v1/webhooks/alertmanager` — accepts AM v4 webhook payload
2. `AlertmanagerAdapter` — parses + maps AM payload → `list[AlertCreate]`
3. Per-alert processing reusing `AlertProcessor`, `AlertNoiseReducer`, `JiraService`, `RemediationRegistry` (no logic duplication)
4. Audit log entries for every webhook reception and per-alert decision (process / suppress / failure)
5. `?coalesce=Nm` time-window aggregation (in-process buffer, opt-in via query param)
6. Configurable max payload size + per-batch alert cap (DoS guard)
7. API docs update (`docs/api-reference.md`) with webhook endpoint, curl example, payload sample, response shape
8. Unit tests for adapter mapping + integration tests for the route
9. Prometheus metrics for webhook calls (counter + duration histogram, low-cardinality labels only)

### Out of Scope (Deferred)

- **Aliyun CMS webhook** — separate spec, triggered after this one lands. Spec re-evaluates `AlertCreate` extensions.
- **Generic webhook abstraction (`BaseAlertSourceAdapter`)** — YAGNI. We have exactly one concrete adapter today; abstract on the second one (CMS).
- **Async job queue / 202 Accepted / persistent Job table** — explicitly rejected (see §6 Decision Log). MVP users can scale LangOps vertically.
- **Signature verification (HMAC)** — out of MVP. Webhook is intended for trusted internal networks per AGENTS.md §3.4. Add when exposed beyond the cluster.
- **Cross-webhook state persistence for coalesce** — buffer is in-process only; a process restart drops the pending window. Acceptable for MVP; upgrade path documented in §9.

## 3. Architecture

### 3.1 Component Layout

```
src/langops/
├── core/
│   ├── audit.py                    # NEW: AuditLogger (rotating file, 7d retention)
│   └── config.py                   # MODIFY: WebhookSettings
├── models/
│   └── webhook.py                  # NEW: AM v4 payload + WebhookBatchResponse
├── adapters/
│   ├── __init__.py                 # NEW (package marker)
│   └── alertmanager.py             # NEW: AlertmanagerAdapter (parse + map)
├── web/
│   ├── _alert_flow.py              # NEW: process_one_alert helper
│   ├── _coalesce.py                # NEW: CoalesceBuffer + parse_coalesce_duration
│   ├── api/
│   │   ├── alerts.py               # MODIFY: delegate to process_one_alert
│   │   └── webhooks.py             # NEW: webhook routes
│   ├── dependencies.py             # MODIFY: adapter, audit, coalesce DI
│   ├── main.py                     # MODIFY: include webhooks router
│   └── metrics.py                  # MODIFY: webhook counters/histograms

tests/
├── unit/
│   ├── test_core/
│   │   └── test_audit.py           # NEW
│   ├── test_adapters/
│   │   └── test_alertmanager_adapter.py   # NEW
│   ├── test_models/
│   │   └── test_webhook_payload.py        # NEW
│   └── test_web/
│       ├── test_alert_flow.py             # NEW
│       └── test_coalesce_buffer.py        # NEW
└── integration/
    └── test_webhook_alertmanager.py       # NEW
```

**File responsibility:**

| File | Responsibility | Does NOT do |
|------|---------------|-------------|
| `core/audit.py` | `AuditLogger` — dedicated rotating audit file | Business logic |
| `web/_alert_flow.py` | `process_one_alert()` shared by alerts + webhooks routes | HTTP routing |
| `web/_coalesce.py` | `CoalesceBuffer`, `parse_coalesce_duration()` | Adapter mapping |
| `models/webhook.py` | Pydantic schema for AM v4 payload + `WebhookBatchResponse` | Mapping logic, HTTP handling |
| `adapters/alertmanager.py` | `AlertmanagerAdapter.to_alert_creates(payload) -> list[AlertCreate]` | HTTP, logging, dedup |
| `web/api/webhooks.py` | HTTP route, batch dispatch, coalesce wiring | Adapter internals |
| `web/dependencies.py` | DI factories for adapter + coalesce buffer | Anything else |

### 3.2 Data Flow

```
AM ──POST──▶ FastAPI route
                  │
                  ├─ Read raw body; reject if len(body) > max_payload_bytes (422)
                  ├─ Pydantic validates AM payload (rejected → 422)
                  ├─ Reject if len(alerts) > max_alerts_per_batch (422)
                  ├─ Adapter maps payload → list[AlertCreate]
                  ├─ Coalesce branch (if ?coalesce=Nm AND workers==1):
                  │     └─ push alerts into CoalesceBuffer
                  │        └─ buffer flushes after window → asyncio.Task → process_one_alert × N
                  └─ Default branch:
                        └─ asyncio.gather(*[
                             process_one_alert(...)  # catches all exceptions internally
                           ])
                  │
                  └─ Response: 200 OK with per-alert results list
```

**Batch error isolation:** `process_one_alert` **must catch all exceptions** and return `AnalysisResponse(success=False, error=...)`. `asyncio.gather` may use `return_exceptions=False` safely because no task raises. This matches existing `create_alert` try/except semantics (§5).

### 3.3 Audit Log

Every webhook event records a structured log line with these fields:

| Event | Log key | Required fields |
|-------|---------|-----------------|
| Webhook received | `webhook.received` | `webhook_source`, `request_id`, `alert_count`, `group_labels` (truncated to first 5 keys) |
| Per-alert processed | `alert.processed` | `webhook_source`, `alert_id`, `decision` (process/suppress/failure), `fingerprint`, `trace_id` (if RCA ran), `duration_ms` |
| Coalesce window opened | `coalesce.opened` | `webhook_source`, `coalesce_seconds`, `first_alert_id` |
| Coalesce window flushed | `coalesce.flushed` | `webhook_source`, `coalesce_seconds`, `alert_count`, `duration_ms` |
| Adapter mapping failed | `adapter.mapping_failed` | `webhook_source`, `alert_index`, `error` |

**Audit log destination:** `logs/langops-audit.log` (rotated daily, retained 7 days). Configurable via `WebhookSettings.audit_log_path` and `WebhookSettings.audit_log_retention_days`. **Default retention: 7 days** (configurable). Cleanup happens via `TimedRotatingFileHandler`'s built-in retention — no separate cleanup job required.

**Log level:** `INFO` for audit events (always recorded, regardless of `LOG_LEVEL`). `WARNING`+ for failures.

**What's NOT in the audit log:** full alert payloads, raw AM annotations, secrets, API keys.

### 3.4 Refactor: extract `process_one_alert` from `POST /api/v1/alerts`

Current `src/langops/web/api/alerts.py::create_alert` contains the full processing flow inline (~100 lines). Both the existing route AND the new webhook route need this flow. **Extract** `process_one_alert(alert_create, processor, dedup, remediation_registry, jira, *, webhook_source: str | None = None, audit: AuditLogger | None = None) -> AnalysisResponse` into `src/langops/web/_alert_flow.py`.

**Constraint:** The existing route's behavior and response shape must remain identical. Re-run `tests/unit/test_web/test_api.py` after refactor — no test modifications required.

**Helper location:** `src/langops/web/_alert_flow.py` (new private module). Rationale: it imports web-layer dependencies (`JiraService`, `RemediationRegistry`) and orchestrates metrics — not pure agent logic. Keeping it under `web/` makes the dependency direction clear (`web → agent`, never the reverse).

**Exception policy:** `process_one_alert` wraps the entire flow in `try/except Exception` and always returns `AnalysisResponse` — never raises. Per-alert failures become `success=False` entries in the webhook batch response.

### 3.5 Coalesce Buffer

`?coalesce=Nm` enables an in-process time-window aggregator:

- Parse query param `coalesce` (seconds; format `Nm` like `5m`, `30s`, `1h`)
- On every webhook with coalesce enabled, push alerts into `CoalesceBuffer`
- The buffer holds **one pending window per webhook_source**. New alerts reset the window timer (last-received-wins — simplest semantics, documented below).
- When window expires, the buffer flushes: spawns an `asyncio.Task` that processes the batch through the same `process_one_alert` helper, then marks itself flushed.
- Buffer is in-process; **process restart drops pending windows**. This is the `ponytail:` simplification.

**Coalesce semantics (deliberate simplification):**

| Behavior | Choice | Why |
|----------|--------|-----|
| Window reset on new alert | **Yes** (last-received-wins) | Simpler than fixed windows; preserves freshness |
| Per-source buckets | **Yes** (one per webhook_source) | Prevents unrelated alerts from being aggregated |
| Buffer cap | **Yes** (`max_buffered_alerts`, default 500) | DoS guard |
| Overflow behavior | **Flush immediately** + log WARNING | Better than dropping alerts |
| Process restart | **Drop pending** | Acceptable; AM will re-send on next firing cycle |

**Configuration (`WebhookSettings`):**

| Setting | Default | Purpose |
|---------|---------|---------|
| `max_payload_bytes` | `1_048_576` (1MB) | Reject oversized webhooks (422) |
| `max_alerts_per_batch` | `100` | Reject batches over this (422) |
| `audit_log_path` | `logs/langops-audit.log` | Audit log file |
| `audit_log_retention_days` | `7` | Auto-cleanup window |
| `coalesce_max_buffered_alerts` | `500` | Per-source buffer cap |

**Multi-worker constraint:** Coalesce buffer is **in-process only**. When `settings.workers > 1`, the webhook route **ignores** the `?coalesce=` parameter and logs a WARNING (`coalesce.disabled_multi_worker`). Document this in API reference troubleshooting. Upgrade path: Redis-backed buffer (§9).

### 3.6 Payload Size Enforcement

Before Pydantic parsing, the route reads the raw body via `await request.body()` and checks `len(body) <= settings.webhook.max_payload_bytes`. If exceeded, return **422** with `{"detail": "payload too large"}`. This prevents large bodies from being parsed into memory twice.

If `Content-Length` header is present and exceeds the limit, reject immediately without reading the body.

## 4. API Contract

### 4.0 Identifier Conventions

Two parallel identifier namespaces — do not conflate:

| Field | AM endpoint value | Used in | Purpose |
|-------|-------------------|---------|---------|
| `webhook_source` | `"alertmanager"` | Audit log, metrics labels, coalesce bucket key | Identifies which webhook endpoint received the callback |
| `AlertSource.type` | `"prometheus"` | Domain model, dedup fingerprint, collectors | Identifies the underlying monitoring system for RCA/collection |

Future CMS endpoint: `webhook_source="aliyun_cms"`, `AlertSource.type="aliyun"`.

### 4.0a Prometheus Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `langops_webhook_received_total` | Counter | `webhook_source`, `status` (`success`/`validation_error`/`error`) |
| `langops_webhook_duration_seconds` | Histogram | `webhook_source` |
| `langops_webhook_alerts_received_total` | Counter | `webhook_source` |

Labels must be low-cardinality enums only — never `alert_id` or `request_id`.

### 4.1 `POST /api/v1/webhooks/alertmanager`

**Headers:** `Content-Type: application/json` (required).

**Query parameters:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `coalesce` | string (`Ns`/`Nm`/`Nh`) | unset | Enable time-window aggregation. `?coalesce=5m` buffers alerts for 5 minutes after the last arrival, then processes them as one batch. |

**Request body:** AlertManager v4 webhook payload. Schema validated by `AlertmanagerWebhookPayload` Pydantic model. See §4.2.

**Response codes:**

| Code | When |
|------|------|
| `200 OK` | Webhook accepted. Body contains per-alert results. |
| `422 Unprocessable Entity` | Pydantic validation failed (malformed payload, size exceeded, batch too large). |
| `500 Internal Server Error` | Unexpected failure. Audit log records the error. |

**Response body (200):**

```json
{
  "success": true,
  "received": 3,
  "results": [
    {
      "alert_id": "alert-a1b2c3d4",
      "success": true,
      "data": { /* AnalysisResponse.data */ },
      "error": null,
      "dedup": { "fingerprint": "fp-...", "action": "process", "occurrence_count": 1 },
      "remediation_plan_id": "plan-..."
    },
    {
      "success": true,
      "data": null,
      "dedup": { "fingerprint": "fp-...", "action": "suppress", "occurrence_count": 3 }
    },
    {
      "success": false,
      "error": "LLM timeout"
    }
  ],
  "audit": {
    "request_id": "req-...",
    "coalesced": false
  }
}
```

**Response body (coalesced):** `coalesced: true` and `results: []` (results are not in-band; the actual processing happens asynchronously after the window expires).

### 4.2 AlertManager Payload Schema

AM v4 payload (excerpt; full schema in Pydantic model):

```json
{
  "version": "4",
  "groupKey": "{}:{alertname=\"HighCPU\"}",
  "status": "firing",
  "receiver": "langops",
  "groupLabels": {"alertname": "HighCPU"},
  "commonLabels": {"alertname": "HighCPU", "severity": "critical"},
  "commonAnnotations": {"summary": "CPU > 90% for 5m"},
  "externalURL": "http://alertmanager:9093",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighCPU",
        "severity": "critical",
        "namespace": "production",
        "pod": "order-service-abc"
      },
      "annotations": {
        "summary": "High CPU usage",
        "description": "Pod CPU > 90% for 5 minutes"
      },
      "startsAt": "2024-01-15T10:30:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "generatorURL": "http://prometheus:9090/graph?..."
    }
  ]
}
```

**Pydantic model:** `src/langops/models/webhook.py::AlertmanagerWebhookPayload` with `extra="ignore"` (forward compatibility with future AM versions).

### 4.3 Mapping Rules (`AlertmanagerAdapter`)

| AM field | LangOps `AlertCreate` field | Notes |
|----------|----------------------------|-------|
| `alerts[i].annotations.summary` (or first non-empty annotation value) | `title` | Required, ≤500 chars; truncate if longer |
| Fallback chain (see below) | `description` | Required, ≤10000 chars; truncate if longer |
| `alerts[i].labels.severity` (pass through; `Alert` validator normalizes) | `severity` | Adapter passes raw label string; `Alert.normalize_severity` handles mapping |
| Inferred from alertname + labels (deterministic keyword match) | `category` | First-match wins (checked in this order): keywords `cpu|memory|disk|fs|filesystem` → `resource`; `down|unreachable|timeout|unavailable|outage` → `availability`; `latency|slow|throttle|backlog` → `performance`; `auth|unauthorized|forbidden|intrusion` → `security`. Fallback: `performance`. Match is case-insensitive against `alertname` + concatenated `labels.values()`. |
| `type = "prometheus"` (hard-coded) | `source.type` | AM is always the source type for this endpoint |
| `externalURL` host or `labels.job` | `source.system` | Prefer externalURL host; fallback `labels.job` |
| `labels.namespace` | `source.namespace` | Optional |
| `labels.pod` or `labels.instance` | `source.pod_name` / `source.instance_id` | Heuristic: `pod-*` patterns → `pod_name`; otherwise `instance_id` |
| `labels.service` | `source.service` | Optional |
| `labels.alertname`, `labels.severity`, `labels.namespace`, top-3 other labels | `context` | Arbitrary enrichment for RCA |
| All other labels | `context["labels"]` | Key: full label dict |
| All annotations | `context["annotations"]` | Key: full annotation dict |
| `alerts[i].startsAt` | `context["starts_at"]` | ISO 8601 string |
| `alerts[i].endsAt` (if non-zero) | `context["ends_at"]` | ISO 8601 string |
| `alerts[i].status` | `context["alertmanager_status"]` | `firing` / `resolved` |
| `metric_data` | (none, AM doesn't send it directly) | Pass empty dict; collector fetches metrics at RCA time |

**`description` fallback chain** (first non-empty wins):

1. `alerts[i].annotations.description`
2. `alerts[i].annotations.summary`
3. `alerts[i].annotations.message` (some AM rules use this key)
4. `f"{labels.alertname}: {alerts[i].status}"` (last resort — always non-empty if alertname present)

**`severity` normalization** — Adapter passes the raw `labels.severity` string (or `"medium"` if missing). `Alert` model's `normalize_severity` validator ( `models/alert.py:60` ) performs the final mapping:

| AM label value | LangOps `AlertSeverity` (via validator) |
|----------------|------------------------------------------|
| `critical`, `page` | `CRITICAL` |
| `high` | `HIGH` |
| `medium`, `warning`, `warn` | `MEDIUM` |
| `low` | `LOW` |
| `info`, `information` | `INFO` |
| (anything else, missing) | `INFO` (validator default) |

Adapter may pre-normalize common AM values (`page` → `critical`) before constructing `AlertCreate`, but **must not contradict** the validator table above.

## 5. Error Handling

| Failure | Behavior |
|---------|----------|
| Malformed JSON | 422, audit `adapter.mapping_failed` or `webhook.received` skipped; log WARNING via structlog |
| Payload > `max_payload_bytes` | 422 with `{"detail": "payload too large"}` — checked on raw body before Pydantic (§3.6) |
| `len(alerts) > max_alerts_per_batch` | 422 with `error: "batch too large"` |
| Pydantic validation error | 422, audit log `WARNING` with `validation_errors` (truncated) |
| Per-alert RCA failure | That alert's `results[i]` has `success: false`, others continue. Webhook returns 200 (partial success). Audit log `WARNING` per failing alert. |
| Coalesce buffer overflow | Flush immediately, log `WARNING`. |
| Audit log write failure | Logged to stderr at ERROR; does not fail the webhook. |

**No retries are initiated by LangOps.** AM owns retry semantics via its `repeat_interval` config.

## 6. Decision Log

| Decision | Choice | Rejected alternative | Why |
|----------|--------|---------------------|-----|
| Sync vs async response | **Sync 200** (with optional `?coalesce=`) | 202 Accepted + Job table | Job table requires storage layer (currently disabled), scheduler, worker — 1.5 weeks. Sync serves MVP. Coalesce handles the only scenario where async adds real value (storm aggregation). |
| Adapter as concrete class | `AlertmanagerAdapter` (concrete) | `BaseAlertSourceAdapter` abstract | YAGNI. Abstract on the second concrete adapter (CMS). |
| Coalesce implementation | In-process asyncio buffer | Redis Streams / persistent queue | Single-instance MVP. Upgrade path documented. |
| HMAC signature verification | **Not in MVP** | HMAC SHA256 | Webhook is trusted internal (AGENTS.md §3.4). Add when exposed externally. |
| Audit log destination | Dedicated rotated file | Reuse main log | Audit log has different retention (7d) and write semantics (always INFO); mixed into main log is harder to parse for compliance. |
| Audit cleanup | `TimedRotatingFileHandler` built-in | Separate cleanup cron | No external dependencies; `logging.handlers` is stdlib. |
| Refactor of `create_alert` | **Extract** `process_one_alert` helper | Duplicate logic in webhook route | DRY. Existing tests guarantee behavior preservation. |
| AlertCreate extensions | **Defer** to CMS spec | Extend now | No current evidence CMS needs fields AM doesn't have. Premature. |

## 7. Testing

### Unit Tests (`tests/unit/`)

| Test file | Coverage |
|-----------|----------|
| `test_models/test_webhook_payload.py` | Pydantic parses a real AM v4 payload (sample from official docs), rejects malformed (extra required fields, missing alerts array), accepts future-compatible extras |
| `test_adapters/test_alertmanager_adapter.py` | Mapping rules per §4.3, severity via validator, description fallback chain (no description → summary → message → alertname), truncation, multi-alert payload, `status=resolved` |
| `test_web/test_coalesce_buffer.py` | Buffer accepts alerts up to cap, overflow flushes + warns, window resets on push, flush spawns processing task |

### Integration Tests (`tests/integration/test_api/`)

| Test file | Coverage |
|-----------|----------|
| `test_webhook_alertmanager.py` | Happy path, multi-alert gather, suppress, per-alert failure (mock LLM), oversize payload → 422, malformed JSON → 422, coalesce returns immediately, audit log entries, `workers>1` ignores coalesce |
| Regression | Re-run `tests/unit/test_web/test_api.py` after `process_one_alert` refactor — no new regression file needed |

### Test Pattern Notes

- Mock `AlertProcessor.process` (use `unittest.mock.AsyncMock`) — no real LLM calls
- Mock `AlertNoiseReducer.evaluate` for deterministic dedup outcomes
- Use `httpx.AsyncClient` + FastAPI `TestClient` (existing pattern)
- Coalesce tests use `asyncio.sleep` with monkey-patched clock or short windows (1s) for speed

## 8. Documentation

### `docs/api-reference.md` updates (REQUIRED — do not skip)

Add a new section after §4 (POST /api/v1/alerts):

**§5. POST /api/v1/webhooks/alertmanager — Prometheus Webhook** containing:
- Endpoint description (1 paragraph)
- Request body schema with full field table
- curl example using a real AM payload
- `?coalesce` query parameter explanation
- Response shape (200 success, 422 error)
- Configuration table (env vars)
- Common troubleshooting (3-5 bullets)

Renumber subsequent sections (§5 → §6, etc.). Update the table of contents at the top.

### `docs/architecture/system-design.md` updates

Add a new "External Alert Sources" subsection in the integration chapter describing the adapter layer, with a small ASCII diagram of the data flow from §3.2.

### `docs/superpowers/specs/` README (if exists)

Cross-link this spec.

### `.env.example` updates

Add new variables under a `# Webhooks (Prometheus AlertManager)` section:
- `WEBHOOK_MAX_PAYLOAD_BYTES=1048576`
- `WEBHOOK_MAX_ALERTS_PER_BATCH=100`
- `WEBHOOK_AUDIT_LOG_PATH=logs/langops-audit.log`
- `WEBHOOK_AUDIT_LOG_RETENTION_DAYS=7`
- `WEBHOOK_COALESCE_MAX_BUFFERED_ALERTS=500`

### `CHANGELOG.md`

Skip — file does not exist in the repository. If added later, include: `feat(webhooks): Prometheus AlertManager webhook adapter with optional time-window coalescing`.

## 9. Upgrade Path (Future)

When LangOps outgrows the in-process coalesce buffer:

1. Replace `CoalesceBuffer` with Redis-backed buffer (existing redis dependency — no new infra).
2. Introduce `Job` model + persistent table when async 202 becomes a real requirement.
3. Add HMAC signature verification when webhooks are exposed beyond trusted network.
4. Introduce `BaseAlertSourceAdapter` when the second concrete adapter (CMS) arrives.
5. When `AlertCreate` is extended for CMS, re-examine if `Alert` model needs new optional fields (e.g., `original_source`).

## 10. Open Questions

1. **Should we also accept AM v3 payload?** v3 has slightly different field shapes. **Recommendation: reject (422)** unless there's an operational need. AM v4 has been stable since 2021; any v3 instance is well past upgrade window.
2. **`alerts[i].status = "resolved"` mapping** — currently this gets `context["alertmanager_status"]="resolved"` but is otherwise treated identically to `firing`. Should `resolved` alerts skip RCA (it's already fixed)? **Recommendation: process identically for v1**; revisit when RCA-on-resolved becomes a real complaint.
3. **Coalesce window reset on new alert** — is "last-received-wins" the right semantic, or should it be "first-received-wins + fixed window"? Documented as last-received; revisit based on real usage.

## 11. Multi-Source Webhook Architecture (Forward-Looking Constraints)

**Motivation:** Aliyun CMS webhook is coming as a separate spec after this one lands. To minimize duplicated code and inconsistent UX, **this spec pre-commits to design constraints** that make the CMS adapter a near-mechanical addition. The actual CMS implementation stays in its own spec; this section just locks in the seams.

### 11.1 Reuse Boundaries

| Concern | Lives in (this spec) | Reusable by CMS (future spec) |
|---------|----------------------|-------------------------------|
| Per-alert processing flow (dedup → RCA → persist → JIRA) | `src/langops/web/_alert_flow.py::process_one_alert` | ✅ **Direct call** — CMS adapter maps → calls same helper |
| Coalesce buffer | `src/langops/web/_coalesce.py::CoalesceBuffer` | ✅ Same buffer, keyed by `webhook_source` so AM and CMS coexist independently |
| Audit log writer | `src/langops/core/audit.py::AuditLogger` (new, see §11.2) | ✅ Same logger, same file, source-tagged |
| Metrics | `src/langops/web/metrics.py` (existing, add new counters) | ✅ Same metrics module |
| Config (max payload, audit retention, coalesce buffer cap) | `WebhookSettings` | ✅ All settings are source-agnostic (no per-source knobs in v1) |

### 11.2 New Module: `src/langops/core/audit.py`

A dedicated audit logger module — not inline `structlog` calls. Provides:

```python
class AuditLogger:
    def __init__(self, path: str, retention_days: int) -> None: ...
    def info(self, event: str, **fields: Any) -> None: ...   # always INFO
    def warning(self, event: str, **fields: Any) -> None: ...
```

**Why a separate module (not just more `logger.info` calls):**
- Audit log has its own file path + retention — needs `TimedRotatingFileHandler` config independent of main log
- Always logs at INFO regardless of `LOG_LEVEL` setting (compliance requirement)
- Single place to enforce "no secrets, no full payloads, truncate labels" rules
- Future CMS spec just imports `AuditLogger` — no duplication

**Audit events (canonical set, both sources share these):**

| Event key | Emitted by | Fields |
|-----------|-----------|--------|
| `webhook.received` | webhook route | `webhook_source`, `request_id`, `alert_count` |
| `alert.processed` | `process_one_alert` | `webhook_source`, `alert_id`, `decision`, `fingerprint`, `trace_id?`, `duration_ms` |
| `coalesce.opened` | `CoalesceBuffer` | `webhook_source`, `coalesce_seconds`, `first_alert_id` |
| `coalesce.flushed` | `CoalesceBuffer` | `webhook_source`, `coalesce_seconds`, `alert_count`, `duration_ms` |
| `adapter.mapping_failed` | adapter | `webhook_source`, `alert_index`, `error` (when mapping throws) |

The `webhook_source` field is **always present**. Values: `alertmanager` (this spec), `aliyun_cms` (future CMS spec). Do **not** use `prometheus` as `webhook_source` — that value is reserved for `AlertSource.type`.

### 11.3 Response Shape Compatibility

Webhook response (§4.1) is **source-agnostic** — the `results` array structure is identical for AM and CMS. This means:
- Frontend can render either source identically
- Tests for response shape are shared (factored into a helper assertion)
- A future unified dashboard needs no special-casing per source

### 11.4 URL Naming Convention

Each source gets its own path under `/api/v1/webhooks/{source}`:

| Source | Path |
|--------|------|
| Prometheus AlertManager | `/api/v1/webhooks/alertmanager` |
| Aliyun CMS (future) | `/api/v1/webhooks/aliyun/cms` (or `/aliyun_cms` — CMS spec decides) |

This makes routing, rate-limiting, and audit filtering trivial (`/webhooks/aliyun/*` vs `/webhooks/prometheus/*`).

### 11.5 Adapter Interface Boundary (Soft Contract)

**Not a Python `Protocol` or abstract base class** — that would be premature (YAGNI: only one adapter exists). Instead, we agree on a **method signature convention** that CMS will follow:

```python
class AliyunCmsAdapter:  # future
    def to_alert_creates(self, payload: AliyunCmsPayload) -> list[AlertCreate]: ...
```

Same shape as `AlertmanagerAdapter`. When CMS lands, we can introduce `AlertSourceAdapter(Protocol)` if the duplication actually hurts. **Today: comments + this spec section are the contract.**

### 11.6 Re-evaluation Trigger for `AlertCreate`

After CMS spec lands, evaluate whether `AlertCreate` needs new fields. Likely candidates (to be confirmed by CMS spec):

| Possible extension | Driven by CMS field | Required? |
|--------------------|--------------------|-----------|
| `source.resource_id` (separate from `instance_id`) | CMS `resourceId` vs `instanceId` distinction | TBD by CMS spec |
| `source.region` (separate from `system`) | CMS regional hierarchy | TBD by CMS spec |
| `alertmanager_status` moves from `context` to typed field | CMS uses different lifecycle vocabulary | TBD by CMS spec |

**If CMS spec decides no extensions are needed → `AlertCreate` stays as-is. If extensions are needed → bump to `AlertCreateV2` or add optional fields with backward compat.**

---

**Version:** 2026-06-26 (rev. 2 — post-review fixes)
**Author:** Brainstorming session, in collaboration with user
**Status:** Approved (2026-06-26)