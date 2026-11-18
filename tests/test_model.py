import unittest
from datetime import datetime, timedelta
from itertools import product

from model import Task, rank_tasks, score, time_description, urgency


class PriorityTests(unittest.TestCase):
    now = datetime(2026, 11, 18, 9)

    def deadline(self, hours):
        return self.now + timedelta(hours=hours)

    def test_all_nine_combinations(self):
        for importance, (hours, urgency_points) in product(range(3), [(6, 2), (48, 1), (96, 0)]):
            with self.subTest(importance=importance, hours=hours):
                task = Task(1, "任务", importance, self.deadline(hours))
                self.assertEqual(score(task, self.now), importance + urgency_points)

    def test_time_boundaries(self):
        tick = timedelta(microseconds=1)
        cases = [
            (None, 0),
            (self.deadline(-2), 2),
            (self.now, 2),
            (self.deadline(24) - tick, 2),
            (self.deadline(24), 2),
            (self.deadline(24) + tick, 1),
            (self.deadline(72) - tick, 1),
            (self.deadline(72), 1),
            (self.deadline(72) + tick, 0),
        ]
        for due, expected in cases:
            with self.subTest(due=due):
                self.assertEqual(urgency(due, self.now), expected)

    def test_report_and_registration_example(self):
        form = Task(1, "登记表", 0, self.deadline(6))
        report = Task(2, "重要报告", 2, self.deadline(48))
        next_week = Task(2, "重要报告", 2, self.deadline(168))
        self.assertEqual(rank_tasks([form, report], self.now), [report, form])
        self.assertEqual(rank_tasks([next_week, form], self.now), [form, next_week])

    def test_equal_scores_use_deadline_then_insertion_id(self):
        no_date = Task(1, "无截止", 2, None)
        later = Task(2, "稍后截止", 1, self.deadline(36))
        first = Task(3, "先添加", 0, self.deadline(4))
        second = Task(4, "后添加", 0, first.due_at)
        self.assertEqual(rank_tasks([second, later, no_date, first], self.now),
                         [first, second, later, no_date])

    def test_overdue_still_competes_by_score(self):
        overdue = Task(1, "已逾期登记", 0, self.deadline(-1))
        report = Task(2, "重要报告", 2, self.deadline(48))
        self.assertEqual(rank_tasks([overdue, report], self.now), [report, overdue])

    def test_advancing_clock_changes_first_task(self):
        ongoing = Task(1, "长期任务", 2, None)
        upcoming = Task(2, "提交作业", 1, self.deadline(73))
        self.assertEqual(rank_tasks([ongoing, upcoming], self.now)[0], ongoing)
        self.assertEqual(rank_tasks([ongoing, upcoming], self.deadline(1))[0], upcoming)

    def test_empty_and_completed_tasks(self):
        pending = Task(1, "还要做", 0, None)
        done = Task(2, "做完了", 2, self.now, True)
        self.assertEqual(rank_tasks([], self.now), [])
        self.assertEqual(rank_tasks([done], self.now), [])
        self.assertEqual(rank_tasks([done, pending], self.now), [pending])

    def test_readable_time_in_recommendation(self):
        self.assertEqual(time_description(None, self.now), "未设截止时间")
        self.assertEqual(time_description(self.now, self.now), "现在到期")
        self.assertEqual(time_description(self.deadline(48), self.now), "距截止还有 48 小时")
        self.assertEqual(time_description(self.deadline(-1.5), self.now), "已逾期 1 小时 30 分钟")
        self.assertEqual(time_description(self.now - timedelta(seconds=1), self.now),
                         "已逾期 不到 1 分钟")
