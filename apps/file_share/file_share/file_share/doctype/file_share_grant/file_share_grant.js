frappe.ui.form.on("File Share Grant", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.revoked_at) return;
		frm.add_custom_button(__("禁用此终端"), () => {
			frappe.confirm(__("禁用后，这份授权签发的终端凭证将立即失效。继续吗？"), async () => {
				await frappe.call({method: "file_share.cli_auth.disable_grant", args: {name: frm.doc.name}, freeze: true});
				await frm.reload_doc();
				frappe.show_alert({message: __("已禁用此终端授权"), indicator: "green"});
			});
		});
	}
});
