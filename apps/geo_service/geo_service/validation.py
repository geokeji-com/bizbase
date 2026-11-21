from datetime import timedelta
from hashlib import sha256
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe.utils import getdate, get_system_timezone

from geo_service.planning import clock, parse_weekdays, subdivide


def prompt(doc, method=None):
    immutable(doc, ['prompt_text'])
    if doc.name != sha256(doc.prompt_text.encode()).hexdigest() or doc.prompt_text != doc.prompt_text.strip():
        frappe.throw('全局问句必须通过服务问句登记。')


def slot(doc, method=None):
    if not doc.flags.from_plan:
        frappe.throw('应采记录由监测计划生成，不支持手工编辑。')


def date_range(start, end):
    if start and end and getdate(end) < getdate(start):
        frappe.throw('结束日期不能早于开始日期。')


def unique(values, label):
    if len(values) != len(set(values)):
        frappe.throw(f'{label}不能重复。')


def immutable(doc, fields):
    if not doc.is_new() and any(doc.has_value_changed(field) for field in fields):
        frappe.throw('已生效的记录不能改写。请新增记录或计划版本。')


def service(doc, method=None):
    immutable(doc, ['customer', 'contract', 'served_organization', 'start_date'])
    contract = frappe.db.get_value('Contract', doc.contract, ['party_type', 'party_name'], as_dict=True)
    if not contract or (contract.party_type, contract.party_name) != ('Customer', doc.customer):
        frappe.throw('合同的签约方必须为所选客户。')
    date_range(doc.start_date, doc.end_date)
    names = [row.target_name for row in doc.targets]
    if not names:
        frappe.throw('至少需要一个优化标的。')
    unique(names, '标的'); unique([row.user for row in doc.members], '成员')
    if not doc.is_new():
        used = frappe.get_all('GEO Service Prompt', filters={'service': doc.name}, pluck='target_name')
        if not set(used) <= set(names):
            frappe.throw('不能删除或改名已有服务问句引用的标的。')
    for member in doc.members:
        date_range(member.active_from, member.active_until)
    for rule in doc.assessment_rules:
        if rule.target_name not in names or not 0 <= rule.threshold <= 100:
            frappe.throw('考核条件必须引用本服务标的，阈值在 0 到 100 之间。')


def lock_service(name):
    if not frappe.db.get_value('GEO Service', name, for_update=True):
        frappe.throw('服务不存在。')


def _overlap(a, b, c, d):
    return (not b or getdate(c) <= getdate(b)) and (not d or getdate(a) <= getdate(d))


def _close_previous(doctype, old_name, service_name, day, start_field, end_field, **filters):
    old = frappe.get_doc(doctype, old_name)
    day = getdate(day)
    if old.service != service_name or getdate(old.get(start_field)) >= day or any(old.get(k) != v for k,v in filters.items()):
        frappe.throw('只能替换同一服务中的较早版本。')
    if old.get(end_field) and getdate(old.get(end_field)) < day - timedelta(days=1):
        frappe.throw('旧版本已经结束。')
    link = 'plan' if doctype == 'GEO Monitoring Plan' else 'service_prompt'
    if frappe.db.exists('GEO Sampling Slot', {link: old_name, 'sampling_date': ['>=', day]}):
        frappe.throw('生效日至少要晚于旧版本已生成的应采记录。')
    frappe.db.set_value(doctype, old_name, end_field, day - timedelta(days=1))
    return old


