"""双击运行的桌面入口，也可以使用 python main.py 启动。"""

import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from storage import TaskStore
from ui import TodoApp


def main() -> None:
    if sys.platform == "win32":
        from ctypes import windll

        windll.user32.SetProcessDPIAware()

    root = tk.Tk()
    if sys.platform == "win32":
        root.iconbitmap(default=str(Path(__file__).with_name("todo.ico")))
    try:
        store = TaskStore()
    except (OSError, sqlite3.Error) as error:
        root.withdraw()
        messagebox.showerror("无法打开待办清单", f"打开本地数据库失败。\n\n{error}", parent=root)
        root.destroy()
        return

    try:
        TodoApp(root, store)
        root.mainloop()
    finally:
        store.close()


if __name__ == "__main__":
    main()
