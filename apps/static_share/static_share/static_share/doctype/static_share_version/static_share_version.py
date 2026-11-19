import frappe
from frappe.model.document import Document


class StaticShareVersion(Document):
	# Parent.save() persists its validated child rows via db_insert/db_update directly.
	# Direct child REST writes must never manufacture or edit version history.
	def validate(self):
		frappe.throw(frappe._("Version history is managed by the server"), frappe.PermissionError)

	def on_trash(self):
		frappe.throw(frappe._("Version history is managed by the server"), frappe.PermissionError)