def service_prompt(doc, method=None):
    lock_service(doc.service)
    immutable(doc, ['service', 'target_name', 'prompt_text', 'prompt', 'active_from', 'replaces', 'change_reason', 'confirmed_by'])
    date_range(doc.active_from, doc.active_until)
    if not frappe.db.exists('GEO Service Target', {'parent':doc.service, 'parenttype':'GEO Service', 'target_name':doc.target_name}):
        frappe.throw('请选择本服务的优化标的。')
    doc.prompt_text = (doc.prompt_text or '').strip()
    if not doc.prompt_text or len(doc.prompt_text) > 8000:
        frappe.throw('问句长度必须在 1 至 8000 个字符之间。')
    key = sha256(doc.prompt_text.encode()).hexdigest()
    if not frappe.db.exists('GEO Prompt', key):
        frappe.get_doc({'doctype':'GEO Prompt','prompt_text':doc.prompt_text}).insert(set_name=key, ignore_permissions=True, ignore_if_duplicate=True)
    if frappe.db.get_value('GEO Prompt', key, 'prompt_text') != doc.prompt_text:
        frappe.throw('问句标识冲突。')
    doc.prompt = key
    if doc.is_new() and doc.replaces:
        if not doc.change_reason or not doc.confirmed_by:
            frappe.throw('换词需要记录确认人和依据。')
        previous = _close_previous(doc.doctype, doc.replaces, doc.service, doc.active_from, 'active_from', 'active_until', target_name=doc.target_name)
        if previous.prompt == key:
            frappe.throw('新旧问句相同。')
    if not doc.is_new() and doc.active_until and frappe.db.exists('GEO Sampling Slot', {'service_prompt':doc.name,'sampling_date':['>',doc.active_until]}):
        frappe.throw('不能排除已经生成的应采记录。')
    rows = frappe.get_all(doc.doctype, filters={'service':doc.service,'target_name':doc.target_name,'prompt':key}, fields=['name','active_from','active_until'])
    if any(row.name != doc.name and _overlap(doc.active_from,doc.active_until,row.active_from,row.active_until) for row in rows):
        frappe.throw('同一服务和标的已在该期间监测此问句。')


def plan(doc, method=None):
    lock_service(doc.service)
    if not doc.is_new():
        frappe.throw('计划版本不可修改，请复制并填写“替换计划版本”。')
    date_range(doc.effective_from, doc.effective_until)
    doc.revision = 1
    if doc.replaces_plan:
        old = _close_previous(doc.doctype, doc.replaces_plan, doc.service, doc.effective_from, 'effective_from','effective_until')
        if frappe.db.exists(doc.doctype, {'replaces_plan':old.name}):
            frappe.throw('此版本已被另一计划替换。')
        doc.revision = old.revision + 1
    if not doc.prompts or not doc.windows or len(doc.prompts) > 100:
        frappe.throw('需要 1 至 100 条问句以及至少一个时窗。')
    unique([r.service_prompt for r in doc.prompts], '计划问句')
    if any(frappe.db.get_value('GEO Service Prompt', r.service_prompt, 'service') != doc.service for r in doc.prompts):
        frappe.throw('计划只能包含本服务的问句。')
    try:
        params = json.loads(doc.parameters_json)
        if not isinstance(params, dict):
            raise ValueError('采集参数须为 JSON 对象。')
        parse_weekdays(doc.weekdays)
        ZoneInfo(doc.time_zone)
        windows = sorted((clock(w.from_time),clock(w.to_time),w.samples) for w in doc.windows)
        if any(first[1] > second[0] for first, second in zip(windows,windows[1:])):
            raise ValueError('同一计划的时窗不得重叠。')
        if sum(w.samples for w in doc.windows) * len(doc.prompts) > 1000:
            raise ValueError('每日每计划最多生成 1000 条应采记录。')
        for a,b,n in windows:
            subdivide(getdate(doc.effective_from),a,b,n,doc.time_zone,get_system_timezone())
    except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
        frappe.throw(f'计划配置无效：{exc}')
    from task_execution.validation import parameters, schema
    cap = frappe.get_doc('Execution Capability', doc.capability)
    if not cap.enabled or cap.operation != 'prompt':
        frappe.throw('监测计划必须选择启用的问句采集能力。')
    try:
        parameters(params, schema(cap.parameter_schema))
    except ValueError as exc:
        frappe.throw(f'采集参数无效：{exc}')
