/* global frappe */
(() => {
  "use strict";

  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
  const validText = (value) => typeof value === "string" && value.length > 0;
  const snapshotKey = (meta) => meta && JSON.stringify([
    meta.source_system, meta.version, meta.data_as_of, meta.mode,
  ]);

  class DirectoryPage {
    constructor(wrapper) {
      this.page = frappe.ui.make_app_page({ parent: wrapper, title: "客户目录", single_column: true });
      this.root = document.createElement("div");
      this.root.className = "bb-directory";
      this.page.body[0].appendChild(this.root);
      this.sequence = 0;
      this.controller = null;
      this.debounce = null;
      this.meta = null;
      this.customers = [];
      this.selected = null;
      this.root.innerHTML = `
        <div class="bb-directory-toolbar"><button type="button" class="btn btn-default btn-sm" data-action="refresh" data-testid="refresh-directory">刷新</button></div>
        <div class="bb-directory-notice" role="status" data-testid="action-notice" hidden></div>
        <div class="bb-directory-meta" data-testid="snapshot-meta" aria-label="数据来源" hidden></div>
        <section class="bb-directory-layout" data-testid="directory-content" aria-label="客户与优化对象">
          <aside class="bb-directory-customers" aria-label="客户列表">
            <div class="bb-directory-panel-heading"><h2>客户</h2><span>已获授权</span></div>
            <div class="bb-directory-search"><label class="bb-directory-sr" for="bb-customer-search">搜索客户名称或 ID</label><input id="bb-customer-search" type="search" class="form-control" data-testid="customer-search" placeholder="搜索客户名称或 ID" autocomplete="off"></div>
            <div data-testid="customer-results"></div>
          </aside>
          <section class="bb-directory-subjects" data-testid="subject-panel" aria-label="优化对象"></section>
        </section>
        <section class="bb-directory-global" data-testid="global-state" hidden></section>
        <p class="bb-directory-footnote">仅展示当前获准读取的客户与优化对象。</p>
        <div class="bb-directory-sr" data-testid="live-status" role="status" aria-live="polite" aria-atomic="true"></div>`;
      this.root.addEventListener("click", (event) => this.handleClick(event));
      this.root.addEventListener("input", (event) => this.handleInput(event));
      this.renderUnselected();
    }

    find(id) { return this.root.querySelector(`[data-testid="${id}"]`); }
    announce(message) { this.find("live-status").textContent = message; }
    invalidate() {
      this.sequence += 1;
      window.clearTimeout(this.debounce);
      if (this.controller) this.controller.abort();
      this.controller = null;
      return this.sequence;
    }
    notice(message = "") {
      this.find("action-notice").textContent = message;
      this.find("action-notice").hidden = !message;
    }
    setBusy(busy) { this.find("directory-content").setAttribute("aria-busy", String(busy)); }
    resetData() {
      this.meta = null;
      this.customers = [];
      this.selected = null;
      this.find("snapshot-meta").innerHTML = "";
      this.find("snapshot-meta").hidden = true;
      this.find("customer-results").innerHTML = "";
      this.find("subject-panel").innerHTML = "";
    }
    showWorkspace() {
      this.find("global-state").hidden = true;
      this.find("global-state").innerHTML = "";
      this.find("directory-content").hidden = false;
    }
    loading(label) {
      return `<div class="bb-directory-loading" data-testid="loading-state"><span class="bb-directory-spinner" aria-hidden="true"></span>${escape(label)}</div>`;
    }
    empty(title, description, action = "", testid = "empty-state") {
      return `<div class="bb-directory-empty" data-testid="${testid}"><h2>${escape(title)}</h2><p>${escape(description)}</p>${action}</div>`;
    }
    renderUnselected() {
      this.find("subject-panel").innerHTML = this.empty("选择客户查看优化对象", "从客户列表中选择一个客户。", "", "choose-customer");
    }
    renderMeta(meta) {
      this.meta = meta;
      this.find("snapshot-meta").innerHTML = `<span class="bb-directory-badge" data-testid="snapshot-mode">历史快照</span>
        <span>数据日期 <strong data-testid="data-as-of">${escape(meta.data_as_of)}</strong></span>
        <span>目录版本 <span class="bb-directory-mono" data-testid="directory-version">${escape(meta.version)}</span></span>
        <span>来源 <span class="bb-directory-mono" data-testid="source-system">${escape(meta.source_system)}</span></span>`;
      this.find("snapshot-meta").hidden = false;
    }
    renderCustomers() {
      const container = this.find("customer-results");
      if (!this.customers.length) {
        container.innerHTML = this.empty("无匹配客户", "请调整客户名称或 ID 后重试。", '<button type="button" class="btn btn-default btn-sm" data-action="clear-customers" data-testid="clear-customer-search">清除查询</button>', "no-matching-customers");
        return;
      }
      container.innerHTML = `<ul class="bb-directory-customer-list" data-testid="customer-list">${this.customers.map((customer) => `<li><button type="button" class="bb-directory-customer" data-customer-id="${escape(customer.customer_id)}" aria-current="${this.selected?.customer_id === customer.customer_id}"><span class="bb-directory-customer-name">${escape(customer.name)}</span><span class="bb-directory-mono bb-directory-customer-id">${escape(customer.customer_id)}</span></button></li>`).join("")}</ul>`;
    }
    renderSubjectShell(customer) {
      this.find("subject-panel").innerHTML = `<div class="bb-directory-subject-heading"><div><h2 data-testid="selected-customer-name">${escape(customer.name)}</h2><p>客户 ID <span class="bb-directory-mono" data-testid="selected-customer-id">${escape(customer.customer_id)}</span></p></div><button class="btn btn-default btn-xs" type="button" data-action="back" data-testid="back-to-customers">返回客户</button></div>
        <div class="bb-directory-subject-toolbar"><span data-testid="subject-count">优化对象</span><div class="bb-directory-search"><label class="bb-directory-sr" for="bb-subject-search">搜索对象名称或 ID</label><input id="bb-subject-search" type="search" class="form-control" data-testid="subject-search" placeholder="搜索对象名称或 ID" autocomplete="off"></div></div><div data-testid="subject-results"></div>`;
    }
    renderSubjects(items, query) {
      this.find("subject-count").textContent = `优化对象 · ${items.length} 项`;
      const results = this.find("subject-results");
      if (!items.length) {
        results.innerHTML = this.empty("无匹配对象", query ? "请调整对象名称或 ID 后重试。" : "此客户在当前快照中没有优化对象。", query ? '<button class="btn btn-default btn-sm" type="button" data-action="clear-subjects" data-testid="clear-subject-search">清除查询</button>' : "", query ? "no-matching-subjects" : "zero-subjects");
      } else {
        results.innerHTML = `<div class="bb-directory-table-scroll"><table class="table" data-testid="subjects-table"><caption class="bb-directory-sr">${escape(this.selected.name)}的优化对象</caption><thead><tr><th scope="col">对象名称</th><th scope="col">对象 ID</th><th scope="col">来源分类</th></tr></thead><tbody>${items.map((item) => `<tr data-testid="subject-row"><td>${escape(item.name)}</td><td class="bb-directory-mono">${escape(item.subject_id)}</td><td>${item.source_type ? escape(item.source_type) : '<span class="bb-directory-unknown" data-testid="unknown-type">未知</span>'}</td></tr>`).join("")}</tbody></table></div>`;
      }
      this.announce(`已读取 ${items.length} 个优化对象`);
    }

    async rpc(method, args, sequence) {
      const controller = new AbortController();
      this.controller = controller;
      const timeout = window.setTimeout(() => controller.abort(), 20000);
      try {
        const params = new URLSearchParams(args);
        const response = await fetch(`/api/method/bizbase.api.directory.${method}?${params}`, {
          method: "GET", credentials: "same-origin", cache: "no-store",
          headers: { Accept: "application/json" }, signal: controller.signal,
        });
        const envelope = await response.json().catch(() => null);
        if (sequence !== this.sequence) return null;
        const payload = envelope?.message;
        if (!response.ok || payload?.error || !payload) {
          throw { status: response.status, code: payload?.error?.code, requestId: payload?.error?.request_id };
        }
        if (!Array.isArray(payload.items) || payload.meta?.mode !== "snapshot" ||
            !["source_system", "version", "data_as_of", "request_id"].every((field) => validText(payload.meta[field]))) {
          throw { status: 503 };
        }
        return payload;
      } finally {
        window.clearTimeout(timeout);
        if (this.controller === controller) this.controller = null;
      }
    }

    async loadCustomers(message = "") {
      const sequence = this.invalidate();
      const query = this.find("customer-search").value.trim();
      this.resetData();
      this.showWorkspace();
      this.notice(message);
      this.renderUnselected();
      this.find("customer-results").innerHTML = this.loading("正在读取客户目录…");
      this.setBusy(true);
      this.announce("正在读取客户目录");
      try {
        const result = await this.rpc("list_customers", query ? { query } : {}, sequence);
        if (!result || sequence !== this.sequence) return;
        if (!result.items.every((item) => validText(item.customer_id) && validText(item.name))) throw { status: 503 };
        this.customers = result.items.map(({ customer_id, name }) => ({ customer_id, name }));
        this.renderMeta(result.meta);
        this.renderCustomers();
        this.setBusy(false);
        this.announce(this.customers.length ? "客户目录已更新，请选择客户" : "无匹配客户");
      } catch (error) {
        if (sequence === this.sequence) this.showError(error);
      }
    }

    async loadSubjects(customer, query = "", preserveInput = false) {
      const sequence = this.invalidate();
      const source = this.meta?.source_system;
      const expectedSnapshot = snapshotKey(this.meta);
      if (!source) return this.loadCustomers();
      this.selected = customer;
      this.notice();
      this.renderCustomers();
      if (!preserveInput) this.renderSubjectShell(customer);
      this.find("subject-results").innerHTML = this.loading("正在读取优化对象…");
      this.find("subject-count").textContent = "优化对象";
      this.setBusy(true);
      this.announce("正在读取优化对象");
      try {
        const result = await this.rpc("list_subjects", { source_system: source, customer_id: customer.customer_id, ...(query ? { query } : {}) }, sequence);
        if (!result || sequence !== this.sequence) return;
        if (snapshotKey(result.meta) !== expectedSnapshot) {
          return this.loadCustomers("目录版本已更新，请重新选择客户。");
        }
        if (result.customer?.customer_id !== customer.customer_id || !validText(result.customer?.name) ||
            !result.items.every((item) => validText(item.subject_id) && validText(item.name) && item.customer_id === customer.customer_id && (item.source_type == null || typeof item.source_type === "string"))) {
          throw { status: 503 };
        }
        this.selected = { customer_id: result.customer.customer_id, name: result.customer.name };
        this.find("selected-customer-name").textContent = this.selected.name;
        this.renderMeta(result.meta);
        this.renderSubjects(result.items, query);
        this.setBusy(false);
      } catch (error) {
        if (sequence === this.sequence) this.showError(error);
      }
    }

    showError(error) {
      this.invalidate();
      this.resetData();
      this.notice();
      this.setBusy(false);
      this.find("directory-content").hidden = true;
      const denied = [401, 403, 404].includes(error?.status);
      const disabled = error?.code === "DIRECTORY_DISABLED";
      const requestFailed = error?.code === "AUDIT_UNAVAILABLE";
      const invalid = error?.status === 400;
      const kind = disabled ? "disabled" : denied ? "forbidden" : invalid ? "invalid-request" : requestFailed ? "request-error" : "source-error";
      const title = disabled ? "客户目录已停用" : denied ? "没有目录读取权限" : invalid ? "无法完成本次查询" : requestFailed ? "暂时无法完成目录请求" : "暂时无法读取目录来源";
      const description = disabled ? "目前无法读取目录，请联系管理员。" : denied ? "请联系管理员确认账号与客户读取授权。" : invalid ? "请清除查询内容后重试。" : "本次读取失败，请重试。";
      const action = `<button type="button" class="btn btn-default btn-sm" data-action="${invalid ? "clear-customers" : "retry"}" data-testid="${denied ? "check-permission" : "retry-source"}">${denied ? "重新检查" : invalid ? "清除查询" : "重试"}</button>`;
      const panel = this.find("global-state");
      panel.innerHTML = `<div data-testid="${kind}" role="alert">${this.empty(title, description, action)}${validText(error?.requestId) ? `<p class="bb-directory-request-id">请求编号：${escape(error.requestId)}</p>` : ""}</div>`;
      panel.hidden = false;
      this.announce(title);
    }

    handleClick(event) {
      const button = event.target.closest("[data-customer-id]");
      if (button) {
        const customer = this.customers.find((item) => item.customer_id === button.dataset.customerId);
        if (customer) this.loadSubjects(customer);
        return;
      }
      const action = event.target.closest("[data-action]")?.dataset.action;
      if (action === "refresh" || action === "retry") this.loadCustomers();
      if (action === "back") {
        this.invalidate();
        this.selected = null;
        this.setBusy(false);
        this.renderCustomers();
        this.renderUnselected();
        this.find("customer-search").focus();
      }
      if (action === "clear-customers") {
        this.find("customer-search").value = "";
        this.loadCustomers();
        this.find("customer-search").focus();
      }
      if (action === "clear-subjects" && this.selected) {
        this.find("subject-search").value = "";
        this.loadSubjects(this.selected, "", true);
        this.find("subject-search").focus();
      }
    }

    handleInput(event) {
      if (event.target === this.find("customer-search")) {
        this.invalidate();
        this.resetData();
        this.notice();
        this.renderUnselected();
        this.find("customer-results").innerHTML = this.loading("正在读取客户目录…");
        this.setBusy(true);
        this.debounce = window.setTimeout(() => this.loadCustomers(), 220);
      }
      if (event.target === this.find("subject-search") && this.selected) {
        this.invalidate();
        const customer = this.selected;
        const query = event.target.value.trim();
        this.find("subject-results").innerHTML = this.loading("正在读取优化对象…");
        this.find("subject-count").textContent = "优化对象";
        this.setBusy(true);
        this.debounce = window.setTimeout(() => this.loadSubjects(customer, query, true), 220);
      }
    }
  }

  frappe.pages["bb-directory"].on_page_load = function (wrapper) {
    wrapper.bb_directory = new DirectoryPage(wrapper);
  };
  frappe.pages["bb-directory"].on_page_show = function (wrapper) {
    wrapper.bb_directory.loadCustomers();
  };
})();
