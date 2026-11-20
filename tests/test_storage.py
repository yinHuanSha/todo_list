import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

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

    def test_legacy_database_migrates_once_under_concurrent_open_and_write(self):
        self.path.parent.mkdir()
        deadline = datetime(2026, 12, 1, 9, 30)
        with closing(sqlite3.connect(self.path)) as legacy, legacy:
            # 旧版正式表结构，含已经删除的最大任务号。
            legacy.execute(
                """CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    importance INTEGER NOT NULL CHECK (importance IN (0, 1, 2)),
                    due_at TEXT,
                    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
                )"""
            )
            legacy.executemany(
                "INSERT INTO tasks (id, title, importance, due_at, done) VALUES (?, ?, ?, ?, ?)",
                [
                    (3, "报告", 2, deadline.isoformat(), 0),
                    (8, "已交表格", 0, None, 1),
                    (17, "已删除", 0, None, 0),
                ],
            )
            legacy.execute("DELETE FROM tasks WHERE id = 17")

        workers = 4
        start = Barrier(workers)

        def finish_subtask(number):
            start.wait(timeout=10)
            with closing(TaskStore(self.path)) as store:
                child = store.add_subtask(3, f"章节 {number}", 1)
                store.set_done(child.id, True)
                return child.id

        with ThreadPoolExecutor(max_workers=workers) as pool:
            child_ids = list(pool.map(finish_subtask, range(workers)))
        self.assertEqual(len(set(child_ids)), workers)
        self.assertGreater(min(child_ids), 17)
        with closing(TaskStore(self.path)) as reopened:
            report, old_done, *children = reopened.list_tasks()
            self.assertEqual(report, Task(3, "报告", 2, deadline, True))
            self.assertEqual(old_done, Task(8, "已交表格", 0, None, True))
            self.assertEqual([t.id for t in children], sorted(child_ids))
            for child in children:
                self.assertEqual((child.parent_id, child.due_at, child.done), (3, deadline, True))

    def test_subtask_inherits_edited_and_cleared_deadline_across_instances(self):
        first_due = datetime(2027, 1, 2, 17, 20)
        second_due = datetime(2027, 1, 5, 8, 50)
        with closing(TaskStore(self.path)) as store, closing(TaskStore(self.path)) as other:
            parent = store.add_task("报告", 2, first_due)
            child = store.add_subtask(parent.id, " 初稿 ", 0)
            self.assertEqual(child, Task(child.id, "初稿", 0, first_due, parent_id=parent.id))
            other.update_task(parent.id, "终稿", 1, second_due)
            store.update_subtask(child.id, "修改提纲", 2)
            edited = Task(child.id, "修改提纲", 2, second_due, parent_id=parent.id)
            self.assertEqual(other.list_tasks()[1], edited)
            with closing(sqlite3.connect(self.path)) as db:
                raw_child = db.execute("SELECT due_at FROM tasks WHERE id = ?", (child.id,)).fetchone()
                self.assertIsNone(raw_child[0])
            other.update_task(parent.id, "终稿", 1, None)
            self.assertIsNone(store.list_tasks()[1].due_at)

    def test_completion_reopens_when_adding_or_restoring_a_subtask(self):
        with closing(TaskStore(self.path)) as store:
            parent = store.add_task("写作", 2, None)
            store.set_done(parent.id, True)
            first = store.add_subtask(parent.id, "引言", 1)
            self.assertFalse(store.list_tasks()[0].done)
            second = store.add_subtask(parent.id, "小结", 0)
            store.set_done(first.id, True)
            self.assertEqual([task.done for task in store.list_tasks()], [False, True, False])
            store.set_done(second.id, True)
            self.assertEqual([task.done for task in store.list_tasks()], [True, True, True])
            with self.assertRaises(ValueError):
                store.set_done(parent.id, False)

        with closing(TaskStore(self.path)) as reopened:
            reopened.set_done(first.id, False)
            self.assertEqual([task.done for task in reopened.list_tasks()], [False, False, True])

    def test_delete_recomputes_parent_and_last_child_preserves_standalone_state(self):
        with closing(TaskStore(self.path)) as store:
            for done in (False, True):
                with self.subTest(last_child_done=done):
                    parent = store.add_task("报告", 1, None)
                    first = store.add_subtask(parent.id, "保留", 1)
                    other = store.add_subtask(parent.id, "删除", 1)
                    store.set_done(first.id, done)
                    store.set_done(other.id, not done)
                    store.delete_task(other.id)
                    self.assertEqual([t.done for t in store.list_tasks()], [done, done])
                    store.delete_task(first.id)
                    self.assertEqual(store.list_tasks(), [Task(parent.id, "报告", 1, None, done)])
                    store.set_done(parent.id, not done)
                    self.assertEqual(store.list_tasks()[0].done, not done)
                    store.delete_task(parent.id)

    def test_cascade_delete_and_stale_forms(self):
        with closing(TaskStore(self.path)) as store, closing(TaskStore(self.path)) as other:
            parent = store.add_task("旧项目", 1, None)
            separate = store.add_task("保留项目", 1, None)
            child = other.add_subtask(parent.id, "子项", 0)
            sibling = other.add_subtask(parent.id, "批注", 2)
            with self.assertRaises(ValueError):
                store.set_done(parent.id, True)
            with self.assertRaises(ValueError):
                store.update_task(child.id, "误操作", 0, None)
            with self.assertRaises(ValueError):
                store.update_subtask(parent.id, "误操作", 0)
            with self.assertRaises(ValueError):
                store.add_subtask(child.id, "三级", 1)
            self.assertEqual(store.list_tasks(), [parent, separate, child, sibling])
            other.delete_task(parent.id)
            with self.assertRaises(KeyError):
                store.update_subtask(child.id, "过期的编辑框", 2)
            with self.assertRaises(KeyError):
                store.add_subtask(parent.id, "过期的新增框", 0)
            self.assertEqual(store.list_tasks(), [separate])

    def test_failed_parent_update_rolls_back_child_completion(self):
        with closing(TaskStore(self.path)) as store:
            parent = store.add_task("报告", 1, None)
            child = store.add_subtask(parent.id, "校对", 0)
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute(
                    """CREATE TRIGGER reject_parent_completion BEFORE UPDATE OF done ON tasks
                       WHEN NEW.parent_id IS NULL AND NEW.done = 1
                       BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
                )
            with self.assertRaises(sqlite3.IntegrityError):
                store.set_done(child.id, True)
            self.assertEqual(store.list_tasks(), [parent, child])
