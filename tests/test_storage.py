import unittest
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from model import Task
from storage import TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "TodoList" / "tasks.db"

    def test_lifecycle_across_reopens(self):
        deadline = datetime(2026, 11, 21, 10, 0, 12, 123456)
        with closing(TaskStore(self.path)) as store:
            task = store.add_task("  修改 O'Brien 的报告  ", 2, deadline)
            expected = Task(task.id, "修改 O'Brien 的报告", 2, deadline)
            self.assertEqual(task, expected)

        with closing(TaskStore(self.path)) as store:
            self.assertEqual(store.list_tasks(), [expected])
            store.set_done(task.id, True)
            store.update_task(task.id, "已交报告", 1, None)

        with closing(TaskStore(self.path)) as store:
            self.assertEqual(store.list_tasks(), [Task(task.id, "已交报告", 1, None, True)])
            store.set_done(task.id, False)
            self.assertFalse(store.list_tasks()[0].done)
            store.delete_task(task.id)

        with closing(TaskStore(self.path)) as store:
            self.assertEqual(store.list_tasks(), [])

    def test_invalid_update_and_missing_id_preserve_existing_task(self):
        with closing(TaskStore(self.path)) as store:
            task = store.add_task("写提纲", 2, None)
            with self.assertRaises(ValueError):
                store.update_task(task.id, "  ", 1, None)
            missing_id = task.id + 1
            with self.assertRaises(KeyError):
                store.update_task(missing_id, "新标题", 0, None)
            with self.assertRaises(KeyError):
                store.set_done(missing_id, True)
            with self.assertRaises(KeyError):
                store.delete_task(missing_id)

        with closing(TaskStore(self.path)) as store:
            self.assertEqual(store.list_tasks(), [task])

    def test_two_stores_share_commits_and_do_not_reuse_deleted_ids(self):
        with closing(TaskStore(self.path)) as first, closing(TaskStore(self.path)) as second:
            original = first.add_task("原任务", 0, None)
            self.assertEqual(second.list_tasks(), [original])
            second.delete_task(original.id)
            self.assertEqual(first.list_tasks(), [])
            replacement = first.add_task("新任务", 2, None)
            self.assertGreater(replacement.id, original.id)
            self.assertEqual(second.list_tasks(), [replacement])
