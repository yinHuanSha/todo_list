"""用 SQLite 保存待办任务，每次修改都独立提交。"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from model import Task, normalize_fields


class TaskStore:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
            path = Path(local) / "TodoList" / "tasks.db"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.row_factory = sqlite3.Row
        try:
            self._db.execute("PRAGMA foreign_keys = ON")
            self._initialize_schema()
        except sqlite3.Error:
            self._db.close()
            raise

    @contextmanager
    def _write(self):
        # 先取得写锁，再读取父子状态。另一个窗口的修改会在本次提交后执行。
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            yield

    def _initialize_schema(self) -> None:
        with self._write():
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    importance INTEGER NOT NULL CHECK (importance IN (0, 1, 2)),
                    due_at TEXT,
                    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
                )"""
            )
            columns = {row["name"] for row in self._db.execute("PRAGMA table_info(tasks)")}
            if "parent_id" not in columns:
                self._db.execute(
                    """ALTER TABLE tasks ADD COLUMN parent_id INTEGER
                       REFERENCES tasks(id) ON DELETE CASCADE
                       CHECK (parent_id IS NULL OR (parent_id <> id AND due_at IS NULL))"""
                )
            self._db.execute("CREATE INDEX IF NOT EXISTS tasks_by_parent ON tasks(parent_id)")

    def list_tasks(self) -> list[Task]:
        rows = self._db.execute(
            """SELECT t.id, t.title, t.importance, t.done, t.parent_id,
                      CASE WHEN t.parent_id IS NULL THEN t.due_at ELSE parent.due_at END AS due_at
               FROM tasks AS t LEFT JOIN tasks AS parent ON t.parent_id = parent.id
               ORDER BY t.id"""
        )
        return [
            Task(
                id=row["id"],
                title=row["title"],
                importance=row["importance"],
                due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
                done=bool(row["done"]),
                parent_id=row["parent_id"],
            )
            for row in rows
        ]

    def add_task(self, title: str, importance: int, due_at: datetime | None) -> Task:
        title, importance, due_at = normalize_fields(title, importance, due_at)
        with self._db:
            cursor = self._db.execute(
                "INSERT INTO tasks (title, importance, due_at) VALUES (?, ?, ?)",
                (title, importance, due_at.isoformat() if due_at else None),
            )
        return Task(id=cursor.lastrowid, title=title, importance=importance, due_at=due_at)

    def add_subtask(self, parent_id: int, title: str, importance: int) -> Task:
        title, importance, _ = normalize_fields(title, importance, None)
        with self._write():
            parent = self._get_row(parent_id)
            if parent["parent_id"] is not None:
                raise ValueError("只能在主任务下添加子任务。")
            due_at = datetime.fromisoformat(parent["due_at"]) if parent["due_at"] else None
            cursor = self._db.execute(
                "INSERT INTO tasks (title, importance, parent_id) VALUES (?, ?, ?)",
                (title, importance, parent_id),
            )
            self._db.execute("UPDATE tasks SET done = 0 WHERE id = ?", (parent_id,))
        return Task(cursor.lastrowid, title, importance, due_at, parent_id=parent_id)

    def update_task(
        self, task_id: int, title: str, importance: int, due_at: datetime | None
    ) -> None:
        title, importance, due_at = normalize_fields(title, importance, due_at)
        with self._write():
            if self._get_row(task_id)["parent_id"] is not None:
                raise ValueError("子任务的截止时间由主任务决定。")
            self._db.execute(
                "UPDATE tasks SET title = ?, importance = ?, due_at = ? WHERE id = ?",
                (title, importance, due_at.isoformat() if due_at else None, task_id),
            )

    def update_subtask(self, task_id: int, title: str, importance: int) -> None:
        title, importance, _ = normalize_fields(title, importance, None)
        with self._write():
            if self._get_row(task_id)["parent_id"] is None:
                raise ValueError("请选择要编辑的子任务。")
            self._db.execute(
                "UPDATE tasks SET title = ?, importance = ? WHERE id = ?",
                (title, importance, task_id),
            )

    def set_done(self, task_id: int, done: bool) -> None:
        with self._write():
            parent_id = self._get_row(task_id)["parent_id"]
            if parent_id is None and self._db.execute(
                "SELECT 1 FROM tasks WHERE parent_id = ? LIMIT 1", (task_id,)
            ).fetchone():
                raise ValueError("请逐项完成或恢复子任务，主任务状态会自动更新。")
            self._db.execute("UPDATE tasks SET done = ? WHERE id = ?", (int(done), task_id))
            if parent_id is not None:
                self._sync_parent(parent_id)

    def delete_task(self, task_id: int) -> None:
        with self._write():
            parent_id = self._get_row(task_id)["parent_id"]
            self._db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            if parent_id is not None:
                self._sync_parent(parent_id)

    def _get_row(self, task_id: int) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT parent_id, due_at FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise KeyError(task_id)
        return row

    def _sync_parent(self, parent_id: int) -> None:
        # done 取 0 或 1。全为 1 时最小值才是 1；没有子任务时保留原状态。
        state = self._db.execute(
            "SELECT MIN(done) FROM tasks WHERE parent_id = ?", (parent_id,)
        ).fetchone()[0]
        if state is not None:
            self._db.execute("UPDATE tasks SET done = ? WHERE id = ?", (state, parent_id))

    def close(self) -> None:
        self._db.close()
