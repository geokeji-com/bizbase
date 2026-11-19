// Only a functional page name crosses the sandbox boundary. No analytics code runs here.
(() => {
	"use strict";
	if (window !== window.top || location.origin !== "https://bizbase.geokeji.com") return;
	const installed = Symbol.for("bizbase.usage.navigation");
	if (window[installed]) return;
	window[installed] = true;

	const has = (obj, key) => !!obj && Object.prototype.hasOwnProperty.call(obj, key);
	const words = (list) => new Set(list.split(" "));
	const listViews = words("list report tree calendar kanban gantt dashboard image inbox map");
	const webPages = words("404 error about attribution contact me message portal printview printpreview qrcode third_party_apps confirm_workflow_action modified_doc_alert banking support book_appointment jobs roster crm hrms payment_setup_certification boms timesheets project tasks issues newsletters");
	const webRecords = words("orders invoices supplier-quotations purchase-orders purchase-invoices quotations shipments rfq addresses material-requests");
	const loginTabs = new Map([["#forgot", "forgot-password"], ["#signup", "signup"], ["#login-with-email-link", "email-link"], ["#login_with_email_link", "email-link"]]);

	// Require BOTH the runtime registry and the package's reviewed feature vocabulary.
	// A custom schema/report/workspace named after a person must not become a URL either.
	function named(view, registeredName) {
		const prefix = "desk/" + view + "/";
		if (typeof registeredName === "string" && /^[a-z0-9]+(?:[ _-]+[a-z0-9]+)*$/i.test(registeredName)) {
			const slug = registeredName.toLowerCase().replace(/[ _-]+/g, "-");
			if (slug.length <= 80 && window.bizbaseUsageFeatures?.has("/_usage/" + prefix + slug)) {
				return prefix + slug;
			}
		}
		return prefix + "other";
	}

	function deskFeature(f, route) {
		const [kind, name, mode] = route;
		if (!kind) return "desk/home";
		if (kind === "Workspaces") {
			if (name === "private") return "desk/workspace/private";
			const ws = f.boot?.allowed_workspaces?.find((w) => w.name === name);
			return named("workspace", ws?.public && !ws.for_user ? ws.name : null);
		}
		if (kind === "query-report") return named("report", has(f.boot?.allowed_reports, name) ? name : null);
		if (["List", "Form", "Tree", "Report", "Print", "Dashboard"].includes(kind)) {
			const dt = f.boot?.user?.can_read?.includes(name) ? name : null;
			if (dt === "Static Share" || dt === "Yishan ID Binding") {
				if (kind === "List" || kind === "Form") {
					return (dt === "Static Share" ? "file-share/" : "yishan-id/") + kind.toLowerCase();
				}
			}
			const listView = typeof mode === "string" ? mode.toLowerCase() : "list";
			return named(kind === "List" && listViews.has(listView) ? listView : kind.toLowerCase(), dt);
		}
		return named("page", has(f.boot?.page_info, kind) || has(f.standard_pages, kind) ? kind : null);
	}

	function websiteFeature(path) {
		if (path === "/") return "website/home";
		if (path === "/login") return "auth/" + (loginTabs.get(location.hash) || "login");
		if (path === "/update-password") return "auth/reset-password";
		if (path === "/complete_signup") return "auth/signup";
		if (path === "/logout") return "auth/logout";
		if (path === "/yishan-id/login") return "yishan-id/login";
		if (path === "/yishan-id") return "yishan-id/list";
		if (path === "/file-share") return "file-share/list";
		// These standalone templates already contain a server-rendered counter.
		if (["/banking", "/printview", "/printpreview"].includes(path)) return null;
		// Share shells own their result-specific counter; never instrument uploaded assets.
		if (/^\/(?:file-share|s|_usage|api|assets|files|private)(?:\/|$)/.test(path)) return null;
		if (path === "/book_appointment/verify") return "website/book-appointment-verify";
		const [, section, ...rest] = path.split("/");
		if (webRecords.has(section)) return "website/" + section + (rest.length ? "-detail" : "");
		if (webPages.has(section) && (!rest.length || ["crm", "hrms", "banking"].includes(section))) {
			return "website/" + section.replace(/_/g, "-");
		}
		return "website/other";
	}

	let lastNavigation, frame;
	function visit(feature, localKey) {
		if (lastNavigation === localKey || !document.body) return;
		lastNavigation = localKey; // Volatile equality only. Never assign this value to the DOM or send/store it.
		frame?.remove();
		frame = null;
		if (!feature || new URL(document.baseURI).origin !== location.origin) return;
		frame = document.createElement("iframe");
		frame.hidden = true;
		frame.inert = true;
		frame.tabIndex = -1;
		frame.setAttribute("aria-hidden", "true");
		frame.setAttribute("sandbox", "allow-scripts");
		frame.setAttribute("referrerpolicy", "no-referrer");
		frame.setAttribute("credentialless", ""); // Additional isolation where supported; sandbox is unconditional.
		frame.src = "/_usage/" + feature;
		document.body.appendChild(frame);
	}

	function start() {
		if (/^\/desk(?:\/|$)/.test(location.pathname)) {
			// v16 route() awaits parse(), writes the canonical shell URL, renders, then emits change.
			// pushState, replaceState and popstate are inputs to that process, not extra visits.
			const f = window.frappe, router = f?.router;
			if (!router?.on) return;
			const onRoute = () => {
				const route = router.current_route;
				if (Array.isArray(route)) visit(deskFeature(f, route), JSON.stringify(route));
			};
			router.on("change", onRoute);
			onRoute(); // Also handle inclusion after the first route has already resolved.
			window.addEventListener("pageshow", (e) => { if (e.persisted) { lastNavigation = undefined; onRoute(); } });
		} else {
			const onPage = () => {
				const path = location.pathname.replace(/\/+$/, "") || "/";
				const feature = websiteFeature(path);
				visit(feature, JSON.stringify([path, feature]));
			};
			onPage();
			window.addEventListener("hashchange", onPage);
			window.addEventListener("popstate", onPage);
			window.navigation?.addEventListener("currententrychange", onPage);
			window.addEventListener("pageshow", (e) => { if (e.persisted) { lastNavigation = undefined; onPage(); } });
		}
	}
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
	else start();
})();
