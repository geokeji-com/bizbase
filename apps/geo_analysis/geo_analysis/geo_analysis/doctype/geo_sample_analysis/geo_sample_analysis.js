frappe.ui.form.on('GEO Sample Analysis', {
    setup(frm) {
        frm.set_query('slot', () => ({filters: {service: frm.doc.service}}));
        frm.set_query('entity_set', () => ({filters: {service: frm.doc.service}}));
    },
    refresh(frm) {
        frm.add_custom_button(__('查看原始回答'), async () => {
            if (!frm.doc.service || !frm.doc.slot) {
                frappe.msgprint(__('请先选择服务和应采记录。'));
                return;
            }
            const saved = !frm.is_new();
            const evidence = (await frappe.call({
                method: saved ? 'geo_analysis.api.read_sample' : 'geo_analysis.api.read_slot',
                args: saved ? {service: frm.doc.service, sample: frm.doc.name} : {service: frm.doc.service, slot: frm.doc.slot},
            })).message;
            const dialog = new frappe.ui.Dialog({title: __('原始回答'), fields: [{fieldtype: 'HTML', fieldname: 'source'}]});
            const area = dialog.fields_dict.source.$wrapper;
            $('<p>').text(evidence.prompt_text).appendTo(area);
            $('<pre>').css('white-space', 'pre-wrap').text(evidence.answer).appendTo(area);
            $('<h5>').text(__('信源')).appendTo(area);
            $('<pre>').css('white-space', 'pre-wrap').text(JSON.stringify(evidence.sources, null, 2)).appendTo(area);
            dialog.show();
        });
    },
});
