frappe.ui.form.on("File Share Domain", {
	onload(frm) { frm._saved_status = frm.doc.status; },
	after_save(frm) { frm._saved_status = frm.doc.status; },
	async before_save(frm) {
		if (frm.is_new() || frm._saved_status !== "Enabled" || frm.doc.status === "Enabled") return;
		const {message: count} = await frm.call("impact_count");
		await new Promise((ok, cancel) => frappe.confirm(
			__("此操作会关闭该域名下所有报告的访问，包括 {0} 个已开启的发布入口。确定保存？", [count]),
			ok, () => cancel(new Error(__("已取消停用域名")))
		));
	},
});
