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
			if (!(await frappe.xcall("static_share.permissions.can_upload_report"))) {
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
			await frm.fields_dict.upload.on_upload_complete(message);
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

	frappe.ui.form.on("Static Share", {
		refresh(frm) {
			const field = frm.fields_dict.upload;
			field.on_attach_click = () => choose(frm);
			field.$input?.text(__("Choose report file"));
			frm.set_df_property("upload", "description", help);
			frm.set_df_property("section_access", "label", __("Share audience"));
			if (frm.attachments) frm.attachments.new_attachment = () => choose(frm);
			if (frm.is_new()) return;
			frm.add_custom_button(__("Copy Share Link"), () =>
				frappe.utils.copy_to_clipboard(new URL(frm.doc.share_url, location.origin).href));
			if (frm.perm[0].write) frm.add_custom_button(__("Upload New Version"), () => choose(frm));
		},
	});
})();
