const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const test = require('node:test');

const frappe = { listview_settings: {}, user_info: id => id === 'alice' ? {fullname: 'A&B'} : {},
	utils: {escape_html: s => s.replaceAll('&', '&amp;')} };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../file_share/doctype/file_share/file_share_list.js'), 'utf8'), {frappe, __: s => s});
const settings = frappe.listview_settings['File Share'];
const defaults = () => [{type:'Subject',df:{fieldname:'title'}},{type:'Tag'},{type:'Field',df:{fieldname:'name'}}];

test('creator appears once by title, including after native column setup', async () => {
	const list = {columns: defaults(), setup_columns() { this.columns = defaults(); }};
	settings.onload(list);
	for (let i=0; i<2; i++) {
		assert.deepEqual(list.columns.map(c => c.df?.fieldname), ['title',undefined,'owner','name']);
		await list.setup_columns();
	}
	list.list_filter = {active_layout_name:'personal'};
	await list.setup_columns();
	assert.equal(list.columns.some(c => c.df?.fieldname === 'owner'), false);
});
test('native owner column is not duplicated; display name is escaped with account fallback', () => {
	const list = {columns:[{type:'Field',df:{fieldname:'owner'}}], setup_columns(){}};
	settings.onload(list);
	assert.equal(list.columns.length, 1);
	assert.equal(list.columns[0].df.label,'创建人');
	assert.equal(settings.formatters.owner('alice'), 'A&amp;B');
	assert.equal(settings.formatters.owner('other@example.com'), 'other@example.com');
	assert.equal(settings.formatters.owner(''), '');
});
