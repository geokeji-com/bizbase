"""Acceptance test on a disposable site; never run against an existing site."""
import html
import os
import re
from contextlib import contextmanager

import frappe
from frappe.app import application
from frappe.utils.file_manager import save_file
from werkzeug.test import Client

os.chdir('sites')
SITE = 'share-qa.test'
COMPANY, A, B = 'company.example', 'channel-a.example', 'channel-b.example'


@contextmanager
def admin():
    frappe.init(site=SITE, sites_path=os.getcwd())
    frappe.connect()
    frappe.set_user('Administrator')
    try:
        yield
        frappe.db.commit()
    finally:
        frappe.destroy()


with admin():
    # Test fixture for the Employee binding. Avoid needing a real company or HR onboarding.
    frappe.get_doc(dict(doctype='Employee', name='QA-EMP', user_id='Administrator', status='Active')).db_insert()
    for host in (COMPANY, A, B):
        if not frappe.db.exists('File Share Domain', host):
            frappe.get_doc(dict(doctype='File Share Domain', origin='https://' + host,
                                display_name=host, status='Enabled')).insert()
    def upload(v):
        return save_file(f'qa-v{v}.html', f'<p>report V{v}</p>'.encode(), None, None, is_private=1).file_url
    report = frappe.get_doc(dict(doctype='File Share', title='交付验收', upload=upload(1),
        publish_upload=1, status='Active', access_level='Public', entries=[dict(domain=COMPANY, enabled=1,
        access_mode='Inherit', version_mode='Follow')])).insert()
    # Recreate the pre-upgrade shape using synthetic data, then run the real PG patch twice.
    from file_share.migrate_publication import execute as migrate_publication
    old_name, original_salt = report.name, report.access_salt
    frappe.db.delete('File Share Entry', {'parent': old_name})
    frappe.db.set_value('File Share', old_name, 'share_url', '/file-share/' + old_name)
    log = frappe.get_doc(dict(doctype='File Share Access Log', share=old_name, share_owner=report.owner,
                              version=1, result='Viewed')).insert(ignore_permissions=True)
    migrate_publication()
    migrate_publication()
    report.reload()
    assert len(report.entries) == 1 and report.entries[0].domain == COMPANY
    assert report.entries[0].legacy_domain_epoch and report.access_salt == original_salt
    assert frappe.db.get_value('File Share Access Log', log.name, 'title_snapshot') == report.title
    sidebar = frappe.get_doc('Sidebar', 'File Share')
    assert [item.link_to for item in sidebar.items] == ['File Share', 'File Share Access Log', 'File Share Grant', 'File Share Domain']
    for version in (2, 3, 4):
        report.reload()
        report.upload, report.publish_upload = upload(version), int(version < 4)
        report.save()
    assert report.current_version == 3, 'draft was published without confirmation'
    report.reload()
    report.current_version = 4
    report.append('entries', dict(domain=A, enabled=1, access_mode='Password', password='fixture-password',
                                  version_mode='Pinned', pinned_version=2))
    report.save()
    name = report.name
    base = '/file-share/s/' + name
    assert report.share_url == base

client = Client(application)


def request(host, path, code=200, password=None):
    r = client.open(path, base_url='https://' + host, headers={'X-Frappe-Site-Name': SITE},
                    method='GET' if password is None else 'POST',
                    data={} if password is None else {'password': password})
    assert r.status_code == code, (host, path.partition('/c/')[0], r.status_code, code, r.get_data(as_text=True)[:200])
    return r.get_data(as_text=True)


def asset(host, path, v):
    page = request(host, path)
    found = re.search(r'<iframe src="([^"]+)"', page)
    assert found, (host, page[:100])
    src = html.unescape(found[1])
    assert f'report V{v}' in request(host, src)
    return src


current = asset(COMPANY, base, 4)
for alias in ('/file-share/', '/s/'):
    asset(COMPANY, alias + name, 4)
request(B, base, 404)
request(B, current, 404)
request(A, base, 401, 'incorrect')
request(A, base, 303, 'fixture-password')
old = asset(A, base + '?v=4', 2)
with admin():
    doc = frappe.get_doc('File Share', name)
    doc.entries[1].pinned_version = 4
    doc.save()
request(A, old, 403)
recent = asset(A, base, 4)
with admin():
    doc = frappe.get_doc('File Share', name)
    doc.entries[1].enabled = 0
    doc.save()
    assert frappe.db.exists('File Share Access Log', dict(share=name, access_domain=A,
        title_snapshot='交付验收', version=2, result='Viewed'))
request(A, recent, 404)
request(A, '/s/' + name, 404)
asset(COMPANY, base, 4)
print('PASS PostgreSQL: real publish, draft, passwords, titles, host isolation, pinned delivery, old links and revocation')
