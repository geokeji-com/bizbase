// The installed Module Def stays `yishan_id`; only its Desk URL segment changes.
(() => {
	const router = frappe.router;
	const nativeSlug = router.shell_slug;
	router.shell_slug = function (name) {
		return name === "yishan_id" ? "yishan-id" : nativeSlug.call(this, name);
	};
	const setup = router.setup_shell_routes;
	router.setup_shell_routes = function () {
		setup.call(this);
		if (this.shell_routes["yishan-id"] === "yishan_id") {
			this.shell_routes.yishan_id = "yishan_id"; // saved links and SPA navigation
		}
	};
	router.on("change", () => {
		if (router.current_shell === "yishan_id" && location.pathname.startsWith("/desk/yishan_id/")) {
			history.replaceState(history.state, "", location.pathname.replace("/desk/yishan_id/", "/desk/yishan-id/")
				+ location.search + location.hash);
		}
	});
})();
