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


def checkbox_images(root, size):
    """Create the two clickable tree icons at the display's text scale."""
    images = {}
    for checked in (False, True):
        image = tk.PhotoImage(master=root, width=size + 5, height=size)
        image.put(GREEN if checked else MUTED, to=(1, 1, size-1, size-1))
        if checked:
            # Draw two strokes as a check at the same resolution as the box.
            for x in range(size // 5, size * 4 // 5):
                y = int(size * .70 - abs(x - size * .42))
                image.put(PAPER, to=(x, y, x + 1, y + max(2, size // 8)))
        else:
            image.put(PAPER, to=(3, 3, size-3, size-3))
        images[checked] = image
    return images


class TaskDialog(tk.Toplevel):
    def __init__(self, root, task, on_save, parent_task=None):
        super().__init__(root)
        self.withdraw()
        self.on_save = on_save
        self.parent_task = parent_task
        kind = "子事项" if parent_task else "任务"
        self.title(("编辑" if task else "添加") + kind)
        self.transient(root)
        self.resizable(False, False)
        self.configure(bg=PAPER)
        body = tk.Frame(self, bg=PAPER, padx=24, pady=20)
        body.pack(fill="both", expand=True)
        label(body, self.title(), size=17, bold=True, bg=PAPER).pack(anchor="w")
        if parent_task:
            label(body, f"所属任务：{parent_task.title}", fg=MUTED, bg=PAPER,
                  wraplength=350, justify="left").pack(anchor="w", pady=(5, 0))
        label(body, kind + "名称", bg=PAPER).pack(anchor="w", pady=(16, 4))
        self.name_var = tk.StringVar(value=task.title if task else "")
        self.name_entry = ttk.Entry(body, width=38, textvariable=self.name_var)
        self.name_entry.pack(fill="x")
        label(body, "重要程度", bg=PAPER).pack(anchor="w", pady=(12, 4))
        self.importance = ttk.Combobox(body, values=IMPORTANCE_LABELS, state="readonly")
        self.importance.current(task.importance if task else 1)
        self.importance.pack(fill="x")
        if parent_task:
            deadline = parent_task.due_at
            deadline_text = deadline.isoformat(" ", timespec="minutes") if deadline else "未设截止时间"
            label(body, "截止时间（随所属任务）", bg=PAPER).pack(anchor="w", pady=(12, 4))
            label(body, deadline_text, fg=MUTED, bg=PAPER).pack(anchor="w")
        else:
            self.build_deadline_field(body, task)
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

    def build_deadline_field(self, body, task):
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
        due_at = None
        if self.parent_task is None:
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
        self.children = {}
        self.expanded = {}
        self.reveal_group = None
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
        root.bind("<Control-Shift-N>", lambda _: self.add_child())
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
        columns = ("importance", "urgency", "due", "score")
        self.tree = ttk.Treeview(
            table_area, name="tasks", columns=columns, show="tree headings",
            selectmode="browse", height=5,
        )
        body_font = Font(self.root, font=(FONT, 10))
        heading_font = Font(self.root, font=(FONT, 9))
        # Size columns in the actual display font, including the longest supported
        # overdue duration. Windows display scaling changes glyph widths in pixels.
        contents = (
            ("任务名称", "任务名称", 160),
            ("重要程度", "水水就行", 84),
            ("紧迫程度", "迫切", 84),
            ("截止时间", time_description(datetime.min, datetime.max), 178),
            ("优先分", "10/10", 68),
        )
        fixed_width = 0
        for name, (heading, sample, base_width) in zip(("#0", *columns), contents):
            width = max(base_width, heading_font.measure(heading) + 20, body_font.measure(sample) + 12)
            anchor = "w" if name == "#0" else "center"
            self.tree.column(name, width=width, minwidth=width, stretch=name == "#0", anchor=anchor)
            self.tree.heading(name, text=heading, anchor=anchor)
            fixed_width += width
        self.tree.tag_configure("overdue", foreground=ERROR)
        self.tree.tag_configure("group", foreground=DARK, font=(FONT, 10, "bold"))
        self.tree.tag_configure("finished", foreground=MUTED)
        self.checkboxes = checkbox_images(self.root, max(15, body_font.metrics("linespace") - 2))
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
        for event in ("<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tree.bind(event, lambda _: self.root.after_idle(self.update_actions))
        self.tree.bind("<Button-1>", self.click_checkbox)
        self.tree.bind("<Double-1>", self.edit_at_pointer)
        self.tree.bind("<Return>", lambda _: self.edit_selected())
        self.tree.bind("<space>", lambda _: self.toggle_selected())
        self.tree.bind("<Delete>", lambda _: self.delete_selected())

        tk.Frame(panel, bg=BORDER, height=1).grid(row=1, column=0, sticky="ew")
        foot = tk.Frame(panel, bg=PAPER, padx=9, pady=6)
        foot.grid(row=2, column=0, sticky="ew")
        self.state_button = ttk.Button(foot, width=9, style="Quiet.TButton", command=self.toggle_selected)
        self.state_button.pack(side="left")
        self.edit_button = ttk.Button(
            foot, text="编辑", width=4, style="Quiet.TButton", command=self.edit_selected
        )
        self.edit_button.pack(side="left", padx=5)
        self.subtask_button = ttk.Button(
            foot, name="add_child", text="添加子事项", width=9, style="Quiet.TButton", command=self.add_child
        )
        self.subtask_button.pack(side="left")
        self.delete_button = ttk.Button(
            foot, text="删除", width=4, style="Danger.TButton", command=self.delete_selected
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
        self.tasks_by_id = {task.id: task for task in tasks}
        self.children = {}
        for task in tasks:
            if task.parent_id is not None:
                self.children.setdefault(task.parent_id, []).append(task)
        # A group takes the place of its highest-ranked actionable child.
        pending_roots = list(dict.fromkeys(
            task.parent_id if task.parent_id is not None else task.id for task in pending
        ))
        done_roots = sorted(
            (task.id for task in tasks if task.parent_id is None and task.done), reverse=True
        )
        self.best = pending[0] if pending else None
        self.update_recommendation(now)
        for done, caption, count in ((False, "待办", len(pending_roots)), (True, "已完成", len(done_roots))):
            active = done == self.show_done
            self.tab_buttons[done].configure(
                text=f"{caption}  {count}", bg=PALE if active else BG,
                fg=DARK if active else MUTED, relief="flat",
            )
        rows = []
        positions = {task.id: index for index, task in enumerate(pending)}
        for root_id in (done_roots if self.show_done else pending_roots):
            children = sorted(self.children.get(root_id, ()),
                              key=lambda child: (child.done, positions.get(child.id, child.id)))
            root_task = self.tasks_by_id[root_id]
            rows.append(self.make_row(root_task, now, priority_source=children[0] if children else root_task))
            rows.extend(self.make_row(child, now) for child in children)
        self.display_rows(rows)
        self.update_actions()

    def make_row(self, task, now, *, priority_source=None):
        children = self.children.get(task.id)
        # 子事项共用截止时间，排在最前的待办子事项也具有最高的重要程度。
        priority_source = priority_source or task
        title = task.title
        due = task.due_at.isoformat(" ", timespec="minutes") if task.due_at else "—"
        urgent = URGENCY_LABELS[urgency(task.due_at, now)]
        points = "—" if task.done else f"{score(priority_source, now)}/10"
        tag = ""
        if children:
            title += f"\n已完成 {sum(child.done for child in children)}/{len(children)}"
            tag = "group"
        if task.done:
            urgent = "已完成"
            if not children:
                tag = "finished"
        elif task.due_at and task.due_at < now:
            due += "\n" + time_description(task.due_at, now)
            if not children:
                tag = "overdue"
        importance = "—" if children and task.done else IMPORTANCE_LABELS[priority_source.importance]
        return task, title, (importance, urgent, due, points), tag

    def update_recommendation(self, now):
        if self.best is None:
            self.hero_title.configure(text="没有待办任务")
            self.hero_reason.grid_remove()
            self.hero_button.configure(text="添加第一件任务")
            return
        task = self.best
        title = task.title if len(task.title) <= 60 else task.title[:59] + "…"
        self.hero_title.configure(text=title)
        context = ""
        if task.parent_id is not None:
            parent_title = self.tasks_by_id[task.parent_id].title
            if len(parent_title) > 30:
                parent_title = parent_title[:29] + "…"
            context = f"所属任务：{parent_title}  ·  "
        self.hero_reason.configure(
            text=f"{context}{IMPORTANCE_LABELS[task.importance]}  ·  {time_description(task.due_at, now)}"
                 f"  ·  优先分 {score(task, now)}/10"
        )
        self.hero_reason.grid()
        self.hero_button.configure(text="标记完成")

    def display_rows(self, rows):
        state = (self.show_done, rows)
        if state == self.last_rows and self.reveal_group is None:
            return
        self.last_rows = state
        columns = ("importance", "due") if self.show_done else "#all"
        self.tree.configure(displaycolumns=columns)
        old_ids = self.tree.get_children()
        for iid in old_ids:
            if self.tree.get_children(iid):
                self.expanded[int(iid)] = bool(self.tree.item(iid, "open"))
        if self.reveal_group is not None:
            self.expanded[self.reveal_group] = True
            self.reveal_group = None
        if old_ids:
            self.tree.delete(*old_ids)
        for task, title, values, tag in rows:
            is_child = task.parent_id is not None
            self.tree.insert(
                str(task.parent_id) if is_child else "", "end", iid=str(task.id),
                text=title, values=values, tags=(tag,) if tag else (),
                image=self.checkboxes[task.done] if is_child else "",
                open=self.expanded.get(task.id, False),
            )
        if rows:
            self.blank_hint.place_forget()
            iid = self.last_selected[self.show_done]
            if not iid or not self.tree.exists(iid):
                iid = str(rows[0][0].id)
            parent = self.tree.parent(iid)
            if parent and not self.tree.item(parent, "open"):
                iid = parent
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
        if task and task.id in self.children:
            action = "收起子事项" if self.tree.item(str(task.id), "open") else "展开子事项"
        else:
            action = "恢复待办" if task and task.done else "标记完成"
        self.state_button.configure(text=action, state=state)
        self.edit_button.configure(state=state)
        self.subtask_button.configure(state="normal" if task and task.parent_id is None else "disabled")
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

    def add_child(self):
        parent = self.selected_task()
        if parent is not None and parent.parent_id is None:
            self.open_form(parent_task=parent)
        return "break"

    def open_form(self, task: Task | None = None, parent_task: Task | None = None):
        if self.dialog is not None and self.dialog.winfo_exists():
            self.dialog.lift()
            return "break"

        def save(title, importance, due_at):
            if parent_task and task is None:
                self.store.add_subtask(parent_task.id, title, importance)
                self.show_done = False
                self.last_selected[False] = str(parent_task.id)
                self.reveal_group = parent_task.id
            elif parent_task:
                self.store.update_subtask(task.id, title, importance)
            elif task is None:
                self.store.add_task(title, importance, due_at)
                self.show_done = False
            else:
                self.store.update_task(task.id, title, importance, due_at)
            self.refresh()

        self.dialog = TaskDialog(self.root, task, save, parent_task)
        return "break"

    def edit_selected(self):
        task = self.selected_task()
        if task:
            self.open_form(task, self.tasks_by_id.get(task.parent_id))
        return "break"

    def edit_at_pointer(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            element = self.tree.identify_element(event.x, event.y)
            if element.endswith(("image", "indicator")):
                return "break"
            self.tree.selection_set(iid)
            self.edit_selected()
            return "break"

    def click_checkbox(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and self.tree.identify_element(event.x, event.y).endswith("image"):
            task = self.tasks_by_id[int(iid)]
            if task.parent_id is not None:
                self.tree.focus_set()
                self.tree.focus(iid)
                self.tree.selection_set(iid)
                self.last_selected[self.show_done] = iid
                self.change_done(task)
                return "break"

    def toggle_selected(self):
        task = self.selected_task()
        if task and task.id in self.children:
            iid = str(task.id)
            self.tree.item(iid, open=not self.tree.item(iid, "open"))
            self.update_actions()
        elif task:
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
        if task is None:
            return "break"
        kind = "子事项" if task.parent_id is not None else "任务"
        children = self.children.get(task.id, ())
        count = len(children)
        targets = f"“{task.title}”及其全部 {count} 个子事项" if count else f"“{task.title}”"
        prompt = f"确定永久删除{targets}吗？"
        if children:
            names = [child.title if len(child.title) <= 40 else child.title[:39] + "…"
                     for child in children[:5]]
            prompt += "\n\n" + "\n".join("• " + title for title in names)
            if count > len(names):
                prompt += f"\n另有 {count - len(names)} 个子事项"
        if messagebox.askyesno(f"删除{kind}", prompt,
                               parent=self.root, default="no"):
            try:
                self.store.delete_task(task.id)
            except STORAGE_ERRORS as exc:
                messagebox.showerror("删除失败", str(exc), parent=self.root)
            self.refresh()
        return "break"
