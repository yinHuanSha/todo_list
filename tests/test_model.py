import unittest
from datetime import datetime, timedelta

from model import Task, rank_tasks, score, time_description, urgency


class PriorityTests(unittest.TestCase):
    now = datetime(2026, 11, 18, 9)

    def deadline(self, hours):
        return self.now + timedelta(hours=hours)

    def test_all_nine_combinations(self):
        tasks = []
        expected_scores = ((0, 2, 4), (3, 5, 7), (6, 8, 10))
        for importance, row in enumerate(expected_scores):
            for hours, points in zip((96, 48, 6), row, strict=True):
                with self.subTest(importance=importance, hours=hours):
                    task = Task(len(tasks) + 1, "任务", importance, self.deadline(hours))
                    tasks.append(task)
                    self.assertEqual(score(task, self.now), points)
        previous_order = sorted(tasks, key=lambda t: (t.importance + urgency(t.due_at, self.now),
                                                       t.importance), reverse=True)
        self.assertEqual(rank_tasks(tasks, self.now), previous_order)

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

    def test_scores_show_the_priority_of_previously_tied_tasks(self):
        meeting = Task(1, "座谈会", 0, self.deadline(15))
        prep = Task(2, "组会准备", 1, self.deadline(48))
        report = Task(3, "提交开题报告", 2, self.deadline(126))
        tasks = [meeting, prep, report]
        self.assertEqual([score(task, self.now) for task in tasks], [4, 5, 6])
        self.assertEqual(rank_tasks(tasks, self.now), [report, prep, meeting])

    def test_equal_scores_and_importance_use_deadline_then_insertion_id(self):
        no_date = Task(1, "无截止", 2, None)
        later = Task(2, "稍后截止", 2, self.deadline(100))
        first = Task(3, "先添加", 2, self.deadline(90))
        second = Task(4, "后添加", 2, first.due_at)
        self.assertEqual(rank_tasks([second, later, no_date, first], self.now),
                         [first, second, later, no_date])

    def test_overdue_still_competes_by_score(self):
        overdue = Task(1, "已逾期登记", 0, self.deadline(-1))
        report = Task(2, "重要报告", 2, self.deadline(48))
        self.assertEqual(rank_tasks([overdue, report], self.now), [report, overdue])

    def test_advancing_clock_changes_first_task(self):
        ongoing = Task(1, "长期任务", 2, None)
        upcoming = Task(2, "提交作业", 1, self.deadline(73))
        for elapsed, points, recommended in [(0, 3, ongoing), (1, 5, ongoing), (49, 7, upcoming)]:
            with self.subTest(elapsed=elapsed):
                now = self.deadline(elapsed)
                self.assertEqual(score(upcoming, now), points)
                self.assertEqual(rank_tasks([ongoing, upcoming], now)[0], recommended)

    def test_empty_and_completed_tasks(self):
        pending = Task(1, "还要做", 0, None)
        done = Task(2, "做完了", 2, self.now, True)
        self.assertEqual(rank_tasks([], self.now), [])
        self.assertEqual(rank_tasks([done], self.now), [])
        self.assertEqual(rank_tasks([done, pending], self.now), [pending])

    def test_rank_subtasks_alongside_standalone_tasks(self):
        group = Task(1, "提交开题材料", 2, self.deadline(96))
        report = Task(2, "报告正文", 2, group.due_at, parent_id=group.id)
        cover = Task(3, "封面", 0, group.due_at, parent_id=group.id)
        seminar = Task(4, "准备组会", 1, self.deadline(36))
        tasks = [group, cover, seminar, report]
        self.assertEqual(rank_tasks(iter(tasks), self.now), [report, seminar, cover])
        finished_report = Task(report.id, report.title, 2, group.due_at, True, group.id)
        self.assertEqual(rank_tasks([group, finished_report, cover, seminar], self.now),
                         [seminar, cover])

    def test_completed_children_do_not_turn_group_into_a_recommendation(self):
        group = Task(1, "材料", 2, self.now)
        submitted = Task(2, "附件", 0, group.due_at, True, group.id)
        self.assertEqual(rank_tasks([group, submitted], self.now), [])

    def test_readable_time_in_recommendation(self):
        self.assertEqual(time_description(None, self.now), "未设截止时间")
        self.assertEqual(time_description(self.now, self.now), "现在到期")
        self.assertEqual(time_description(self.deadline(48), self.now), "距截止还有 2 天")
        self.assertEqual(time_description(self.deadline(-1.5), self.now), "已逾期 1 小时 30 分钟")
        self.assertEqual(time_description(self.now - timedelta(seconds=1), self.now),
                         "已逾期 不到 1 分钟")

    def test_day_hour_minute_countdown(self):
        cases = [
            (timedelta(hours=23, minutes=59), "23 小时 59 分钟"),
            (timedelta(hours=24), "1 天"),
            (timedelta(days=1, minutes=1), "1 天 1 分钟"),
            (timedelta(hours=126, minutes=13), "5 天 6 小时 13 分钟"),
        ]
        for delta, expected in cases:
            with self.subTest(delta=delta):
                self.assertEqual(time_description(self.now + delta, self.now), f"距截止还有 {expected}")
                self.assertEqual(time_description(self.now - delta, self.now), f"已逾期 {expected}")
