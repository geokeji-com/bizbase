frappe.ui.form.on("Static Share", {
	setup(frm) {
		frm.fields_dict.upload.df.options = {
			make_attachments_public: false,
			allow_toggle_private: false,
			disable_file_browser: true,
			allow_web_link: false,
			allow_take_photo: false,
			allow_google_drive: false,
			restrictions: { allowed_file_types: [".html", ".htm", ".zip"] },
		};
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Copy Share Link"), () =>
			frappe.utils.copy_to_clipboard(new URL(frm.doc.share_url, location.origin).href)
		);
		if (frm.perm[0].write) {
			frm.add_custom_button(__("Upload New Version"), () => frm.fields_dict.upload.on_attach_click());
		}
	},
});
