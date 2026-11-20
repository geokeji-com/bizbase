(() => {
	const help = __("Upload an HTML file or ZIP. The source stays private. Choose who can open the report under Share audience.");
	const denied = __("To upload a report, sign in with your company Yishan ID or ask an administrator to link your Desk account to an active employee.");

	async function upload(frm, file) {
		if (!file || frm.__uploading_report) return;
		if (!/\.(html?|zip)$/i.test(file.name)) {
			frappe.msgprint(__("Choose an HTML or ZIP file."));
			return;
		}
		frm.__uploading_report = true;
		try {
			if (!(await frappe.xcall("file_share.permissions.can_upload_report"))) {
				frappe.msgprint(denied);
				return;
			}
			const data = new FormData();
			data.append("file", file);
			data.append("is_private", "1");
			data.append("doctype", frm.doctype);
			data.append("docname", frm.doc.name);
			data.append("fieldname", "upload");
			const response = await fetch("/api/method/upload_file", {
				method: "POST", body: data, headers: { "X-Frappe-CSRF-Token": frappe.csrf_token },
			});
			if (!response.ok) {
				frappe.msgprint(response.status === 403 ? __("Upload denied. Check your employee sign-in and permission to edit this share.") :
					response.status === 413 ? __("This file exceeds the site upload limit.") : __("Upload failed. Check the file size and type, then try again."));
				return;
			}
			const { message } = await response.json();
			// Attaching must not auto-save the form: the publisher chooses draft vs publish.
			await frm.set_value("upload", message.file_url);
		} catch (error) {
			frappe.msgprint(__("Could not finish attaching the report. Refresh the form and try again."));
		} finally {
			frm.__uploading_report = false;
		}
	}

	function choose(frm) {
		const input = document.createElement("input");
		input.type = "file";
		input.accept = ".html,.htm,.zip";
		input.onchange = () => upload(frm, input.files[0]);
		input.click();
	}

	const policyLabels = {Internal: "内部员工", Specified: "指定人员或角色", Password: "密码访问", Public: "公开：任何持链接者可看"};
	const active = frm => (frm.doc.entries || []).filter(r => r.enabled && frm._domains?.some(d => d.name === r.domain));
	const state = doc => JSON.stringify([doc.access_level, doc.password, (doc.allowed_users || []).map(r => r.user).sort(), (doc.allowed_roles || []).map(r => r.role).sort()]);
	function remember(frm) {
		frm._published = {version: frm.doc.current_version || 0, policy: state(frm.doc), upload: frm.doc.upload};
	}
	function newEntry(frm, domain) {
		frm.add_child("entries", {domain, enabled: 1, access_mode: "Inherit", version_mode: "Follow"});
		frm.refresh_field("entries"); frm.dirty(); renderEntries(frm);
	}
	function renderEntries(frm) {
		const root = frm.fields_dict.entry_links.$wrapper.empty();
		const saved = !frm.is_new() && !frm.is_dirty();
		for (const row of frm.doc.entries || []) {
			const d = frm._domains?.find(v => row.domain === v.name);
			const effective = row.access_mode === "Inherit" ? frm.doc.access_level : row.access_mode;
			const version = row.version_mode === "Pinned" ? row.pinned_version : frm.doc.current_version;
			const open = d && row.enabled && frm.doc.status === "Active";
			const line = $("<div class='my-2'>").appendTo(root);
			$("<strong>").text((d?.display_name || row.domain) + " · " + row.domain).appendTo(line);
			$("<span>").text(`　${open ? (version ? "已开启" : "待发布") : "未开放"} · ${policyLabels[effective] || "—"} · ${version ? "V" + version : "无发布版"}`).appendTo(line);
			if (open && saved) {
				const url = d.origin + frm.doc.share_url;
				if (version) {
					$("<small class='mx-2'>").text(url).appendTo(line);
					$("<button type='button' class='btn btn-xs btn-default'>复制链接</button>").appendTo(line).on("click", () => frappe.utils.copy_to_clipboard(url));
				}
				if (frappe.session.user === frm.doc.owner && frm.doc.versions?.length) {
					$("<button type='button' class='btn btn-xs btn-default ml-2'>预览版本</button>").appendTo(line).on("click", () => {
						const versions = frm.doc.versions.map(v => String(v.version)).reverse();
						frappe.prompt([{fieldname:"version", label:"作者预览版本", fieldtype:"Select", options:versions.join("\n"), default:versions[0], reqd:1}],
							v => window.open(url + "?v=" + encodeURIComponent(v.version), "_blank", "noopener"), "预览报告", "打开预览");
					});
				}
			}
		}
		if (frm.is_dirty()) $("<small>").text("保存后可复制链接或预览版本。").appendTo(root);
	}
	function addDomain(frm) {
		const used = new Set((frm.doc.entries || []).map(r => r.domain));
		const domains = (frm._domains || []).filter(d => !used.has(d.name));
		if (!domains.length) return frappe.msgprint("没有可添加的已启用域名，请联系管理员。");
		frappe.prompt([{fieldname:"domain", label:"发布域名", fieldtype:"Select", reqd:1,
			options:domains.map(d => ({label:`${d.display_name} · ${d.name}`, value:d.name}))}],
			v => newEntry(frm, v.domain), "添加发布域名", "添加");
	}

	frappe.ui.form.on("File Share", {
		onload(frm) { remember(frm); },
		after_save(frm) { remember(frm); },
		async before_save(frm) {
			const prior = frm._published;
			if (!prior) return;
			const follows = active(frm).filter(r => r.version_mode === "Follow").map(r => r.domain);
			const pinned = active(frm).filter(r => r.version_mode === "Pinned").map(r => r.domain);
			const inherits = active(frm).filter(r => r.access_mode === "Inherit").map(r => r.domain);
			const lines = [];
			if (prior.version !== (frm.doc.current_version || 0) || (frm.doc.publish_upload && prior.upload !== frm.doc.upload)) {
				lines.push("切换当前发布版，跟随更新：" + (follows.join("、") || "无"), "保持固定版本：" + (pinned.join("、") || "无"));
			}
			if (!frm.is_new() && prior.policy !== state(frm.doc) && inherits.length) lines.push("默认查看权限变更影响：" + inherits.join("、"));
			if (lines.length) await new Promise((ok, cancel) => frappe.confirm(lines.map(s => frappe.utils.escape_html(s)).join("<br>"), ok, () => cancel(new Error("已取消保存"))));
		},
		access_level: renderEntries, current_version: renderEntries, status: renderEntries,
		async refresh(frm) {
			const field = frm.fields_dict.upload;
			field.on_attach_click = () => choose(frm);
			field.$input?.text(__("Choose report file"));
			frm.set_df_property("upload", "description", help);
			frm.set_df_property("section_access", "label", __("Share audience"));
			if (frm.attachments) frm.attachments.new_attachment = () => choose(frm);
			frm.set_df_property("entries", "cannot_add_rows", 1);
			frm._domains = await frappe.xcall("file_share.publication.available_domains");
			if (frm.is_new() && !frm._auto_domain && frm._domains.length === 1 && !(frm.doc.entries || []).length) {
				frm._auto_domain = true;
				newEntry(frm, frm._domains[0].name);
				await frm.set_value("publish_upload", 1);
			}
			if (frm.perm[0].write || frm.is_new()) frm.add_custom_button("添加发布域名", () => addDomain(frm));
			if (!frm.is_new() && frm.perm[0].write) frm.add_custom_button(__("Upload New Version"), () => choose(frm));
			renderEntries(frm);
		},
	});
	frappe.ui.form.on("File Share Entry", {enabled: renderEntries, access_mode: renderEntries, version_mode: renderEntries, pinned_version: renderEntries, entries_remove: renderEntries});
})();
