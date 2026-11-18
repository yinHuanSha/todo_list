"""Windows 桌面清单界面。排序规则见 model.py，数据读写见 storage.py。"""

import sqlite3
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox, ttk
from tkinter.font import Font

from date_picker import DatePicker
from model import (
    IMPORTANCE_LABELS,
    URGENCY_LABELS,
    Task,
    rank_tasks,
    score,
    time_description,
    urgency,
)
from storage import TaskStore


BG = "#f4f6f5"
PAPER = "#ffffff"
INK = "#192b2b"
MUTED = "#556a68"
GREEN = "#146051"
DARK = "#163f39"
PALE = "#deeee7"
BORDER = "#d4dfda"
ERROR = "#a03936"
FONT = "Microsoft YaHei UI"
STORAGE_ERRORS = (sqlite3.Error, OSError, KeyError, ValueError)
DATE_FORMAT = "%Y-%m-%d %H:%M"
DEFAULT_DUE_TIME = "23:59"


def deadline_parts(text: str) -> list[str]:
    return text.strip().replace("：", ":").split(maxsplit=1)


def parse_deadline(text: str) -> datetime | None:
    parts = deadline_parts(text)
    if not parts:
        return None
    if len(parts) == 1:
        parts.append(DEFAULT_DUE_TIME)
    return datetime.strptime(" ".join(parts), DATE_FORMAT)


def calendar_fields(text: str, today: date) -> tuple[date, str]:
    parts = deadline_parts(text)
    if not parts:
        return today, DEFAULT_DUE_TIME
    if len(parts) == 1 and ":" in parts[0]:
        return today, parts[0]
    try:
        initial = datetime.strptime(parts[0], "%Y-%m-%d").date()
    except ValueError:
        initial = today
    return initial, parts[1] if len(parts) == 2 else DEFAULT_DUE_TIME


def set_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    root.option_add("*Font", (FONT, 10))
    for name, background, foreground, hover in (
        ("Accent.TButton", GREEN, PAPER, "#0b5042"),
        ("Hero.TButton", PALE, DARK, "#c1e0d2"),
        ("Quiet.TButton", PAPER, INK, "#e7efeb"),
        ("Danger.TButton", PAPER, ERROR, "#f5e9e5"),
    ):
        style.configure(
            name, background=background, foreground=foreground, font=(FONT, 10),
            padding=(14, 7), borderwidth=1, relief="flat", anchor="center",
            bordercolor=background, lightcolor=background, darkcolor=background,
        )
        style.map(
            name,
            background=[("disabled", BG), ("active", hover)],
            foreground=[("disabled", "#778984")],
            bordercolor=[("focus", "#729e91"), ("active", hover)],
            lightcolor=[("active", hover)], darkcolor=[("active", hover)],
        )
    line_height = Font(root, font=(FONT, 10)).metrics("linespace")
    style.configure(
        "Treeview", font=(FONT, 10), background=PAPER, foreground=INK,
        fieldbackground=PAPER, borderwidth=0, rowheight=2 * line_height + 6,
    )
    style.map(
        "Treeview", background=[("selected", PALE)], foreground=[("selected", DARK)]
    )
    style.configure(
        "Treeview.Heading", font=(FONT, 9), foreground=MUTED, background="#edf2ef",
        padding=(8, 8), relief="flat", borderwidth=0,
    )
    style.map("Treeview.Heading", background=[("active", "#edf2ef")])
    style.configure("TEntry", padding=(6, 5), fieldbackground=PAPER)
    style.configure("TCombobox", padding=(6, 5))
    style.map("TCombobox", fieldbackground=[("readonly", PAPER)])


def label(parent, text="", *, size=10, bold=False, fg=INK, bg=BG, **kwargs):
    return tk.Label(
        parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
        bg=bg, fg=fg, bd=0, highlightthickness=0, anchor="w", **kwargs,
    )


