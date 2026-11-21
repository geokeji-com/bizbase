from datetime import datetime, time, timedelta

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate

from geo_analysis.scoring import evaluate, format_rate


def lines(text):
    return [line.strip() for line in (text or '').splitlines() if line.strip()]


def require_scope(service):
    from geo_service.access import require_service
    if not isinstance(service, str) or not service:
        frappe.throw('请选择服务。', frappe.PermissionError)
    require_service(service)


def scoped_doc(doctype, name, service):
    require_scope(service)
    if not isinstance(name, str) or not frappe.db.exists(doctype, {'name': name, 'service': service}):
        frappe.throw('本服务无法访问该记录。', frappe.PermissionError)
    return frappe.get_doc(doctype, name)


def is_adoptable(result, slot):
    return (result and result.response_kind in ('answer', 'refusal') and result.observed_at
            and get_datetime(slot.window_start) <= get_datetime(result.observed_at) < get_datetime(slot.window_end))


def result_for_slot(slot):
    if not slot.task:
        return None
    fields = ['name', 'answer', 'observed_at', 'response_kind', 'sources', 'actual_parameters', 'share_url']
    result = frappe.db.get_value('Execution Result', {'task': slot.task}, fields, as_dict=True)
    return result if is_adoptable(result, slot) else None


class Revision(Document):
    def validate(self):
        if not self.is_new():
            frappe.throw('已保存的版本不可修改，请新建版本。')
        self.build()

    def on_trash(self):
        frappe.throw('追溯所用版本不可删除。')


class GEOEntitySetRevisionRecord(Revision):
    def build(self):
        require_scope(self.service)
        targets = frappe.get_doc('GEO Service', self.service).get('targets') or []
        if self.target not in {row.target_name for row in targets}:
            frappe.throw('标的必须属于所选服务。')
        if set([self.target, *lines(self.aliases)]) & set(lines(self.competitors)):
            frappe.throw('请核对标的、别名与竞品的重名项。')


class GEOAnalysisMethodRevisionRecord(Revision):
    def build(self):
        if self.refusal_policy not in ('Exclude', 'Include as miss'):
            frappe.throw('请选择有效的拒答处理口径。')


class GEOSampleAnalysisRecord(Revision):
    def build(self):
        slot = scoped_doc('GEO Sampling Slot', self.slot, self.service)
        entities = scoped_doc('GEO Entity Set Revision', self.entity_set, self.service)
        if slot.target_name != entities.target:
            frappe.throw('采样标的与竞品版本不一致。')
        result = result_for_slot(slot)
        if not result or not result.answer:
            frappe.throw('此应采记录尚无回答。')
        if (result.response_kind == 'refusal') != (self.outcome == 'Refusal'):
            frappe.throw('复核结论与回传回答的拒答标记不符。')
        method = frappe.get_doc('GEO Analysis Method Revision', self.method)
        try:
            scores = evaluate(result.answer, [entities.target, *lines(entities.aliases)], self.outcome,
                              self.position, self.evidence_quote, method.refusal_policy)
        except ValueError as error:
            frappe.throw(str(error))
        self.update(scores)
        self.source_result = result.name
        self.observed_at = result.observed_at


class GEOReportRevisionRecord(Revision):
    def build(self):
        entities = scoped_doc('GEO Entity Set Revision', self.entity_set, self.service)
        start, end = getdate(self.from_date), getdate(self.to_date)
        if end < start:
            frappe.throw('截至日期应晚于或等于起始日期。')
        if self.prompt_filter:
            scoped_doc('GEO Service Prompt', self.prompt_filter, self.service)
        filters = [['service', '=', self.service], ['target_name', '=', entities.target],
                   ['window_start', '>=', datetime.combine(start, time.min)],
                   ['window_start', '<', datetime.combine(end + timedelta(days=1), time.min)]]
        if self.prompt_filter:
            filters.append(['service_prompt', '=', self.prompt_filter])
        if self.capability_filter:
            filters.append(['capability', '=', self.capability_filter])
        slots = frappe.get_all('GEO Sampling Slot', filters=filters, fields=['name', 'task', 'prompt_text', 'capability', 'window_start', 'window_end'], order_by='window_start asc, name asc')
        self.set('rows', [])
        self.expected = len(slots)
        self.collected = self.reviewed = self.mention_count = self.numerator = self.denominator = 0
        seen_results = set()
        for offset in range(0, len(slots), 500):
            batch = slots[offset:offset + 500]
            tasks = [row.task for row in batch if row.task]
            results = frappe.get_all('Execution Result', filters={'task': ['in', tasks]}, fields=['name', 'task', 'observed_at', 'response_kind']) if tasks else []
            results_by_task = {row.task: row for row in results}
            analyses = frappe.get_all('GEO Sample Analysis', filters={'service': self.service, 'entity_set': self.entity_set, 'method': self.method, 'slot': ['in', [row.name for row in batch]]}, fields=['name','slot','source_result','included','hit','mentioned_as'], order_by='creation asc, name asc')
            latest = {row.slot: row for row in analyses}
            for slot in batch:
                result = results_by_task.get(slot.task)
                analysis = latest.get(slot.name)
                row = self.append('rows', dict(slot=slot.name, prompt_text=slot.prompt_text, capability=slot.capability, window_start=slot.window_start, window_end=slot.window_end, count_status='尚未采到回答', included=0, hit=0))
                if not result:
                    continue
                if not is_adoptable(result, slot):
                    row.count_status = '采样条件或时间不符'
                    continue
                self.collected += 1
                if not analysis or analysis.source_result != result.name:
                    row.count_status = '待复核'
                    continue
                row.analysis = analysis.name
                if result.name in seen_results:
                    row.count_status = '同一回答已计入本报告'
                    continue
                seen_results.add(result.name)
                self.reviewed += 1
                row.count_status = '已纳入' if analysis.included else '按口径排除拒答'
                row.included, row.hit = analysis.included, analysis.hit
                row.mention_hit = int(bool(analysis.mentioned_as and analysis.included))
                self.mention_count += row.mention_hit
                self.denominator += row.included
                self.numerator += row.hit
        self.mention_rate = format_rate(self.mention_count, self.denominator)
        self.top3_display = format_rate(self.numerator, self.denominator)
