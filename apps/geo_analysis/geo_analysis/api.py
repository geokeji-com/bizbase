"""Service-scoped projections. Global result/task IDs and execution resources stay private."""

import json

import frappe
from geo_analysis.records import result_for_slot, scoped_doc
from geo_analysis.scoring import answer_hash


def fields(doc, allowed):
    return {field: doc.get(field) for field in allowed.split()}


@frappe.whitelist()
def read_report(service: str, report: str):
    revision = scoped_doc('GEO Report Revision', report, service)
    data = fields(revision, 'name service entity_set method from_date to_date prompt_filter capability_filter creation expected collected reviewed numerator denominator top3_display mention_count mention_rate')
    data['rows'] = [fields(row, 'slot prompt_text capability window_start window_end analysis count_status included hit mention_hit') for row in revision.rows]
    return data


@frappe.whitelist()
def read_sample(service: str, sample: str):
    review = scoped_doc('GEO Sample Analysis', sample, service)
    slot = scoped_doc('GEO Sampling Slot', review.slot, service)
    result = result_for_slot(slot)
    if not result or result.name != review.source_result or answer_hash(result.answer) != review.source_hash:
        frappe.throw('无法核对本条样本的原始回答。')
    data = fields(review, 'name service slot entity_set method owner creation outcome position evidence_quote review_note mentioned_as included hit')
    data.update(_evidence(slot, result))
    return data


@frappe.whitelist()
def read_slot(service: str, slot: str):
    entry = scoped_doc('GEO Sampling Slot', slot, service)
    result = result_for_slot(entry)
    if not result:
        frappe.throw('尚无符合此时窗的回答。')
    return _evidence(entry, result)


def _evidence(slot, result):
    return dict(prompt_text=slot.prompt_text, capability=slot.capability, observed_at=result.observed_at,
                response_kind=result.response_kind, answer=result.answer, sources=json.loads(result.sources or '[]'),
                actual_parameters=json.loads(result.actual_parameters or '{}'), share_url=result.share_url)
