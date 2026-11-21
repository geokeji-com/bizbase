"""Business callers submit internally; dedicated Worker users claim and settle via POST."""
from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from task_execution import validation as v

LEASE = timedelta(minutes=5)
MAX_ATTEMPTS = 3


def _insert(doctype, **fields):
    return frappe.get_doc({'doctype': doctype, **fields}).insert(ignore_permissions=True)


def _update(doctype, key, **fields):
    frappe.db.set_value(doctype, key, fields)


def _lock(doctype, key):
    if not frappe.db.get_value(doctype, key, 'name', for_update=True):
        frappe.throw('记录不存在', frappe.DoesNotExistError)
    return frappe.get_doc(doctype, key)


def ensure_task(prompt_text, capability, parameters, window_start, window_end, sample_index=0):
    cap = _lock('Execution Capability', capability)
    if not cap.enabled:
        frappe.throw('此执行能力已停用')
    prompt = prompt_text.strip() if isinstance(prompt_text, str) else ''
    start, end = v.site_time(window_start), v.site_time(window_end)
    if not prompt or len(prompt) > 20000 or end <= start or type(sample_index) is not int or sample_index < 0:
        frappe.throw('输入、采样时窗或样本序号无效')
    if cap.operation == 'link_check':
        v.url(prompt)
    params = v.parameters(parameters, v.schema(cap.parameter_schema))
    key = v.digest([prompt, capability, params, start.isoformat(), end.isoformat(), sample_index])
    if frappe.db.exists('Execution Task', key):
        return key
    return _insert('Execution Task', request_key=key, prompt_text=prompt, capability=cap.name,
                   operation=cap.operation, parameters=v.canonical(params), window_start=start,
                   window_end=end, sample_index=sample_index, state='Queued').name


@frappe.whitelist(methods=['POST'])
def submit(input_text: str, capability: str, parameters, window_start, window_end, sample_index: int = 0):
    """Manual single-task submission; the planner uses ensure_task internally."""
    frappe.only_for('System Manager')
    return ensure_task(input_text, capability, parameters, window_start, window_end, sample_index)


def _worker():
    user = frappe.session.user
    if user in ('Guest', 'Administrator'):
        frappe.throw('需要专用 Worker 身份', frappe.PermissionError)
    key = frappe.db.get_value('Execution Worker', {'worker_user': user, 'enabled': 1}, 'name', for_update=True)
    if not key:
        frappe.throw('Worker 未登记或已停用', frappe.PermissionError)
    worker = frappe.get_doc('Execution Worker', key)
    _update('Execution Worker', key, last_seen_at=now_datetime())
    return worker


def _terminal(task, now):
    if task.window_end <= now:
        return 'Expired'
    if task.attempt_count >= MAX_ATTEMPTS:
        return 'Failed'
    return 'Queued'


def _release(task, now, reason, attempt_state):
    if task.current_attempt and task.state == 'Running':
        _update('Execution Attempt', task.current_attempt, state=attempt_state, ended_at=now, reason=reason)
    state = _terminal(task, now)
    _update('Execution Task', task.name, state=state, lease_until=None,
            completed_at=None if state == 'Queued' else now)
    return state


def expire_tasks():
    """Bounded, repeatable sweeps. Terminal tasks retain their last attempt for audit."""
    now = now_datetime()
    table = frappe.qb.DocType('Execution Task')
    tasks = (frappe.qb.from_(table).select(table.name)
             .where(((table.state == 'Queued') & (table.window_end <= now)) |
                    ((table.state == 'Running') & (table.lease_until <= now)))
             .orderby(table.window_end).limit(200).for_update(skip_locked=True).run())
    for (key,) in tasks:
        _release(frappe.get_doc('Execution Task', key), now, '采样时窗或租约已结束', 'Expired')


def _offer(task, attempt):
    cap = frappe.get_doc('Execution Capability', task.capability)
    return dict(task=task.name, attempt=attempt.name, lease_until=attempt.lease_until,
                window_start=task.window_start, window_end=task.window_end, operation=task.operation,
                input=task.prompt_text, capability=cap.name, platform=cap.platform, channel=cap.channel,
                version_tag=cap.version_tag, parameters=v.as_object(task.parameters))


