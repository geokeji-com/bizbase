"""Service demand, dispatch and coverage. A slot is one service's entitlement to one answer."""

from datetime import datetime, timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import getdate, get_system_timezone, now_datetime

from geo_service.access import require_manager, require_service
from geo_service.planning import parse_weekdays, subdivide


def _active(day, start, end):
    return getdate(start) <= day and (not end or day <= getdate(end))


def _preview(plan, day):
    service = frappe.get_doc('GEO Service', plan.service)
    if (service.status == 'Closed' or not _active(day, service.start_date, service.end_date)
            or not _active(day, plan.effective_from, plan.effective_until) or day.isoweekday() not in parse_weekdays(plan.weekdays)):
        return []
    windows = []
    for window in plan.windows:
        windows.extend(subdivide(day, window.from_time, window.to_time, window.samples, plan.time_zone, get_system_timezone()))
    records = []
    for row in plan.prompts:
        prompt = frappe.get_doc('GEO Service Prompt', row.service_prompt)
        if not _active(day, prompt.active_from, prompt.active_until):
            continue
        for a,b in windows:
            records.append({'service': plan.service, 'service_prompt': prompt.name, 'target_name':prompt.target_name,
                            'prompt_text':prompt.prompt_text, 'plan':plan.name, 'sampling_date':day, 'capability':plan.capability,
                            'window_start':a, 'window_end':b, 'sample_index':0})
    return records


@frappe.whitelist()
def preview(plan, date):
    service = frappe.db.get_value('GEO Monitoring Plan', plan, 'service')
    require_service(service)
    return [{k: row[k] for k in ('prompt_text','target_name','capability','window_start','window_end')}
            for row in _preview(frappe.get_doc('GEO Monitoring Plan', plan), getdate(date))]


def _generate(plan, day):
    # Serialize expansion and revision closure per service, independently of task sharing.
    service = frappe.db.get_value('GEO Monitoring Plan', plan, 'service')
    frappe.db.get_value('GEO Service', service, 'name', for_update=True)
    doc = frappe.get_doc('GEO Monitoring Plan', plan)
    slots = []
    for record in _preview(doc, day):
        slot_key = sha256(json.dumps([plan,record['service_prompt'],str(day),str(record['window_start']),str(record['window_end'])]).encode()).hexdigest()
        if not frappe.db.exists('GEO Sampling Slot', slot_key):
            slot = frappe.get_doc({'doctype':'GEO Sampling Slot', **record})
            slot.flags.from_plan = True
            slot.insert(set_name=slot_key, ignore_permissions=True)
        slots.append(slot_key)
    return slots


@frappe.whitelist(methods=['POST'])
def generate_slots(plan, date):
    require_manager()
    return _generate(plan, getdate(date))


def _dispatch(plan_name, day):
    from task_execution.api import ensure_task
    plan = frappe.get_doc('GEO Monitoring Plan', plan_name)
    params = json.loads(plan.parameters_json)
    eligible = {(r['service_prompt'], r['window_start'], r['window_end']) for r in _preview(plan, day)}
    output = []
    for name in frappe.get_all('GEO Sampling Slot', filters={'plan':plan_name,'sampling_date':day}, pluck='name',order_by='window_start, name'):
        slot = frappe.db.get_value('GEO Sampling Slot',name,['task','service_prompt','prompt_text','capability','window_start','window_end','sample_index'],as_dict=True,for_update=True)
        if not slot.task and slot.window_end > now_datetime() and (slot.service_prompt, slot.window_start, slot.window_end) in eligible:
            task = ensure_task(slot.prompt_text,slot.capability,params,slot.window_start,slot.window_end,slot.sample_index)
            frappe.db.set_value('GEO Sampling Slot', name, 'task', task)
            slot.task = task
        output.append({'slot':name,'task':slot.task})
    return output


@frappe.whitelist(methods=['POST'])
def dispatch_slots(plan, date):
    require_manager()
    day = getdate(date)
    _generate(plan, day)
    return _dispatch(plan, day)


def dispatch_due_plans():
    """Create today's and tomorrow's demand ahead of the execution windows."""
    for row in frappe.get_all('GEO Monitoring Plan', fields=['name','time_zone','effective_from','effective_until']):
        today = datetime.now(ZoneInfo(row.time_zone)).date()
        for day in (today,today + timedelta(days=1)):
            if not _active(day,row.effective_from,row.effective_until):
                continue
            try:
                _generate(row.name,day)
                # Persist demand even when no compatible executor can currently dispatch it.
                frappe.db.commit()
                _dispatch(row.name,day)
                frappe.db.commit()
            except Exception:
                frappe.db.rollback()
                frappe.log_error(title='GEO 计划派发失败', message=f'{row.name} / {day}\n{frappe.get_traceback()}')


@frappe.whitelist()
def my_services():
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw('请先登录。', frappe.PermissionError)
    fields = ['name','service_title']
    if 'System Manager' in frappe.get_roles(user):
        return frappe.get_all('GEO Service', fields=fields, order_by='creation desc')
    today = getdate()
    memberships = frappe.get_all('GEO Service Member',filters={'parenttype':'GEO Service','parentfield':'members','user':user},fields=['parent','active_from','active_until'])
    allowed = {m.parent for m in memberships if (not m.active_from or m.active_from <= today) and (not m.active_until or m.active_until >= today)}
    allowed.update(frappe.get_all('GEO Service',filters={'responsible_user':user},pluck='name'))
    return frappe.get_all('GEO Service', filters={'name':['in',list(allowed)]},fields=fields,order_by='creation desc') if allowed else []


@frappe.whitelist()
def coverage(service, date):
    require_service(service)
    rows = frappe.get_all('GEO Sampling Slot', filters={'service':service,'sampling_date':getdate(date)},
                          fields=['name','service_prompt','prompt_text','target_name','capability','window_start','window_end','task'],order_by='window_start, service_prompt')
    tasks = {row.task for row in rows if row.task}
    results = set(frappe.get_all('Execution Result',filters={'task':['in',list(tasks)]},pluck='task')) if tasks else set()
    statuses = dict(frappe.get_all('Execution Task',filters={'name':['in',list(tasks)]},fields=['name','state'],as_list=True)) if tasks else {}
    for row in rows:
        task = row.pop('task', None)
        row['collected'] = task in results
        row['status'] = '已采' if row.collected else ('已过窗' if row.window_end <= now_datetime() else statuses.get(task, '待派发'))
    return {'service':service,'date':getdate(date),'expected':len(rows),'collected':sum(r.collected for r in rows),'slots':rows}
