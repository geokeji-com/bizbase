from datetime import date, datetime, timedelta
import unittest

from geo_service.planning import clock, parse_weekdays, subdivide


class ScheduleTests(unittest.TestCase):
    def test_weekdays(self):
        self.assertEqual(parse_weekdays('1, 3,5'), {1, 3, 5})
        for value in ('', '0,1', '1,8', '周日'):
            with self.assertRaises(ValueError):
                parse_weekdays(value)

    def test_contiguous_independent_samples_preserve_full_window(self):
        spans = subdivide(date(2026, 1, 3), '08:00:00', '09:00:01', 3, 'Asia/Shanghai', 'UTC')
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0][0], datetime(2026, 1, 3, 0))
        self.assertEqual(spans[-1][-1], datetime(2026, 1, 3, 1, 0, 1))
        self.assertEqual([e for _,e in spans[:-1]], [s for s,_ in spans[1:]])
        self.assertEqual(clock(timedelta(hours=9)), datetime(2026, 1, 3, 9).time())

    def test_no_zero_length_or_ambiguous_windows(self):
        for a,b,n in [('11:00','10:00',1),('10:00','10:01',0),('10:00:00','10:00:01',2)]:
            with self.assertRaises(ValueError):
                subdivide(date(2026,1,1),a,b,n,'Asia/Shanghai','UTC')
        with self.assertRaises(ValueError):
            subdivide(date(2026,11,1),'01:15','02:35',1,'America/New_York','UTC')


if __name__ == '__main__':
    unittest.main()
