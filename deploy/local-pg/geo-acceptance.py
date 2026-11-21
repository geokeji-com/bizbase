"""Two synthetic services on a local PG preview. Run with bench's Python; roll back all rows."""
import json
import os
from uuid import uuid4

import frappe
from frappe.utils import getdate, now_datetime


def insert(doctype, **fields):
    return frappe.get_doc({"doctype": doctype, **fields}).insert()


def check():
    from geo_analysis import api as analysis
    from geo_service import api as plans
    from geo_service.access import require_service
    from task_execution import api as tasks

    prefix = f"QA-{uuid4().hex[:10]}"
    today = getdate()
    question = f"{prefix} 示例：哪些品牌值得比较？"
    answer = "建议顺序为：1. 甲品牌；2. 丙品牌；3. 丁品牌；4. 乙品牌。"
    parameters = {"online": True}
    payload = {"response_kind": "answer", "answer": answer, "actual_parameters": parameters,
               "sources": [{"title": "合成信源", "url": "https://example.test/evidence"}]}
    frappe.set_user("Administrator")
    worker = insert("User", email=f"worker-{prefix.lower()}@example.test", first_name="测试执行器", send_welcome_email=0)
    member = insert("User", email=f"member-{prefix.lower()}@example.test", first_name="测试运营", send_welcome_email=0,
                    roles=[{"role": "Sales User"}])
    capabilities = [insert("Execution Capability", capability_key=f"{prefix}-{i}", operation="prompt", platform=platform,
                           channel="App", version_tag="qa1", parameter_schema=json.dumps({"online": [True, False]}))
                    for i, platform in enumerate(["测试甲平台", "测试乙平台"])]
    insert("Execution Worker", worker_user=worker.name, worker_label=prefix,
           capabilities=[{"capability": cap.name} for cap in capabilities])
    services = []
    slots = []
    for index, target in enumerate(["甲品牌", "乙品牌"]):
        label = f"{prefix}-{index}"
        customer = insert("Customer", customer_name=label, customer_type="Company")
        contract = insert("Contract", party_type="Customer", party_name=customer.name, contract_terms="测试约定")
        service = insert("GEO Service", service_title=label, customer=customer.name, contract=contract.name,
                         served_organization=label, responsible_user="Administrator", start_date=today,
                         targets=[{"target_name": target, "target_type": "Brand"}],
                         members=[{"user": member.name}] if index == 0 else [])
        services.append(service)
        prompt = insert("GEO Service Prompt", service=service.name, target_name=target, prompt_text=question,
                        active_from=today)
        selected = []
        for cap in capabilities[:index + 1]:
            plan = insert("GEO Monitoring Plan", plan_title=label, service=service.name, capability=cap.name,
                          parameters_json=json.dumps(parameters), effective_from=today,
                          prompts=[{"service_prompt": prompt.name}],
                          windows=[{"from_time": "00:00:00", "to_time": "23:59:59", "samples": 1}])
            generated = plans.generate_slots(plan.name, str(today))
            assert len(generated) == 1
            assert plans.generate_slots(plan.name, str(today)) == generated
            adopted = plans.dispatch_slots(plan.name, str(today))
            assert len(adopted) == 1 and adopted == plans.dispatch_slots(plan.name, str(today))
            selected.extend(adopted)
        slots.append(selected)
    assert slots[0][0]['task'] == slots[1][0]['task'] != slots[1][1]['task']
    assert len({s['slot'] for group in slots for s in group}) == 3
    task_names = {s['task'] for group in slots for s in group}
    frappe.set_user(worker.name)
    for index in range(2):
        claimed = tasks.claim()
        assert tasks.claim()['attempt'] == claimed['attempt']
        if index == 0:
            first_task = claimed['task']
            first_time = frappe.db.get_value('Execution Task', first_task, 'first_claimed_at')
            assert tasks.fail(first_task, claimed['attempt'], 'synthetic device timeout') == 'Queued'
            retried = tasks.claim()
            if retried['task'] == first_task:
                assert retried['attempt'] != claimed['attempt']
            assert frappe.db.get_value('Execution Task', first_task, 'first_claimed_at') == first_time
            claimed = retried
        tasks.renew(claimed['task'], claimed['attempt'])
        assert claimed['task'] in task_names
        task_names.remove(claimed['task'])
        observed_at = str(now_datetime())
        accepted = tasks.complete(claimed['task'], claimed['attempt'], observed_at, payload)
        assert tasks.complete(claimed['task'], claimed['attempt'], observed_at, payload) == accepted
    assert not tasks.claim()
    frappe.set_user('Administrator')
    for key in {s['task'] for group in slots for s in group}:
        task = frappe.get_doc('Execution Task', key)
        assert task.creation <= task.first_claimed_at <= task.completed_at
        assert task.attempt_count == (2 if key == first_task else 1)
        assert frappe.db.count('Execution Result', {'task': key}) == 1
    method = insert('GEO Analysis Method Revision', label=prefix, refusal_policy='Exclude')
    reports = []
    samples = []
    for i, (service, adopted) in enumerate(zip(services, slots, strict=True)):
        target = ['甲品牌', '乙品牌'][i]
        entity_set = insert('GEO Entity Set Revision', service=service.name, target=target)
        service_samples = []
        for slot in adopted:
            sample = insert('GEO Sample Analysis', service=service.name, slot=slot['slot'],
                            entity_set=entity_set.name, method=method.name, outcome='Ranked',
                            position=[1, 4][i], evidence_quote=answer)
            service_samples.append(sample.name)
        samples.append(service_samples)
        report = insert('GEO Report Revision', service=service.name, entity_set=entity_set.name,
                        method=method.name, from_date=today, to_date=today)
        totals = (report.expected, report.collected, report.reviewed, report.numerator, report.denominator)
        assert totals == ((1, 1, 1, 1, 1) if i == 0 else (2, 2, 2, 0, 2)), totals
        reports.append(report)
    frappe.set_user(member.name)
    require_service(services[0].name)
    assert [s.name for s in plans.my_services()] == [services[0].name]
    progress = plans.coverage(services[0].name, today)
    assert (progress['expected'], progress['collected']) == (1, 1)
    assert all('task' not in row for row in progress['slots'])
    from geo_analysis.www.geo_review import get_context
    frappe.local.form_dict = frappe._dict(service=services[0].name, date=str(today), report=reports[0].name, sample=samples[0][0])
    context = frappe._dict()
    get_context(context)
    from frappe.utils.jinja import get_jenv
    template = get_jenv().get_template('geo_analysis/www/geo-review.html')
    html = ''.join(template.blocks['page_content'](template.new_context(context)))
    assert answer in html and question in html and services[1].service_title not in html
    evidence = analysis.read_sample(services[0].name, samples[0][0])
    assert answer in json.dumps(evidence, ensure_ascii=False, default=str)
    for operation in (lambda: require_service(services[1].name),
                      lambda: analysis.read_report(services[1].name, reports[1].name),
                      lambda: analysis.read_sample(services[0].name, samples[1][0])):
        try:
            operation()
        except (frappe.PermissionError, frappe.DoesNotExistError):
            continue
        raise AssertionError('out-of-scope service data was returned')
    print('PASS: 3 service slots, 2 tasks and 2 answers; repeated dispatch and callbacks; service-scoped evidence.')


if __name__ == '__main__':
    os.chdir('sites')
    frappe.init(site='frontend')
    try:
        frappe.connect()
        assert frappe.db.db_type == 'postgres'
        check()
    finally:
        frappe.db.rollback()
        frappe.destroy()