class TaskDialog(tk.Toplevel):
    def __init__(self, root, task, on_save):
        super().__init__(root)
        self.withdraw()
        self.on_save = on_save
        self.title("编辑任务" if task else "添加任务")
        self.transient(root)
        self.resizable(False, False)
        self.configure(bg=PAPER)
        body = tk.Frame(self, bg=PAPER, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        label(body, self.title(), size=17, bold=True, bg=PAPER).pack(anchor="w")
        label(body, "任务名称", bg=PAPER).pack(anchor="w", pady=(16, 4))
        self.name_var = tk.StringVar(value=task.title if task else "")
        self.name_entry = ttk.Entry(body, width=38, textvariable=self.name_var)
        self.name_entry.pack(fill="x")
        label(body, "重要程度", bg=PAPER).pack(anchor="w", pady=(12, 4))
        self.importance = ttk.Combobox(body, values=IMPORTANCE_LABELS, state="readonly")
        self.importance.current(task.importance if task else 1)
        self.importance.pack(fill="x")
        label(body, "截止时间（选填）", bg=PAPER).pack(anchor="w", pady=(12, 4))
        self.due_var = tk.StringVar(
            value=task.due_at.isoformat(" ", timespec="minutes") if task and task.due_at else ""
        )
        due_row = tk.Frame(body, bg=PAPER)
        due_row.pack(fill="x")
        self.due_entry = ttk.Entry(due_row, textvariable=self.due_var)
        self.due_entry.pack(side="left", fill="x", expand=True)
        self.calendar = None
        calendar_button = ttk.Button(due_row, text="选日期", style="Quiet.TButton",
                                     command=self.open_calendar)
        calendar_button.pack(side="left", padx=(6, 0))
        calendar_button.bind("<Return>", lambda _: self.open_calendar())
        label(body, "例如 2026-11-23 18：30，只选日期默认 23:59", size=9, fg=MUTED,
              bg=PAPER).pack(anchor="w", pady=(4, 0))
        self.feedback = label(body, size=9, fg=ERROR, bg=PAPER, wraplength=370)
        self.feedback.pack(fill="x", pady=(3, 4))
        actions = tk.Frame(body, bg=PAPER)
        actions.pack(fill="x")
        ttk.Button(actions, text="保存", style="Accent.TButton", command=self.save).pack(
            side="right"
        )
        ttk.Button(actions, text="取消", style="Quiet.TButton", command=self.destroy).pack(
            side="right", padx=6
        )
        self.bind("<Return>", lambda _: self.save())
        self.bind("<Escape>", lambda _: self.destroy())
        self.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - self.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - self.winfo_reqheight()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        self.grab_set()
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def open_calendar(self):
        if self.calendar is not None and self.calendar.winfo_exists():
            self.calendar.lift()
            return "break"
        initial, clock = calendar_fields(self.due_var.get(), date.today())

        def choose(day):
            self.due_var.set(f"{day.isoformat()} {clock}")
            self.feedback.configure(text="")

        self.calendar = DatePicker(self, initial, choose)
        return "break"

    def save(self):
        title = self.name_var.get().strip()
        if not title:
            self.feedback.configure(text="请填写任务名称。")
            self.name_entry.focus_set()
            return "break"
        try:
            due_at = parse_deadline(self.due_var.get())
        except ValueError:
            self.feedback.configure(text="请填写有效的日期和时间，例如 2026-11-20 18:30。")
            self.due_entry.focus_set()
            return "break"
        try:
            self.on_save(title, self.importance.current(), due_at)
        except STORAGE_ERRORS as exc:
            self.feedback.configure(text=f"保存失败。{exc}")
            return "break"
        self.destroy()
        return "break"


class TodoApp:
    def __init__(self, root: tk.Tk, store: TaskStore):
        self.root = root
        self.store = store
        self.show_done = False
        self.dialog = None
        self.focus_refresh = None
        self.best = None
        self.tasks_by_id = {}
        self.last_rows = None
        self.last_selected = {False: None, True: None}
        root.title("待办清单")
        root.geometry("920x640")
        root.minsize(720, 530)
        root.configure(bg=BG)
        set_styles(root)
        outer = tk.Frame(root, bg=BG, padx=24, pady=18)
        outer.pack(fill="both", expand=True)
        self.build_header(outer)
        self.build_recommendation(outer)
        self.build_list(outer)
        self.refresh()
        self.tree.focus_set()
        root.bind("<Control-n>", lambda _: self.open_form())
        root.bind("<Control-Tab>", lambda _: self.switch_list(not self.show_done))
        root.bind("<FocusIn>", self.queue_refresh, add="+")
        root.after(60_000, self.minute_tick)

    def build_header(self, parent):
        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(0, 14))
        mark = tk.Canvas(bar, width=32, height=32, bg=GREEN, bd=0, highlightthickness=0)
        mark.create_line(8, 16, 14, 22, 24, 10, fill=PAPER, width=3, joinstyle="round")
        mark.pack(side="left", padx=(0, 11))
        label(bar, "待办清单", size=21, bold=True).pack(side="left")
        ttk.Button(
            bar, text="＋ 添加任务", style="Accent.TButton", command=self.open_form
        ).pack(side="right")

    def build_recommendation(self, parent):
        hero = tk.Frame(parent, bg=DARK, padx=20, pady=16)
        hero.pack(fill="x")
        hero.columnconfigure(0, weight=1)
        label(hero, "现在先做", size=10, bold=True, fg="#a9d6c5", bg=DARK).grid(
            row=0, column=0, sticky="w"
        )
        self.hero_title = label(hero, size=17, bold=True, fg=PAPER, bg=DARK)
        self.hero_title.grid(row=1, column=0, sticky="ew", pady=(3, 2))
        self.hero_reason = label(hero, fg="#d0e4dd", bg=DARK)
        self.hero_reason.grid(row=2, column=0, sticky="ew")
        self.hero_button = ttk.Button(hero, style="Hero.TButton", command=self.hero_action)
        self.hero_button.grid(row=0, column=1, rowspan=3, sticky="e", padx=(12, 0))
        for field in (self.hero_title, self.hero_reason):
            field.configure(width=1, justify="left")
            field.bind("<Configure>", self.wrap_recommendation)

    def wrap_recommendation(self, event):
        event.widget.configure(wraplength=max(1, event.width - 6))

    def build_list(self, parent):
        tabs = tk.Frame(parent, bg=BG)
        tabs.pack(fill="x", pady=(16, 8))
        self.tab_buttons = {}
        for done in (False, True):
            button = tk.Button(
                tabs, relief="flat", bd=0, font=(FONT, 11, "bold"), cursor="hand2",
                padx=11, pady=4, activebackground=PALE, activeforeground=DARK,
                highlightthickness=0, command=lambda done=done: self.switch_list(done),
            )
            button.pack(side="left", padx=(0, 5))
            self.tab_buttons[done] = button

        panel = tk.Frame(parent, bg=PAPER, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)
        table_area = tk.Frame(panel, bg=PAPER)
        table_area.grid(row=0, column=0, sticky="nsew")
        columns = ("title", "importance", "urgency", "due", "score")
        self.tree = ttk.Treeview(
            table_area, name="tasks", columns=columns, show="headings",
            selectmode="browse", height=5,
        )
        body_font = Font(self.root, font=(FONT, 10))
        heading_font = Font(self.root, font=(FONT, 9))
        # Size columns in the actual display font, including the longest supported
        # overdue duration. Windows display scaling changes glyph widths in pixels.
        contents = (
            ("任务名称", "任务名称", 100),
            ("重要程度", "水水就行", 84),
            ("紧迫程度", "迫切", 84),
            ("截止时间", time_description(datetime.min, datetime.max), 178),
            ("综合分", "4", 68),
        )
        fixed_width = 0
        for name, (heading, sample, base_width) in zip(columns, contents):
            width = max(base_width, heading_font.measure(heading) + 20, body_font.measure(sample) + 12)
            anchor = "w" if name == "title" else "center"
            self.tree.column(name, width=width, minwidth=width, stretch=name == "title", anchor=anchor)
            self.tree.heading(name, text=heading, anchor=anchor)
            fixed_width += width
        self.tree.tag_configure("overdue", foreground=ERROR)
        scrollbar = ttk.Scrollbar(table_area, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        # 48 px outer padding plus panel borders and the scrollbar.
        min_width = max(720, fixed_width + scrollbar.winfo_reqwidth() + 54)
        # Leave space for the list and footer below a wrapped recommendation.
        min_height = max(530, body_font.metrics("linespace") * 25)
        self.root.minsize(min_width, min_height)
        self.blank_hint = label(table_area, fg=MUTED, bg=PAPER)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.update_actions())
        self.tree.bind("<Double-1>", self.edit_at_pointer)
        self.tree.bind("<Return>", lambda _: self.edit_selected())
        self.tree.bind("<space>", lambda _: self.toggle_selected())
        self.tree.bind("<Delete>", lambda _: self.delete_selected())

        tk.Frame(panel, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew")
        foot = tk.Frame(panel, bg=PAPER, padx=9, pady=6)
        foot.grid(row=2, column=0, sticky="ew")
        self.state_button = ttk.Button(foot, style="Quiet.TButton", command=self.toggle_selected)
        self.state_button.pack(side="left")
        self.edit_button = ttk.Button(
            foot, text="编辑", style="Quiet.TButton", command=self.edit_selected
        )
        self.edit_button.pack(side="left", padx=5)
        self.delete_button = ttk.Button(
            foot, text="删除", style="Danger.TButton", command=self.delete_selected
        )
        self.delete_button.pack(side="right")
        self.error_hint = label(parent, size=9, fg=ERROR, wraplength=620)

    def minute_tick(self):
        self.refresh()
        self.root.after(60_000, self.minute_tick)

    def queue_refresh(self, _event):
        if self.focus_refresh is None:
            self.focus_refresh = self.root.after_idle(self.refresh_on_focus)

    def refresh_on_focus(self):
        self.focus_refresh = None
        self.refresh()

    def refresh(self):
        try:
            tasks = self.store.list_tasks()
        except STORAGE_ERRORS as exc:
            self.error_hint.configure(text=f"读取清单失败。{exc}")
            self.error_hint.pack(fill="x", pady=(5, 0))
            return
        self.error_hint.pack_forget()
        now = datetime.now()
        pending = rank_tasks(tasks, now)
        completed = sorted((task for task in tasks if task.done), key=lambda t: -t.id)
        self.tasks_by_id = {task.id: task for task in tasks}
        self.best = pending[0] if pending else None
        self.update_recommendation(now)
        for done, caption, count in ((False, "待办", len(pending)), (True, "已完成", len(completed))):
            active = done == self.show_done
            self.tab_buttons[done].configure(
                text=f"{caption}  {count}", bg=PALE if active else BG,
                fg=DARK if active else MUTED, relief="flat",
            )
        rows = []
        for task in (completed if self.show_done else pending):
            expired = not task.done and task.due_at is not None and task.due_at < now
            due_text = task.due_at.isoformat(" ", timespec="minutes") if task.due_at else "—"
            if expired:
                due_text += "\n" + time_description(task.due_at, now)
            urgency_text = URGENCY_LABELS[urgency(task.due_at, now)]
            rows.append((str(task.id), (task.title, IMPORTANCE_LABELS[task.importance],
                         urgency_text, due_text, score(task, now)), expired))
        self.display_rows(rows)
        self.update_actions()

    def update_recommendation(self, now):
        if self.best is None:
            self.hero_title.configure(text="没有待办任务")
            self.hero_reason.grid_remove()
            self.hero_button.configure(text="添加第一件任务")
            return
        task = self.best
        title = task.title if len(task.title) <= 60 else task.title[:59] + "…"
        self.hero_title.configure(text=title)
        self.hero_reason.configure(
            text=f"{IMPORTANCE_LABELS[task.importance]}  ·  {time_description(task.due_at, now)}"
                 f"  ·  综合 {score(task, now)} 分"
        )
        self.hero_reason.grid()
        self.hero_button.configure(text="标记完成")

    def display_rows(self, rows):
        state = (self.show_done, rows)
        if state == self.last_rows:
            return
        self.last_rows = state
        columns = ("title", "importance", "due") if self.show_done else "#all"
        self.tree.configure(displaycolumns=columns)
        old_ids = self.tree.get_children()
        if old_ids:
            self.tree.delete(*old_ids)
        for iid, values, expired in rows:
            self.tree.insert("", "end", iid=iid, values=values, tags=("overdue",) if expired else ())
        if rows:
            self.blank_hint.place_forget()
            iid = self.last_selected[self.show_done]
            if not iid or not self.tree.exists(iid):
                iid = rows[0][0]
            self.tree.focus(iid)
            self.tree.selection_set(iid)
            self.tree.see(iid)
        elif self.show_done:
            self.blank_hint.configure(text="还没有已完成的任务")
            self.blank_hint.place(relx=.5, rely=.55, anchor="center")
        else:
            self.blank_hint.place_forget()

    def selected_task(self):
        selection = self.tree.selection()
        return self.tasks_by_id.get(int(selection[0])) if selection else None

    def update_actions(self):
        task = self.selected_task()
        if task is not None:
            self.last_selected[self.show_done] = str(task.id)
        state = "normal" if task else "disabled"
        self.state_button.configure(text="恢复待办" if self.show_done else "标记完成", state=state)
        self.edit_button.configure(state=state)
        self.delete_button.configure(state=state)

    def switch_list(self, done):
        self.show_done = done
        self.refresh()
        self.tree.focus_set()
        return "break"

    def hero_action(self):
        if self.best:
            self.change_done(self.best)
        else:
            self.open_form()

    def open_form(self, task: Task | None = None):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.lift()
            return "break"

        def save(title, importance, due_at):
            if task is None:
                self.store.add_task(title, importance, due_at)
                self.show_done = False
            else:
                self.store.update_task(task.id, title, importance, due_at)
            self.refresh()

        self.dialog = TaskDialog(self.root, task, save)
        return "break"

    def edit_selected(self):
        task = self.selected_task()
        if task:
            self.open_form(task)
        return "break"

    def edit_at_pointer(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.edit_selected()
            return "break"

    def toggle_selected(self):
        task = self.selected_task()
        if task:
            self.change_done(task)
        return "break"

    def change_done(self, task):
        try:
            self.store.set_done(task.id, not task.done)
        except STORAGE_ERRORS as exc:
            messagebox.showerror("更新失败", str(exc), parent=self.root)
        self.refresh()

    def delete_selected(self):
        task = self.selected_task()
        if task and messagebox.askyesno(
            "删除任务", f"确定永久删除“{task.title}”吗？", parent=self.root, default="no"
        ):
            try:
                self.store.delete_task(task.id)
            except STORAGE_ERRORS as exc:
                messagebox.showerror("删除失败", str(exc), parent=self.root)
            self.refresh()
        return "break"
