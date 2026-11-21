"""Read-only review page. Every drilldown re-checks current service membership."""
import frappe
from frappe.utils import getdate

from geo_analysis.api import read_report, read_sample, read_slot
from geo_service.access import require_service
from geo_service.api import coverage

no_cache = 1


def get_context(context):
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw('请先登录以查看获授权的服务。', frappe.PermissionError)
    from geo_service.api import my_services
    context.services = my_services()
    service = frappe.form_dict.get('service')
    if not service:
        return
    require_service(service)
    context.selection = service
    context.day = str(getdate(frappe.form_dict.get('date')))
    context.progress = coverage(service, context.day)
    context.reports = frappe.get_all('GEO Report Revision', filters={'service': service}, fields=['name','from_date','to_date','top3_display'], order_by='creation desc', limit_page_length=50)
    if report := frappe.form_dict.get('report'):
        context.report = read_report(service, report)
    if sample := frappe.form_dict.get('sample'):
        context.evidence = read_sample(service, sample)
    elif slot := frappe.form_dict.get('slot'):
        context.evidence = read_slot(service, slot)
