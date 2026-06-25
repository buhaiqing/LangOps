/** LangOps Web UI — vanilla JS, no build step. ponytail: upgrade path = Vite/React SPA. */

function $(selector) {
  return document.querySelector(selector);
}

function formatJson(data) {
  return JSON.stringify(data, null, 2);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.detail || body.error || response.statusText);
  }
  return body;
}

function setResult(el, data, isError) {
  el.textContent = typeof data === "string" ? data : formatJson(data);
  el.classList.toggle("error", Boolean(isError));
}

async function refreshHealth() {
  const badge = $("#health-badge");
  try {
    const data = await fetchJson("/health");
    badge.textContent = data.status === "healthy" ? "服务正常" : data.status;
    badge.className = "badge badge-ok";
  } catch {
    badge.textContent = "服务异常";
    badge.className = "badge";
    badge.style.color = "var(--danger)";
  }
}

function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".panel");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const name = tab.dataset.tab;
      tabs.forEach((t) => t.classList.toggle("active", t === tab));
      panels.forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
    });
  });
}

function buildAlertPayload(form) {
  const data = new FormData(form);
  let metricData = {};
  const metricRaw = String(data.get("metric_data") || "{}").trim();
  if (metricRaw) {
    metricData = JSON.parse(metricRaw);
  }

  const source = {
    type: data.get("source_type"),
    system: data.get("system"),
  };
  const namespace = data.get("namespace");
  const podName = data.get("pod_name");
  if (namespace) source.namespace = namespace;
  if (podName) source.pod_name = podName;

  return {
    title: data.get("title"),
    description: data.get("description"),
    severity: data.get("severity"),
    category: data.get("category"),
    source,
    metric_data: metricData,
  };
}

function initAlertForm() {
  const form = $("#alert-form");
  const result = $("#alert-result");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    setResult(result, "分析中…");

    try {
      const payload = buildAlertPayload(form);
      const body = await fetchJson("/api/v1/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setResult(result, body, !body.success);
    } catch (err) {
      setResult(result, err.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

function initQueryForm() {
  const form = $("#query-form");
  const result = $("#query-result");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    setResult(result, "查询中…");

    try {
      const query = new FormData(form).get("query");
      const body = await fetchJson("/api/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      setResult(result, body, !body.success);
    } catch (err) {
      setResult(result, err.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initAlertForm();
  initQueryForm();
  refreshHealth();
});
