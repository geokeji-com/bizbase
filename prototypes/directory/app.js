"use strict";

// 此文件只供 prototypes/directory 使用。全部夹具是合成数据，不读取网络或浏览器存储。
const fixtures = Object.freeze({
  meta: Object.freeze({
    mode: "snapshot",
    data_as_of: "2026-11-02",
    version: "synthetic-v1",
    source_system: "synthetic-directory",
  }),
  customers: Object.freeze([
    Object.freeze({ customer_id: "synthetic-customer-a", name: "合成客户 A" }),
    Object.freeze({ customer_id: "synthetic-customer-b", name: "合成客户 B" }),
  ]),
  subjects: Object.freeze([
    Object.freeze({ subject_id: "synthetic-subject-a-01", customer_id: "synthetic-customer-a", name: "合成对象 A-01", source_type: "synthetic-type" }),
    Object.freeze({ subject_id: "synthetic-subject-a-02", customer_id: "synthetic-customer-a", name: "合成对象 A-02", source_type: null }),
  ]),
});

const state = {
  scenario: "normal", enabled: true, status: "ready", selectedId: null,
  customerQuery: "", subjectQuery: "", sequence: 0,
};
const content = document.querySelector("#directory-content");
const meta = document.querySelector("#snapshot-meta");
const scenarioSelect = document.querySelector("#scenario-select");
const toggleButton = document.querySelector("#directory-toggle");
const refreshButton = document.querySelector("#refresh-directory");
const notice = document.querySelector("#notice");
const liveStatus = document.querySelector("#live-status");
const icons = {
  folder: '<path d="M5 10h11l4 4h15v20H5V10Z"/><path d="M5 17h30"/>',
  search: '<circle cx="18" cy="18" r="10"/><path d="m26 26 9 9"/>',
  error: '<path d="M20 5 37 34H3L20 5Z"/><path d="M20 15v9m0 5v1"/>',
  lock: '<rect x="8" y="18" width="24" height="18" rx="3"/><path d="M13 18v-6a7 7 0 0 1 14 0v6m-7 14v3"/>',
  pause: '<circle cx="20" cy="20" r="15"/><path d="M16 14v12m8-12v12"/>',
};
const searchIcon = '<svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" stroke-width="1.5"/><path d="m13 13 4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function statePanel({ kind, title, description, action, compact = false, initial = false }) {
  return `<div class="empty-state${compact ? " compact-state" : ""}${initial ? " initial-state" : ""}" data-testid="${kind}-state">
    <svg class="state-icon" viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[kind] || icons.folder}</svg>
    <h2>${title}</h2><p>${description}</p>${action || ""}</div>`;
}

function announce(message) { liveStatus.textContent = message; }
function clearNotice() { notice.hidden = true; notice.textContent = ""; }
function showNotice(message) { notice.textContent = message; notice.hidden = false; announce(message); }

function render() {
  const blocked = ["source-error", "forbidden", "disabled"].includes(state.status);
  meta.hidden = blocked || state.status === "loading-directory";
  meta.querySelector('[data-testid="data-as-of"]').textContent = fixtures.meta.data_as_of;
  meta.querySelector('[data-testid="directory-version"]').textContent = fixtures.meta.version;
  meta.querySelector('[data-testid="source-system"]').textContent = fixtures.meta.source_system;
  scenarioSelect.value = state.scenario;
  toggleButton.textContent = state.enabled ? "模拟停用目录" : "模拟启用目录";
  toggleButton.setAttribute("aria-pressed", String(!state.enabled));
  refreshButton.disabled = !state.enabled || state.status.startsWith("loading");
  content.setAttribute("aria-busy", String(state.status.startsWith("loading")));

  if (blocked) {
    const states = {
      "source-error": { kind: "error", title: "暂时无法读取目录来源", description: "本次读取失败，请重试。", action: '<button type="button" class="button button-primary" data-action="retry" data-testid="retry-source">重试</button>' },
      forbidden: { kind: "lock", title: "没有目录读取权限", description: "请联系管理员确认账号与客户读取授权。", action: '<button type="button" class="button" data-action="check-permission" data-testid="check-permission">重新检查</button>' },
      disabled: { kind: "pause", title: "客户目录已停用", description: "目前无法读取目录，请联系管理员。" },
    };
    content.innerHTML = `<section class="global-state" data-state="${state.status}" data-testid="${state.status}">${statePanel(states[state.status])}</section>`;
    return;
  }
  if (state.status === "loading-directory") {
    content.innerHTML = `<section class="global-state" data-testid="loading-directory">${loadingPanel("正在读取客户目录…")}</section>`;
    return;
  }
  content.innerHTML = `<section class="directory-layout" aria-label="客户与优化对象">
    <aside class="customer-panel" aria-label="客户列表">
      <div class="panel-heading"><h2>客户</h2><span class="panel-caption">已获授权</span></div>
      <div class="search-wrap">${searchIcon}<label for="customer-search" class="sr-only">搜索客户名称或 ID</label><input type="search" id="customer-search" class="search-input" data-testid="customer-search" placeholder="搜索客户名称或 ID" value="${escapeHtml(state.customerQuery)}" autocomplete="off"></div>
      <div id="customer-results"></div>
    </aside>
    <section class="subject-panel" aria-label="优化对象" id="subject-content" data-testid="subject-panel"></section>
  </section>`;
  renderCustomers();
  renderSubjects();
}

