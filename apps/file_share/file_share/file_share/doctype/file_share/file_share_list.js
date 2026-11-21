// owner is Frappe's original creator, not the uploader of the current version.
frappe.listview_settings["File Share"] = {
	add_fields: ["owner"],
	onload(list) {
		list.page.add_menu_item(__("安装文件分享助手"), () => window.location.assign("/file-share-setup"));
		const show_creator = () => {
			const existing = list.columns.find((col) => col.df?.fieldname === "owner");
			if (existing) {
				existing.df = { ...existing.df, label: __("创建人") };
				return;
			}
			const layout = list.list_filter?.active_layout_name;
			if (layout && layout !== "default_layout") return;
			// Keep the framework's Subject/Tag columns together and retain status, ID and audience.
			const pos = list.columns.findIndex((col) => col.type === "Tag");
			list.columns.splice(pos < 0 ? 1 : pos + 1, 0, {
				type: "Field", df: { fieldname: "owner", fieldtype: "Data", label: __("创建人") },
			});
		};
		// Frappe sets up columns before onload and rebuilds them on layout changes.
		const setup_columns = list.setup_columns.bind(list);
		list.setup_columns = async (...args) => {
			await setup_columns(...args);
			show_creator();
		};
		show_creator();
	},
	formatters: {
		owner(value) {
			if (!value) return "";
			return frappe.utils.escape_html(frappe.user_info(value)?.fullname || value);
		},
	},
};
