"""Prometheus metrics for LangOps application observability."""

from prometheus_client import Counter, Histogram

PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# ── Alert metrics ────────────────────────────────────────────────────

alerts_received_total = Counter(
    "langops_alerts_received_total",
    "Total alerts received",
    ["severity", "category"],
)

alerts_processed_total = Counter(
    "langops_alerts_processed_total",
    "Total alerts processed",
    ["severity", "status"],
)

alert_processing_duration_seconds = Histogram(
    "langops_alert_processing_duration_seconds",
    "Alert processing end-to-end duration",
    buckets=(0.5, 1, 2, 5, 10, 15, 30, 60, 120),
)

# ── Dedup metrics ────────────────────────────────────────────────────

dedup_suppressed_total = Counter(
    "langops_dedup_suppressed_total",
    "Total alerts suppressed by deduplication",
)

# ── LLM metrics ──────────────────────────────────────────────────────

llm_calls_total = Counter(
    "langops_llm_calls_total",
    "Total LLM API calls",
    ["model", "status"],
)

llm_call_duration_seconds = Histogram(
    "langops_llm_call_duration_seconds",
    "LLM API call duration",
    ["model"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60),
)

llm_tokens_total = Counter(
    "langops_llm_tokens_total",
    "Total LLM tokens consumed",
    ["model", "type"],
)

# ── Collector metrics ────────────────────────────────────────────────

collector_query_duration_seconds = Histogram(
    "langops_collector_query_duration_seconds",
    "Data collector query duration",
    ["source"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# ── Remediation metrics ──────────────────────────────────────────────

remediation_plans_total = Counter(
    "langops_remediation_plans_total",
    "Total remediation plans created",
    ["risk_level"],
)

remediation_actions_total = Counter(
    "langops_remediation_actions_total",
    "Total remediation actions taken",
    ["action", "status"],
)

# ── HTTP metrics ─────────────────────────────────────────────────────

http_requests_total = Counter(
    "langops_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "langops_http_request_duration_seconds",
    "HTTP request duration",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# ── Webhook metrics ──────────────────────────────────────────────────

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