@frappe.whitelist(methods=['POST'])
def claim():
    worker = _worker()
    expire_tasks()
    # One outstanding command per device. A lost claim response returns the same lease.
    active = frappe.db.get_value('Execution Attempt', {'worker': worker.name, 'state': 'Running'}, 'name')
    if active:
        attempt = frappe.get_doc('Execution Attempt', active)
        task = _lock('Execution Task', attempt.task)
        if task.state == 'Running' and task.current_attempt == active and task.lease_until > now_datetime():
            return _offer(task, attempt)
    capabilities = [row.capability for row in worker.capabilities]
    if not capabilities:
        return None
    filters = {'name': ['in', capabilities], 'enabled': 1}
    if worker.account_ref:
        account = frappe.get_doc('Execution Account', worker.account_ref)
        if account.state != 'Ready':
            return None
        filters['platform'] = account.platform
    if worker.proxy_ref and not frappe.db.get_value('Execution Proxy', worker.proxy_ref, 'enabled'):
        return None
    enabled = frappe.get_all('Execution Capability', filters=filters, pluck='name')
    if not enabled:
        return None
    now = now_datetime()
    key = frappe.db.get_value('Execution Task', {'state': 'Queued', 'capability': ['in', enabled],
                              'window_start': ['<=', now], 'window_end': ['>', now]}, 'name',
                              order_by='window_end asc, creation asc', for_update=True, skip_locked=True)
    if not key:
        return None
    task = frappe.get_doc('Execution Task', key)
    until = min(now + LEASE, task.window_end)
    attempt = _insert('Execution Attempt', task=key, worker=worker.name, claimed_at=now, lease_until=until,
                      state='Running', account_ref=worker.account_ref, proxy_ref=worker.proxy_ref)
    _update('Execution Task', key, state='Running', attempt_count=task.attempt_count + 1,
            first_claimed_at=task.first_claimed_at or now, current_attempt=attempt.name, lease_until=until)
    return _offer(task, attempt)


def _owned(task, attempt):
    worker = _worker()
    # Check both references in one read before looking up any global task information.
    if not frappe.db.exists('Execution Attempt', {'name': attempt, 'task': task, 'worker': worker.name}):
        frappe.throw('没有此执行尝试的授权', frappe.PermissionError)
    return _lock('Execution Task', task), frappe.get_doc('Execution Attempt', attempt)


def _check_active(task, attempt, now):
    if task.state != 'Running' or task.current_attempt != attempt.name or task.lease_until <= now:
        frappe.throw('本次领取已结束或租约已过期')


@frappe.whitelist(methods=['POST'])
def renew(task: str, attempt: str):
    current, run = _owned(task, attempt)
    now = now_datetime()
    _check_active(current, run, now)
    until = min(now + LEASE, current.window_end)
    _update('Execution Task', task, lease_until=until)
    _update('Execution Attempt', attempt, lease_until=until)
    return until


@frappe.whitelist(methods=['POST'])
def complete(task: str, attempt: str, observed_at, payload):
    current, run = _owned(task, attempt)
    now = now_datetime()
    observed = v.site_time(observed_at)
    fields = v.result_fields(current.operation, payload, v.as_object(current.parameters))
    signature = v.digest([attempt, observed.isoformat(), fields])
    if current.state == 'Succeeded':
        if current.current_attempt == attempt and frappe.db.get_value('Execution Result', task, 'result_digest') == signature:
            return task
        frappe.throw('任务已经接收不同的回传')
    _check_active(current, run, now)
    if not run.claimed_at <= observed <= now or not current.window_start <= observed < current.window_end:
        frappe.throw('观测时间不在本次执行和约定时窗内')
    result = _insert('Execution Result', task=task, attempt=attempt, observed_at=observed,
                     result_digest=signature, **fields)
    _update('Execution Attempt', attempt, state='Succeeded', ended_at=now)
    _update('Execution Task', task, state='Succeeded', completed_at=now, lease_until=None)
    return result.name


@frappe.whitelist(methods=['POST'])
def fail(task: str, attempt: str, reason: str):
    current, run = _owned(task, attempt)
    now = now_datetime()
    _check_active(current, run, now)
    if not reason.strip() or len(reason) > 1000:
        frappe.throw('请提供简短错误原因')
    return _release(current, now, reason, 'Failed')