function renderCustomers() {
  const query = state.customerQuery.trim().toLocaleLowerCase();
  const customers = fixtures.customers.filter((customer) => `${customer.name} ${customer.customer_id}`.toLocaleLowerCase().includes(query));
  const container = document.querySelector("#customer-results");
  if (!customers.length) {
    container.innerHTML = statePanel({ kind: "search", title: "无匹配客户", description: "请调整客户名称或 ID 后重试。", compact: true, action: '<button class="button" type="button" data-action="clear-customers" data-testid="clear-customer-search">清除查询</button>' });
    announce("无匹配客户");
    return;
  }
  container.innerHTML = `<ul class="customer-list" data-testid="customer-list">${customers.map((customer) => `<li><button class="customer-item" type="button" data-customer-id="${customer.customer_id}" data-testid="customer-${customer.customer_id.endsWith("-a") ? "a" : "b"}" aria-current="${state.selectedId === customer.customer_id}">
    <span class="customer-initial" aria-hidden="true">${customer.customer_id.endsWith("-a") ? "A" : "B"}</span><span><span class="customer-name">${escapeHtml(customer.name)}</span><span class="customer-id mono">${customer.customer_id}</span></span><span class="customer-chevron" aria-hidden="true">›</span></button></li>`).join("")}</ul>`;
}

function loadingPanel(label) {
  return `<div class="loading-content" data-testid="loading-state"><div class="loading-label"><span class="spinner" aria-hidden="true"></span><span>${label}</span></div><div aria-hidden="true"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div></div>`;
}

function renderSubjects() {
  const panel = document.querySelector("#subject-content");
  if (!panel) return;
  const customer = fixtures.customers.find((entry) => entry.customer_id === state.selectedId);
  if (!customer) {
    panel.innerHTML = statePanel({ kind: "folder", title: "选择客户查看优化对象", description: "从左侧客户列表中选择一个客户。", initial: true });
    return;
  }
  panel.innerHTML = `<div class="subject-heading"><div><h2 data-testid="selected-customer-name">${escapeHtml(customer.name)}</h2><p class="customer-reference">客户 ID <span class="mono" data-testid="selected-customer-id">${customer.customer_id}</span></p></div><button class="button button-small button-quiet" type="button" data-action="back" data-testid="back-to-customers">返回客户</button></div>`;
  if (state.status === "loading-subjects") {
    panel.insertAdjacentHTML("beforeend", loadingPanel("正在读取优化对象…"));
    return;
  }
  panel.insertAdjacentHTML("beforeend", `<div class="subject-toolbar"><span class="subject-count" id="subject-count"></span><div class="search-wrap">${searchIcon}<label for="subject-search" class="sr-only">搜索对象名称或 ID</label><input type="search" id="subject-search" class="search-input" data-testid="subject-search" placeholder="搜索对象名称或 ID" value="${escapeHtml(state.subjectQuery)}" autocomplete="off"></div></div><div id="subject-results"></div>`);
  renderSubjectResults();
}

