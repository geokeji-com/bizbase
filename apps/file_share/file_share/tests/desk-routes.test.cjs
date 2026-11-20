const { strict: assert } = require("node:assert");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "../public/desk-routes.js"), "utf8");
const legacy = "/desk/file-share-access-log";
const canonical = "/desk/file-share/access-log";

function desk(pathname) {
	const router = { parse: path => path };
	const sidebar_item = { get_route: ({ href }) => href };
	const calls = [];
	vm.runInNewContext(source, {
		frappe: { router, ui: { sidebar_item } },
		window: { location: { pathname, search: "?share=Ac12Xy34Zq", hash: "#top" } },
		history: { replaceState: (_state, _title, url) => calls.push(url) },
	});
	return { router, sidebar_item, calls };
}

test("canonical log list resolves as the native DocType without rewriting", () => {
	const { router, calls } = desk(canonical);
	assert.equal(router.parse(), legacy);
	assert.deepEqual(calls, []);
});
test("bookmarks keep filters, fragment, and case-sensitive record IDs", () => {
	for (const suffix of ["", "/aBc42", "/view/list"]) {
		const { router, calls } = desk(legacy + suffix);
		assert.equal(router.parse(), legacy + suffix);
		assert.deepEqual(calls, [canonical + suffix + "?share=Ac12Xy34Zq#top"]);
		assert.equal(router.parse(canonical + suffix), legacy + suffix);
	}
});
test("share forms, similarly named routes and other apps are untouched", () => {
	for (const original of ["/desk/file-share/Ac12Xy34Zq", canonical + "ging", legacy + "ger", "/desk/access-log"]) {
		const { router, calls } = desk(original);
		assert.equal(router.parse(), original);
		assert.deepEqual(calls, []);
	}
});
test("sidebar emits the canonical link without replacing DocType permission filtering", () => {
	const { sidebar_item } = desk(canonical);
	assert.equal(sidebar_item.get_route({ href: legacy }), canonical);
	assert.equal(sidebar_item.get_route({ href: "/desk/file-share-domain" }), "/desk/file-share-domain");
	assert.equal(sidebar_item.get_route({}), undefined);
	const sidebar = JSON.parse(readFileSync(path.join(__dirname, "../file_share/sidebar/file_share/file_share.json")));
	assert.deepEqual(sidebar.items.map(i => [i.label, i.link_type, i.link_to]), [
		["文件分享", "DocType", "File Share"],
		["访问记录", "DocType", "File Share Access Log"],
		["分享域名", "DocType", "File Share Domain"],
	]);
});
