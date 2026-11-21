"""服务访问范围。范围只来自有效的服务成员行，不看组织层级、客户负责人和单据所有人。"""

import frappe
from frappe.tests import IntegrationTestCase

from geo_service.permissions import (
	assert_service_access,
	contracts_visible_to,
	customers_visible_to,
	is_service_owner,
	services_of,
)


class AccessTests(IntegrationTestCase):
	def test_scope_comes_only_from_current_membership(self):
		owner = self.make_user("GEO Operations")
		outsider = self.make_user("GEO Operations")
		service = self.make_service(owner, "Owner")

		self.assertEqual(services_of(owner), {service})
		self.assertEqual(services_of(outsider), set())
		self.assertTrue(is_service_owner(owner, service))
		assert_service_access(owner, service, "read")
		with self.assertRaises(frappe.PermissionError):
			assert_service_access(outsider, service, "read")

	def test_expired_membership_loses_access(self):
		user = self.make_user("GEO Operations")
		service = self.make_service(user, "Operations", to_date=self.yesterday())

		self.assertNotIn(service, services_of(user))
		with self.assertRaises(frappe.PermissionError):
			assert_service_access(user, service, "read")

	def test_sales_membership_is_read_only_even_for_an_operator(self):
		user = self.make_user("GEO Operations")
		service = self.make_service(user, "Sales")

		assert_service_access(user, service, "read")
		with self.assertRaises(frappe.PermissionError):
			assert_service_access(user, service, "write")

	def test_owner_actions_need_an_owner_row(self):
		operator = self.make_user("GEO Operations")
		admin = self.make_user("GEO Admin")
		service = self.make_service(operator, "Operations")

		with self.assertRaises(frappe.PermissionError):
			assert_service_access(operator, service, "owner")
		assert_service_access(admin, service, "owner")

	def test_unreferenced_records_stay_with_their_creator(self):
		sales = self.make_user("GEO Sales")
		other = self.make_user("GEO Sales")
		customer = self.make_customer(sales)

		self.assertIn(customer, customers_visible_to(sales))
		self.assertNotIn(customer, customers_visible_to(other))

	def test_a_service_member_sees_its_customer_and_contract(self):
		sales = self.make_user("GEO Sales")
		operator = self.make_user("GEO Operations")
		customer = self.make_customer(sales)
		contract = self.make_contract(sales, customer)
		self.make_service(operator, "Operations", customer=customer, contract=contract)

		self.assertIn(customer, customers_visible_to(operator))
		self.assertIn(contract, contracts_visible_to(operator))
		self.assertIn(customer, customers_visible_to(sales))

	def make_user(self, role):
		email = f"geo-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "roles": [{"role": role}],
		}).insert(ignore_permissions=True)
		return user.name

	def make_customer(self, owner):
		customer = frappe.get_doc({
			"doctype": "Customer", "customer_name": f"客户-{frappe.generate_hash(length=6)}",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
			"territory": frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
		})
		customer.owner = owner
		return customer.insert(ignore_permissions=True).name

	def make_contract(self, owner, customer):
		contract = frappe.get_doc({
			"doctype": "Contract", "party_type": "Customer", "party_name": customer,
			"start_date": "2026-11-01", "end_date": "2027-10-31",
		})
		contract.owner = owner
		return contract.insert(ignore_permissions=True).name

	def make_service(self, user, member_role, *, to_date=None, customer=None, contract=None):
		service = frappe.get_doc({
			"doctype": "GEO Service",
			"service_name": f"服务-{frappe.generate_hash(length=6)}",
			"served_customer": customer or self.make_customer(user),
			"start_date": "2026-11-01",
			"members": [{
				"user": user, "member_role": member_role,
				"from_date": "2026-11-01", "to_date": to_date,
			}],
		})
		if contract:
			service.append("contracts", {"contract": contract, "valid_from": "2026-11-01"})
		return service.insert(ignore_permissions=True).name

	def yesterday(self):
		from frappe.utils import add_days, today
		return add_days(today(), -1)
