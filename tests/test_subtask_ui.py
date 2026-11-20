import tkinter as tk
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from storage import TaskStore
from ui import TodoApp


class SubtaskViewTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        directory = self.enterContext(TemporaryDirectory())
        self.store = TaskStore(Path(directory) / "tasks.db")
        self.addCleanup(self.store.close)
        now = datetime.now()
        self.group = self.store.add_task("开题材料", 2, now + timedelta(days=5))
        self.report = self.store.add_subtask(self.group.id, "撰写正文", 2)
        self.cover = self.store.add_subtask(self.group.id, "整理封面", 0)
        self.meeting = self.store.add_task("准备组会", 1, now + timedelta(days=2))
        self.app = TodoApp(self.root, self.store)

    def test_expanded_group_keeps_progress_when_recommendation_moves(self):
        tree = self.app.tree
        group_id = str(self.group.id)
        self.assertEqual(self.app.best.id, self.report.id)
        self.assertEqual(tree.parent(str(self.report.id)), group_id)
        tree.item(group_id, open=True)
        self.app.hero_action()
        self.assertEqual(self.app.best.id, self.meeting.id)
        self.assertTrue(tree.item(group_id, "open"))
        self.assertIn("1/2", tree.item(group_id, "text"))
        self.assertCountEqual(tree.get_children(group_id), (str(self.report.id), str(self.cover.id)))

    def test_collapsed_group_shows_highest_remaining_child_score(self):
        tree = self.app.tree
        group_id = str(self.group.id)
        tree.item(group_id, open=False)
        self.assertEqual(tree.set(group_id, "score"), "6/10")
        self.app.hero_action()
        self.assertEqual(tree.set(group_id, "score"), "0/10")
        self.assertEqual(tree.set(str(self.meeting.id), "score"), "5/10")
        self.assertFalse(tree.item(group_id, "open"))
        self.store.set_done(self.report.id, False)
        self.app.refresh()
        self.assertEqual(tree.set(group_id, "score"), "6/10")

    def test_restore_one_child_from_a_completed_group(self):
        self.store.set_done(self.report.id, True)
        self.store.set_done(self.cover.id, True)
        self.app.switch_list(True)
        tree = self.app.tree
        group_id = str(self.group.id)
        self.assertIn("2/2", tree.item(group_id, "text"))
        tree.item(group_id, open=True)
        tree.selection_set(str(self.report.id))
        self.app.toggle_selected()
        self.app.switch_list(False)
        self.assertEqual(self.app.best.id, self.report.id)
        self.assertIn("1/2", tree.item(group_id, "text"))
