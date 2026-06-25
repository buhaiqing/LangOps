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
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
}

function switchTab(name) {
  const tabs = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".panel");
  tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  panels.forEach((p) => p.classList.toggle("active", p.id === `panel-${name}`));
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
      let text = formatJson(body);
      if (body.remediation_plan_id) {
        text += `\n\n→ 修复计划: ${body.remediation_plan_id}（可在「修复审批」页签处理）`;
      }
      setResult(result, text, !body.success);
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

function initPredictForm() {
  const form = $("#predict-form");
  const result = $("#predict-result");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    setResult(result, "预测中…");

    try {
      const data = new FormData(form);
      const payload = {
        resource_type: "kubernetes",
        system: data.get("system"),
        namespace: data.get("namespace"),
        pod_name: data.get("pod_name"),
        horizon_hours: Number(data.get("horizon_hours") || 24),
      };
      const body = await fetchJson("/api/v1/predict", {
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

let selectedPlanId = null;

function riskClass(level) {
  if (level === "low") return "risk-low";
  if (level === "medium") return "risk-medium";
  return "risk-high";
}

function renderPlanList(plans) {
  const list = $("#remediation-list");
  list.innerHTML = "";

  if (!plans.length) {
    list.innerHTML = '<li class="plan-empty">暂无待审批计划</li>';
    return;
  }

  plans.forEach((plan) => {
    const item = document.createElement("li");
    item.className = "plan-item" + (plan.plan_id === selectedPlanId ? " active" : "");
    item.dataset.planId = plan.plan_id;
    item.innerHTML = `
      <div class="plan-item-title">${plan.summary}</div>
      <div class="plan-item-meta">
        <span>${plan.plan_id}</span> ·
        <span class="${riskClass(plan.risk_level)}">${plan.risk_level}</span> ·
        ${plan.commands.length} 条命令
      </div>`;
    item.addEventListener("click", () => selectPlan(plan.plan_id));
    list.appendChild(item);
  });
}

async function selectPlan(planId) {
  selectedPlanId = planId;
  const result = $("#remediation-result");
  const actions = $("#remediation-actions");
  setResult(result, "加载中…");
  actions.hidden = true;

  try {
    const plan = await fetchJson(`/api/v1/remediation/${planId}`);
    setResult(result, plan);
    actions.hidden = plan.status !== "pending_approval";
    const refreshBtn = $("#remediation-refresh");
    if (refreshBtn.dataset.loaded === "1") {
      const plans = await fetchJson("/api/v1/remediation");
      renderPlanList(plans);
    }
  } catch (err) {
    setResult(result, err.message, true);
  }
}

function initRemediationPanel() {
  const refreshBtn = $("#remediation-refresh");
  const result = $("#remediation-result");
  const dryRunBtn = $("#remediation-dry-run");
  const rejectBtn = $("#remediation-reject");

  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    setResult(result, "加载中…");
    $("#remediation-actions").hidden = true;

    try {
      const plans = await fetchJson("/api/v1/remediation");
      refreshBtn.dataset.loaded = "1";
      renderPlanList(plans);
      if (plans.length) {
        await selectPlan(plans[0].plan_id);
      } else {
        selectedPlanId = null;
        setResult(result, "暂无待审批计划");
      }
    } catch (err) {
      setResult(result, err.message, true);
    } finally {
      refreshBtn.disabled = false;
    }
  });

  dryRunBtn.addEventListener("click", async () => {
    if (!selectedPlanId) return;
    const approvedBy = $("#remediation-user").value.trim();
    if (!approvedBy) {
      setResult(result, "请填写审批人", true);
      return;
    }
    dryRunBtn.disabled = true;
    try {
      const body = await fetchJson(`/api/v1/remediation/${selectedPlanId}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_by: approvedBy, confirm: true, dry_run: true }),
      });
      setResult(result, body, !body.success);
      $("#remediation-actions").hidden = true;
      refreshBtn.click();
    } catch (err) {
      setResult(result, err.message, true);
    } finally {
      dryRunBtn.disabled = false;
    }
  });

  rejectBtn.addEventListener("click", async () => {
    if (!selectedPlanId) return;
    const rejectedBy = $("#remediation-user").value.trim();
    if (!rejectedBy) {
      setResult(result, "请填写审批人", true);
      return;
    }
    rejectBtn.disabled = true;
    try {
      const body = await fetchJson(`/api/v1/remediation/${selectedPlanId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rejected_by: rejectedBy, reason: "Web UI reject" }),
      });
      setResult(result, body, !body.success);
      $("#remediation-actions").hidden = true;
      refreshBtn.click();
    } catch (err) {
      setResult(result, err.message, true);
    } finally {
      rejectBtn.disabled = false;
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initAlertForm();
  initQueryForm();
  initPredictForm();
  initRemediationPanel();
  refreshHealth();
});
