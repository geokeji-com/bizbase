import unittest

from task_execution.validation import result_fields, parameters, schema, site_time


class Inputs(unittest.TestCase):
    def test_typed_enums(self):
        defs = schema('{"online":[true,false],"depth":["high","low"]}')
        self.assertEqual(parameters({'online': True, 'depth': 'low'}, defs)['depth'], 'low')
        for invalid in ({'online': 1, 'depth': 'low'}, {'online': True}, {'online': True, 'depth': 'auto'}):
            with self.assertRaises(ValueError):
                parameters(invalid, defs)

    def test_observations_need_site_timezone_naive_dates(self):
        self.assertEqual(site_time('2026-11-21 12:00:00').hour, 12)
        with self.assertRaises(ValueError):
            site_time('2026-11-21T12:00:00+00:00')

    def test_prompt_result(self):
        request = {'online': True}
        data = {'answer': '无法提供回答', 'actual_parameters': request, 'response_kind': 'refusal'}
        self.assertEqual(result_fields('prompt', data, request)['sources'], 'null')
        self.assertEqual(result_fields('prompt', dict(data, sources=[]), request)['sources'], '[]')
        with self.assertRaises(ValueError):
            result_fields('prompt', dict(data, actual_parameters={'online': 1}), request)
        with self.assertRaises(ValueError):
            result_fields('prompt', dict(data, sources=[{'url': 'file:///x'}]), request)

    def test_link_outcome(self):
        data = {'http_status': 404, 'final_url': 'https://example.test/missing'}
        self.assertEqual(result_fields('link_check', data, {})['http_status'], 404)
        with self.assertRaises(ValueError):
            result_fields('link_check', dict(data, final_url='https://name:password@example.test'), {})