function renderSubjectResults() {
  const query = state.subjectQuery.trim().toLocaleLowerCase();
  const all = fixtures.subjects.filter((subject) => subject.customer_id === state.selectedId);
  const subjects = all.filter((subject) => `${subject.name} ${subject.subject_id}`.toLocaleLowerCase().includes(query));
  document.querySelector("#subject-count").textContent = `优化对象 · ${subjects.length} 项`;
  const results = document.querySelector("#subject-results");
  if (!subjects.length) {
    results.innerHTML = statePanel({ kind: "search", title: "无匹配对象", description: query ? "请调整对象名称或 ID 后重试。" : "此客户在当前快照中没有优化对象。", action: query ? '<button class="button" type="button" data-action="clear-subjects" data-testid="clear-subject-search">清除查询</button>' : "" });
    results.setAttribute("data-testid", query ? "no-matching-subjects" : "zero-subjects");
    announce("无匹配对象");
    return;
  }
  results.setAttribute("data-testid", "subject-results");
  results.innerHTML = `<div class="table-scroll"><table data-testid="subjects-table"><caption class="sr-only">${escapeHtml(fixtures.customers.find((customer) => customer.customer_id === state.selectedId).name)}的优化对象</caption><thead><tr><th scope="col">对象名称</th><th scope="col">对象 ID</th><th scope="col">来源分类</th></tr></thead><tbody>${subjects.map((subject) => `<tr data-testid="subject-row"><td>${escapeHtml(subject.name)}</td><td class="mono">${subject.subject_id}</td><td>${subject.source_type ? escapeHtml(subject.source_type) : '<span class="unknown" data-testid="unknown-type">未知</span>'}</td></tr>`).join("")}</tbody></table></div>`;
  announce(`已读取 ${subjects.length} 个优化对象，数据日期 ${fixtures.meta.data_as_of}`);
}

function requestSubjects(customerId, delay = 360) {
  const sequence = ++state.sequence;
  state.selectedId = customerId;
  state.subjectQuery = "";
  state.status = "loading-subjects";
  render();
  announce("正在读取优化对象");
  window.setTimeout(() => {
    if (sequence !== state.sequence || !state.enabled) return;
    state.status = "ready";
    render();
  }, delay);
}

function requestDirectory({ recover = false } = {}) {
  const sequence = ++state.sequence;
  const currentScenario = state.scenario;
  state.status = "loading-directory";
  render();
  announce("正在读取客户目录");
  window.setTimeout(() => {
    if (sequence !== state.sequence || !state.enabled) return;
    if (recover) state.scenario = "normal";
    state.status = currentScenario === "forbidden" ? "forbidden" : "ready";
    render();
    if (recover) showNotice("已重新读取目录。");
    else announce(state.status === "forbidden" ? "仍无目录读取权限" : "客户目录已更新");
  }, 550);
}

function setScenario(scenario) {
  ++state.sequence;
  clearNotice();
  Object.assign(state, { scenario, enabled: scenario !== "disabled", status: "ready", selectedId: null, customerQuery: "", subjectQuery: "" });
  if (["source-error", "forbidden", "disabled"].includes(scenario)) state.status = scenario;
  if (scenario === "zero-subjects") state.selectedId = "synthetic-customer-b";
  if (scenario === "no-results") {
    state.selectedId = "synthetic-customer-a";
    state.subjectQuery = "不匹配的合成查询";
  }
  if (scenario === "loading") {
    requestSubjects("synthetic-customer-a", 2000);
    return;
  }
  render();
  announce(`已切换原型场景：${scenarioSelect.selectedOptions[0].textContent}`);
}

scenarioSelect.addEventListener("change", () => setScenario(scenarioSelect.value));
document.querySelector("#reset-prototype").addEventListener("click", () => setScenario("normal"));
toggleButton.addEventListener("click", () => {
  const enable = !state.enabled;
  setScenario(enable ? "normal" : "disabled");
  showNotice(enable ? "模拟启用成功，可以读取客户目录。" : "模拟停用成功，客户目录已不可读取。");
});
refreshButton.addEventListener("click", () => {
  clearNotice();
  requestDirectory({ recover: state.scenario === "source-error" });
});
content.addEventListener("click", (event) => {
  const customer = event.target.closest("[data-customer-id]");
  if (customer) {
    clearNotice();
    requestSubjects(customer.dataset.customerId);
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "retry") requestDirectory({ recover: true });
  if (action === "check-permission") requestDirectory();
  if (action === "back") {
    ++state.sequence;
    state.selectedId = null;
    state.subjectQuery = "";
    state.status = "ready";
    render();
    document.querySelector("#customer-search").focus();
  }
  if (action === "clear-customers") {
    state.customerQuery = "";
    const input = document.querySelector("#customer-search");
    input.value = "";
    renderCustomers();
    input.focus();
  }
  if (action === "clear-subjects") {
    state.subjectQuery = "";
    const input = document.querySelector("#subject-search");
    input.value = "";
    renderSubjectResults();
    input.focus();
  }
});
content.addEventListener("input", (event) => {
  if (event.target.id === "customer-search") {
    ++state.sequence;
    state.customerQuery = event.target.value;
    state.selectedId = null;
    state.subjectQuery = "";
    state.status = "ready";
    refreshButton.disabled = false;
    content.setAttribute("aria-busy", "false");
    renderCustomers();
    renderSubjects();
  }
  if (event.target.id === "subject-search") {
    state.subjectQuery = event.target.value;
    renderSubjectResults();
  }
});

render();
