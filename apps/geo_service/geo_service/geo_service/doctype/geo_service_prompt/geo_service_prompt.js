frappe.ui.form.on('GEO Service Prompt', {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button('换词', () => frappe.new_doc('GEO Service Prompt', {
            service: frm.doc.service, target_name: frm.doc.target_name, replaces: frm.doc.name,
            confirmed_by: frappe.session.user, active_from: frappe.datetime.add_days(frappe.datetime.get_today(), 1)
        }));
    }
});
