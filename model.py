"""任务及其优先级规则。所有比较共用调用者传入的本地时间。"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta


IMPORTANCE_LABELS = ("水水就行", "一般", "重要")
URGENCY_LABELS = ("轻松", "一般", "迫切")
URGENT_WINDOW = timedelta(hours=24)
NORMAL_WINDOW = timedelta(hours=72)


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    importance: int
    due_at: datetime | None
    done: bool = False


def normalize_fields(
    title: str, importance: int, due_at: datetime | None
) -> tuple[str, int, datetime | None]:
    if not isinstance(title, str) or not title.strip():
        raise ValueError("请输入任务名称。")
    if type(importance) is not int or importance not in range(len(IMPORTANCE_LABELS)):
        raise ValueError("请选择有效的重要程度。")
    if due_at is not None and (
        not isinstance(due_at, datetime) or due_at.tzinfo is not None
    ):
        raise ValueError("截止时间应为本地日期和时间。")
    return title.strip(), importance, due_at


def urgency(due_at: datetime | None, now: datetime) -> int:
    if due_at is None:
        return 0
    remaining = due_at - now
    if remaining <= URGENT_WINDOW:
        return 2
    if remaining <= NORMAL_WINDOW:
        return 1
    return 0


def score(task: Task, now: datetime) -> int:
    return task.importance + urgency(task.due_at, now)


def rank_tasks(tasks: Iterable[Task], now: datetime) -> list[Task]:
    def sort_key(task: Task):
        return (
            -score(task, now),
            -task.importance,
            task.due_at is None,
            task.due_at or datetime.max,
            task.id,
        )

    return sorted((task for task in tasks if not task.done), key=sort_key)


def time_description(due_at: datetime | None, now: datetime) -> str:
    if due_at is None:
        return "未设截止时间"
    if due_at == now:
        return "现在到期"

    minutes = abs(due_at - now) // timedelta(minutes=1)
    if minutes == 0:
        duration = "不到 1 分钟"
    else:
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        parts = []
        if days:
            parts.append(f"{days} 天")
        if hours:
            parts.append(f"{hours} 小时")
        if minutes:
            parts.append(f"{minutes} 分钟")
        duration = " ".join(parts)
    if due_at < now:
        return f"已逾期 {duration}"
    return f"距截止还有 {duration}"
