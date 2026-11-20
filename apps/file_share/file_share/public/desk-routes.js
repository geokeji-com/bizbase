// The File Share module and DocType share a slug. Frappe v16 intentionally reads
// /desk/file-share/<name> as a form, so reserve only the access-log segment.
// Keep real DocType sidebar items: Desk filters those against each user's permissions.
(() => {
	const canonical = "/desk/file-share/access-log";
	const legacy = "/desk/file-share-access-log";
	const under = (path, base) => path === base || path?.startsWith(base + "/");
	const router = frappe.router;
	const parse = router.parse;
	router.parse = function (path) {
		const current = path || window.location.pathname;
		if (!path && under(current, legacy)) {
			history.replaceState(history.state, "", canonical + current.slice(legacy.length)
				+ window.location.search + window.location.hash);
		}
		return parse.call(this, under(current, canonical) ? legacy + current.slice(canonical.length) : current);
	};

	const sidebar = frappe.ui.sidebar_item;
	const getRoute = sidebar.get_route;
	sidebar.get_route = function (...args) {
		const route = getRoute.apply(this, args);
		return route === legacy ? canonical : route;
	};
})();
