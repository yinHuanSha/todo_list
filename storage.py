"""用 SQLite 保存待办任务，每次修改都独立提交。"""

import os
import sqlite3
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
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                    importance INTEGER NOT NULL CHECK (importance IN (0, 1, 2)),
                    due_at TEXT,
                    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0, 1))
                )"""
            )
        except sqlite3.Error:
            self._db.close()
            raise

    def list_tasks(self) -> list[Task]:
        rows = self._db.execute(
            "SELECT id, title, importance, due_at, done FROM tasks ORDER BY id"
        )
        return [
            Task(
                id=row["id"],
                title=row["title"],
                importance=row["importance"],
                due_at=datetime.fromisoformat(row["due_at"]) if row["due_at"] else None,
                done=bool(row["done"]),
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

    def update_task(
        self, task_id: int, title: str, importance: int, due_at: datetime | None
    ) -> None:
        title, importance, due_at = normalize_fields(title, importance, due_at)
        self._change_task(
            "UPDATE tasks SET title = ?, importance = ?, due_at = ? WHERE id = ?",
            task_id,
            (title, importance, due_at.isoformat() if due_at else None),
        )

    def set_done(self, task_id: int, done: bool) -> None:
        self._change_task("UPDATE tasks SET done = ? WHERE id = ?", task_id, (int(done),))

    def delete_task(self, task_id: int) -> None:
        self._change_task("DELETE FROM tasks WHERE id = ?", task_id)

    def _change_task(self, sql: str, task_id: int, values: tuple = ()) -> None:
        with self._db:
            cursor = self._db.execute(sql, (*values, task_id))
            if cursor.rowcount == 0:
                raise KeyError(task_id)

    def close(self) -> None:
        self._db.close()
