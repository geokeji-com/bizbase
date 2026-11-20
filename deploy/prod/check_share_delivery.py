"""Read-only before/after invariants for the existing report corpus. Prints only digests/counts."""
import hashlib
import json
import os
import sys
from pathlib import Path

import frappe

SITE = 'bizbase.geokeji.com'
os.chdir('sites')
frappe.init(site=SITE)
frappe.connect()
try:
    h = hashlib.sha256()
    def digest(rows):
        for row in rows:
            h.update(json.dumps(row, ensure_ascii=False, default=str).encode() + b'\n')
        return len(rows)
    shares = frappe.get_all('File Share', fields=['name','title','owner','status','access_level','current_version','access_salt','upload'], order_by='name asc')
    total = digest(shares)
    versions = digest(frappe.get_all('File Share Version', fields=['name','parent','version','entry','source_file'], order_by='name asc'))
    for dt, col in [('File Share User','user'),('File Share Role','role')]:
        digest(frappe.get_all(dt, fields=['parent', col], order_by='name asc'))
    digest(frappe.db.sql('SELECT name, password FROM "__Auth" WHERE doctype=%s AND fieldname=%s ORDER BY name', ('File Share','password')))
    logs = digest(frappe.get_all('File Share Access Log', fields=['name','share','version','result'], order_by='name asc'))
    for p in sorted((Path(SITE)/'private/files/.static_share').rglob('*')):
        if p.is_file():
            h.update(str(p).encode()); h.update(hashlib.sha256(p.read_bytes()).digest())
    if sys.argv[1] == 'after':
        for row in shares:
            doc = frappe.get_doc('File Share', row.name)
            assert doc.share_url == '/file-share/s/' + row.name
            assert len(doc.entries) == 1 and doc.entries[0].domain == SITE and doc.entries[0].enabled
            assert doc.entries[0].access_mode == 'Inherit' and doc.entries[0].version_mode == 'Follow'
        assert frappe.db.exists('File Share Domain', {'name':SITE,'status':'Enabled'})
    print(f'shares={total} versions={versions} logs={logs} sha256={h.hexdigest()}')
finally:
    frappe.destroy()
