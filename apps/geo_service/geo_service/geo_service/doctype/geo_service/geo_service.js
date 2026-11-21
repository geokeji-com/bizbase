frappe.ui.form.on('GEO Service', {
    setup(frm) {
        frm.set_query('contract', () => ({filters: {party_type: 'Customer', party_name: frm.doc.customer}}));
    },
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button('添加问句', () => frappe.new_doc('GEO Service Prompt', {service:frm.doc.name, active_from:frappe.datetime.get_today()}));
        frm.add_custom_button('新建监测计划', () => frappe.new_doc('GEO Monitoring Plan', {service:frm.doc.name, effective_from:frappe.datetime.get_today()}));
        frm.add_custom_button('采集进度', () => frappe.prompt([
            {fieldname:'date',fieldtype:'Date',label:'计划日期',reqd:1,default:frappe.datetime.get_today()}
        ],async ({date}) => {
            const {message} = await frappe.call('geo_service.api.coverage',{service:frm.doc.name,date});
            const esc = value => frappe.utils.escape_html(String(value ?? ''));
            frappe.msgprint({title:`实采 ${message.collected} / 应采 ${message.expected}`, message:message.slots.map(row =>
                `<p>${esc(row.prompt_text)} · ${esc(row.capability)} · ${esc(row.status)}<br>${esc(row.window_start)} 至 ${esc(row.window_end)}</p>`
            ).join('') || '该日尚无应采记录。'});
        },'查看服务采集进度'));
    }
});
