"""Piezas visuales reutilizables y estilo común."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Protocol

from scrapcv.ports import ProgressListener

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_TITLE = ("Segoe UI Semibold", 15)
MONO = ("Consolas", 10)
ACCENT = "#1f3864"
MUTED = "#5b6b82"


class TaskStarter(Protocol):
    """Lo que una vista necesita para lanzar trabajo en segundo plano."""

    def __call__(self, name: str, work: Callable[[ProgressListener], Any], on_success: Callable[[Any], None] | None = None) -> None: ...


def apply_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    root.option_add("*Font", FONT)
    style.configure(".", font=FONT)
    style.configure("Title.TLabel", font=FONT_TITLE, foreground=ACCENT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Section.TLabelframe.Label", font=FONT_BOLD, foreground=ACCENT)
    style.configure("Accent.TButton", font=FONT_BOLD)
    style.configure("Treeview", rowheight=24)
    style.configure("Treeview.Heading", font=FONT_BOLD)


def scrolled_text(parent: tk.Widget, **kwargs) -> tuple[ttk.Frame, tk.Text]:
    frame = ttk.Frame(parent)
    text = tk.Text(frame, wrap="word", relief="solid", borderwidth=1, padx=8, pady=6, **kwargs)
    bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=bar.set)
    text.grid(row=0, column=0, sticky="nsew")
    bar.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, text


def scrolled_tree(parent: tk.Widget, columns: dict[str, tuple[str, int]], height: int = 10) -> tuple[ttk.Frame, ttk.Treeview]:
    """columns: id -> (título, ancho)."""
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=list(columns), show="headings", height=height, selectmode="browse")
    for column, (title, width) in columns.items():
        tree.heading(column, text=title, anchor="w")
        tree.column(column, width=width, anchor="w", stretch=column == next(iter(columns)))
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.grid(row=0, column=0, sticky="nsew")
    bar.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, tree


def set_text(widget: tk.Text, content: str, readonly: bool = True) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", content)
    if readonly:
        widget.configure(state="disabled")
