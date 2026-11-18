import unittest
from datetime import date, datetime

from ui import calendar_fields, parse_deadline


class DeadlineInputTests(unittest.TestCase):
    today = date(2026, 11, 18)

    def test_manual_entry_accepts_both_colons(self):
        expected = datetime(2028, 2, 29, 9, 7)
        for clock in ("09:07", "09：07"):
            with self.subTest(clock=clock):
                self.assertEqual(parse_deadline(f"  2028-02-29 {clock}  "), expected)

    def test_optional_deadline_and_date_only(self):
        self.assertIsNone(parse_deadline("  "))
        self.assertEqual(parse_deadline("2026-11-23"), datetime(2026, 11, 23, 23, 59))
        self.assertEqual(calendar_fields("", self.today), (self.today, "23:59"))
        self.assertEqual(calendar_fields("2028-02-29", self.today), (date(2028, 2, 29), "23:59"))

    def test_calendar_keeps_an_existing_clock(self):
        for raw in ("2028-02-29 19：45", "2028-02-29 19:45"):
            with self.subTest(raw=raw):
                initial, clock = calendar_fields(raw, self.today)
                self.assertEqual(initial, date(2028, 2, 29))
                self.assertEqual(parse_deadline(f"2029-01-01 {clock}"), datetime(2029, 1, 1, 19, 45))
        self.assertEqual(calendar_fields("08：20", self.today), (self.today, "08:20"))

    def test_invalid_date_can_be_replaced_without_losing_typed_time(self):
        self.assertEqual(calendar_fields("2027-02-29 15：00", self.today), (self.today, "15:00"))
        for raw in ("2027-02-29", "2028-02-29 24：01", "08：20", "2028-02-29 10：60"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_deadline(raw)
