"""为任务表单提供可以用鼠标或键盘操作的本地日历。"""

import calendar
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import ttk


class DatePicker(tk.Toplevel):
    def __init__(self, parent, initial: date, on_select: Callable[[date], None]):
        super().__init__(parent)
        self.withdraw()
        self.title("选择日期")
        self.transient(parent)
        self.resizable(False, False)
        self.previous_focus = parent.focus_get()
        self.previous_grab = parent.grab_current()
        self.closed = False
        self.choosing = False
        self.initial = initial
        self.cursor = initial
        self.on_select = on_select
        self.day_buttons = {}
        bg = parent.cget("background")
        panel = tk.Frame(self, bg=bg, padx=12, pady=12)
        panel.pack(fill="both", expand=True)

        nav = tk.Frame(panel, bg=bg)
        nav.pack(fill="x", pady=(0, 6))
        self.previous_button = ttk.Button(
            nav, text="上个月", width=6, style="Quiet.TButton", padding=(4, 3),
            command=lambda: self.move_month(-1),
        )
        self.previous_button.pack(side="left")
        self.next_button = ttk.Button(
            nav, text="下个月", width=6, style="Quiet.TButton", padding=(4, 3),
            command=lambda: self.move_month(1),
        )
        self.next_button.pack(side="right")
        self.month_label = tk.Label(nav, bg=bg, font=("Microsoft YaHei UI", 11, "bold"))
        self.month_label.pack(expand=True, fill="x", padx=6)

        self.grid_frame = tk.Frame(panel, bg=bg)
        self.grid_frame.pack(fill="x")
        for column, name in enumerate("一二三四五六日"):
            self.grid_frame.columnconfigure(column, weight=1, uniform="days")
            tk.Label(self.grid_frame, text=name, bg=bg, fg="#556a68").grid(
                row=0, column=column, pady=3
            )
        self.today_button = ttk.Button(
            panel, text="今天", style="Quiet.TButton", command=lambda: self.select_day(date.today())
        )
        self.today_button.pack(anchor="e", pady=(6, 0))
        self.draw_month()
        self.bind("<Escape>", lambda _: self.dismiss())
        self.bind("<Return>", self.activate_button)
        self.bind("<KP_Enter>", self.activate_button)
        self.bind("<Prior>", lambda _: self.move_month(-1))
        self.bind("<Next>", lambda _: self.move_month(1))
        self.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.tk.call("tk::PlaceWindow", self, "widget", parent)
        if self.tk.call("tk", "windowingsystem") == "win32":
            self.fit_to_parent_monitor(parent)
        self.grab_set()
        self.day_buttons[initial.day].focus_set()

    def fit_to_parent_monitor(self, parent):
        """Keep the title bar and popup inside the parent's monitor work area."""
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD),
            ]

        self.update_idletasks()
        api = ctypes.windll.user32
        parent_hwnd = wintypes.HWND(int(parent.frame(), 0))
        popup_hwnd = wintypes.HWND(int(self.frame(), 0))
        api.MonitorFromWindow.restype = wintypes.HANDLE
        monitor = wintypes.HANDLE(api.MonitorFromWindow(parent_hwnd, 2))
        info = MonitorInfo(size=ctypes.sizeof(MonitorInfo))
        owner = wintypes.RECT()
        popup = wintypes.RECT()
        if not (api.GetMonitorInfoW(monitor, ctypes.byref(info))
                and api.GetWindowRect(parent_hwnd, ctypes.byref(owner))
                and api.GetWindowRect(popup_hwnd, ctypes.byref(popup))):
            return
        width, height = popup.right - popup.left, popup.bottom - popup.top
        x = (owner.left + owner.right - width) // 2
        y = (owner.top + owner.bottom - height) // 2
        x = max(info.work.left, min(x, info.work.right - width))
        y = max(info.work.top, min(y, info.work.bottom - height))
        # Preserve size, Z order and activation. Native positions may be negative.
        api.SetWindowPos(popup_hwnd, None, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)

    def draw_month(self):
        for button in self.day_buttons.values():
            button.destroy()
        self.day_buttons.clear()
        year, month = self.cursor.year, self.cursor.month
        self.month_label.configure(text=f"{year} 年 {month} 月")
        self.previous_button.configure(state="disabled" if (year, month) == (1, 1) else "normal")
        self.next_button.configure(state="disabled" if (year, month) == (9999, 12) else "normal")
        weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(year, month)
        for row, week in enumerate(weeks, start=1):
            for column, day in enumerate(week):
                if day == 0:
                    continue
                value = date(year, month, day)
                button = ttk.Button(
                    self.grid_frame, name=f"day{day}", text=str(day), width=3,
                    padding=(2, 3), style="Accent.TButton" if value == self.initial else "Quiet.TButton",
                    command=lambda value=value: self.select_day(value),
                )
                button.grid(row=row, column=column, sticky="nsew", padx=1, pady=1)
                button.bind("<FocusIn>", lambda _, value=value: self.set_cursor(value))
                for key, offset in (("Left", -1), ("Right", 1), ("Up", -7), ("Down", 7)):
                    button.bind(f"<{key}>", lambda _, offset=offset: self.move_days(offset))
                self.day_buttons[day] = button
        # Reserve six weeks even for short months so navigation stays in place.
        height = self.day_buttons[1].winfo_reqheight() + 2
        for row in range(1, 7):
            self.grid_frame.rowconfigure(row, minsize=height)

    def set_cursor(self, value):
        self.cursor = value

    def focus_date(self, value):
        changed_month = (value.year, value.month) != (self.cursor.year, self.cursor.month)
        self.cursor = value
        if changed_month:
            self.draw_month()
        self.day_buttons[value.day].focus_set()
        return "break"

    def move_days(self, step):
        target = max(date.min.toordinal(), min(date.max.toordinal(), self.cursor.toordinal() + step))
        return self.focus_date(date.fromordinal(target))

    def move_month(self, step):
        month_number = (self.cursor.year - 1) * 12 + self.cursor.month - 1 + step
        if 0 <= month_number < date.max.year * 12:
            year_index, month_index = divmod(month_number, 12)
            year, month = year_index + 1, month_index + 1
            day = min(self.cursor.day, calendar.monthrange(year, month)[1])
            self.focus_date(date(year, month, day))
        return "break"

    def activate_button(self, event):
        if isinstance(event.widget, ttk.Button):
            event.widget.invoke()
        return "break"

    def select_day(self, value):
        if self.choosing or self.closed:
            return
        self.choosing = True
        try:
            self.on_select(value)
        finally:
            self.destroy()

    def dismiss(self):
        self.destroy()
        return "break"

    def destroy(self):
        if self.closed:
            return
        self.closed = True
        super().destroy()
        if self.previous_grab is not None and self.previous_grab.winfo_exists():
            self.previous_grab.grab_set()
        if self.previous_focus is not None and self.previous_focus.winfo_exists():
            self.previous_focus.focus_set()
