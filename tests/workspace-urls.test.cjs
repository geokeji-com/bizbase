// Contract against Frappe v16's workspace parser + shell writer, without a running site.
const assert = require("node:assert/strict");
const test = require("node:test");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const script = readFileSync(path.join(__dirname, "../apps/bizbase_mgmt/bizbase_mgmt/public/workspace-urls.js"), "utf8");

function desk(url, visible = true) {
	const nativeWrites = [];
	const workspace = {name: "sales_board", public: 1};
	const location = new URL(url, "http://desk.test");
	const router = {
		convert_to_standard_route(route) {
			return route[0] === workspace.name && visible ? ["Workspaces", workspace.name] : route;
		},
		write_shell_into_url() { nativeWrites.push(this.current_route); },
	};
	const history = {state: {}, replaceState(state, unused, relative) {
		assert.equal(state, this.state);
		location.href = new URL(relative, location).href;
	}};
	vm.runInNewContext(script, {frappe: {router, workspaces: visible ? {sales_board: workspace} : {},
		boot: {bizbase_workspace_aliases: {"sales-board": "sales_board"}}}, location, history});
	function navigate() {
		router.current_route = router.convert_to_standard_route(location.pathname.replace("/desk/", "").split("/"));
		router.write_shell_into_url();
		return router.current_route;
	}
	return {location, navigate, nativeWrites};
}

for (const spelling of ["sales_board", "sales-board", "sales_board/", "sales-board/"]) {
	test(`card or bookmark ${spelling} and refresh`, () => {
		const page = desk(`/desk/${spelling}?filter=A%2FB#MiXeD`);
		assert.deepEqual(page.navigate(), ["Workspaces", "sales_board"]);
		assert.equal(page.location.href, "http://desk.test/desk/sales-board?filter=A%2FB#MiXeD");
		assert.deepEqual(page.navigate(), ["Workspaces", "sales_board"]);
		assert.equal(page.nativeWrites.length, 0);
	});
}

test("a slug cannot open a workspace the user does not have", () => {
	const page = desk("/desk/sales-board", false);
	assert.deepEqual(page.navigate(), ["sales-board"]);
	assert.equal(page.nativeWrites.length, 1);
});

test("Yishan shell writes hyphens, accepts its old prefix and preserves the binding ID", () => {
	let onChange;
	const router = {
		shell_slug: name => name.toLowerCase().replaceAll(" ", "-"),
		setup_shell_routes() { this.shell_routes = Object.fromEntries(this.shells.map(s => [this.shell_slug(s), s])); },
		on(event, handler) { assert.equal(event, "change"); onChange = handler; },
	};
	const location = new URL("https://desk.test/desk/yishan_id/yishan-id-binding/MiXeD?tab=1#a");
	const history = {replaceState(_state, _unused, url) { location.href = new URL(url, location).href; }};
	vm.runInNewContext(readFileSync(path.join(__dirname, "../apps/yishan_id/yishan_id/public/desk-urls.js"), "utf8"),
		{frappe: {router}, location, history});
	router.shells = ["yishan_id", "Other Module"];
	router.setup_shell_routes();
	assert.equal(router.shell_routes["other-module"], "Other Module");
	assert.equal(router.shell_routes["yishan-id"], "yishan_id");
	router.current_shell = router.shell_routes.yishan_id;
	onChange();
	assert.equal(location.pathname + location.search + location.hash, "/desk/yishan-id/yishan-id-binding/MiXeD?tab=1#a");
	router.shells = ["Other Module"];
	router.setup_shell_routes();
	assert.equal(router.shell_routes.yishan_id, undefined);
});

test("unrelated names, extra segments and case-sensitive document IDs are untouched", () => {
	for (const url of ["private/sales_board", "third_party", "file-share/YDWWBxUtWN", "sales-board/Extra"]){
		const page = desk(`/desk/${url}`);
		page.navigate();
		assert.equal(page.location.pathname, `/desk/${url}`);
		assert.equal(page.nativeWrites.length, 1);
	}
});
