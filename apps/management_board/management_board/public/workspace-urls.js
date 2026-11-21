// Adapt only registered BizBase public workspaces; keep Frappe's persisted names,
// permission-filtered lookup, private workspaces and document identifiers unchanged.
(() => {
	const router = frappe.router;
	const parse = router.convert_to_standard_route;
	router.convert_to_standard_route = function (route) {
		const slug = route[0];
		const aliases = frappe.boot?.bizbase_workspace_aliases || {};
		const bare = route.length === 1 || (route.length === 2 && route[1] === "");
		if (bare && Object.hasOwn(aliases, slug)) {
			const name = aliases[slug];
			const workspace = frappe.workspaces?.[name];
			if (workspace?.public && workspace.name === name) {
				return parse.call(this, [name]);
			}
		}
		return parse.call(this, route);
	};

	const writeShell = router.write_shell_into_url;
	router.write_shell_into_url = function () {
		const [view, name] = this.current_route || [];
		const slug = view === "Workspaces" && name?.replaceAll("_", "-");
		if (slug && frappe.boot?.bizbase_workspace_aliases?.[slug] === name) {
			const path = location.pathname.replace(/\/$/, "");
			const bookmark = path.match(/^\/desk\/([^/]+)$/)?.[1];
			if (bookmark === name || frappe.boot.bizbase_workspace_aliases[bookmark] === name) {
				if (location.pathname !== `/desk/${slug}`) {
					history.replaceState(history.state, "", `/desk/${slug}${location.search}${location.hash}`);
				}
				return; // Do not prepend the same workspace's legacy underscore shell.
			}
		}
		return writeShell.call(this);
	};
})();
