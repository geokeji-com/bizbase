frappe.ui.form.on('GEO Monitoring Plan', {
    setup(frm) {
        frm.set_query('capability', () => ({filters: {enabled: 1, operation: 'prompt'}}));
        frm.set_query('service_prompt', 'prompts', () => ({filters: {service: frm.doc.service}}));
    },
    refresh(frm) {
        if (frm.is_new()) return;
        const escaped = (value) => frappe.utils.escape_html(String(value ?? ''));
        const forDate = (title, callback) => frappe.prompt([
            {fieldtype: 'Date', fieldname: 'date', label: '计划日期', reqd: 1, default: frappe.datetime.get_today()}
        ], ({date}) => callback(date), title, title);
        frm.add_custom_button('预览应采', () => forDate('预览应采', async date => {
            const {message} = await frappe.call('geo_service.api.preview', {plan: frm.doc.name, date});
            frappe.msgprint({title: `应采 ${message.length} 条`, message: message.map(r =>
                `<p>${escaped(r.target_name)}：${escaped(r.prompt_text)}<br>${escaped(r.window_start)} 至 ${escaped(r.window_end)}</p>`
            ).join('') || '该日无应采记录'});
        }));
        frm.add_custom_button('生成并派发', () => forDate('生成并派发', async date => {
            const {message} = await frappe.call('geo_service.api.dispatch_slots', {plan: frm.doc.name, date});
            frappe.msgprint(`应采 ${message.length} 条，已关联任务 ${message.filter(r => r.task).length} 条。`);
        }));
        frm.add_custom_button('创建下一版本', async () => {
            await frappe.new_doc('GEO Monitoring Plan', {}, doc => {
                for (const field of ['plan_title','service','capability','parameters_json','time_zone','weekdays']) doc[field] = frm.doc[field];
                doc.replaces_plan = frm.doc.name;
                doc.effective_from = frappe.datetime.add_days(frappe.datetime.get_today(), 1);
                for (const row of frm.doc.prompts) frappe.model.add_child(doc, 'GEO Plan Prompt', 'prompts').service_prompt = row.service_prompt;
                for (const row of frm.doc.windows) Object.assign(frappe.model.add_child(doc, 'GEO Plan Window', 'windows'), {from_time: row.from_time, to_time: row.to_time, samples: row.samples});
            });
        });
    },
    async capability(frm) {
        if (!frm.is_new() || !frm.doc.capability) return;
        const {message} = await frappe.db.get_value('Execution Capability', frm.doc.capability, 'parameter_schema');
        const choices = JSON.parse(message.parameter_schema);
        frm.set_df_property('parameters_json', 'description', frappe.utils.escape_html(JSON.stringify(choices)));
        frm.refresh_field('parameters_json');
        frm.add_custom_button('选择采集参数', () => {
            const entries = Object.entries(choices);
            if (!entries.length) return frm.set_value('parameters_json','{}');
            frappe.prompt(entries.map(([name, values], i) => ({fieldname: `p${i}`, fieldtype:'Select', label: frappe.utils.escape_html(name), options:values.map(v => JSON.stringify(v)).join('\n'), reqd:1})), values => {
                frm.set_value('parameters_json', JSON.stringify(Object.fromEntries(entries.map(([name], i) => [name, JSON.parse(values[`p${i}`])]))));
            }, '平台采集参数');
        });
    }
});
