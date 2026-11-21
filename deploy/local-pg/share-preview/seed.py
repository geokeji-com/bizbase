"""Seed a local-only employee for testing the installed CLI. No real IdP credentials."""
import os
from pathlib import Path

import frappe
from frappe.utils.password import update_password

os.chdir('sites')
frappe.init(site='frontend', sites_path=os.getcwd())
frappe.connect()
try:
    if frappe.conf.host_name != 'http://127.0.0.1:18081':
        raise RuntimeError('unexpected preview origin')
    frappe.set_user('Administrator')
    email = 'share-preview@example.test'
    if not frappe.db.exists('User', email):
        frappe.get_doc(dict(doctype='User', email=email, first_name='本地文件分享体验', send_welcome_email=0,
                            roles=[dict(role='Desk User')])).insert()
        frappe.get_doc(dict(doctype='Employee', name=email, user_id=email, status='Active')).db_insert()
    update_password(email, Path('/run/secrets/preview_employee').read_text().strip())
    if not frappe.db.exists('File Share Domain', '127.0.0.1:18081'):
        frappe.get_doc(dict(doctype='File Share Domain', origin=frappe.conf.host_name, display_name='本机文件分享',
                            status='Enabled')).insert()
    frappe.db.commit()
finally:
    frappe.destroy()
