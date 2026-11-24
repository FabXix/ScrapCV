"""Piezas visuales reutilizables y el tema de la aplicación.

Tema propio sobre «clam» (incluido en Tk): fondo gris muy claro, tarjetas
blancas, un solo color de acento y tipografía Segoe UI. Sin dependencias extra.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Protocol

from scrapcv.ports import ProgressListener

FONT = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI Semibold", 10)
FONT_H2 = ("Segoe UI Semibold", 12)
FONT_TITLE = ("Segoe UI Semibold", 17)
FONT_BIG = ("Segoe UI Semibold", 30)
MONO = ("Consolas", 10)

BG = "#f3f5f9"
SURFACE = "#ffffff"
BORDER = "#dfe4ec"
INK = "#1b2333"
MUTED = "#667085"
ACCENT = "#2f5bea"
ACCENT_DARK = "#2347c5"
ACCENT_SOFT = "#e8eeff"
OK = "#12805c"
WARN = "#b54708"
DANGER = "#b42318"


class TaskStarter(Protocol):
    """Lo que una vista necesita para lanzar trabajo en segundo plano."""

    def __call__(self, name: str, work: Callable[[ProgressListener], Any], on_success: Callable[[Any], None] | None = None) -> None: ...


def apply_style(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=BG)
    # Solo widgets Tk clásicos: un «*Font» global fija -font en los ttk.Label y anula la fuente de su estilo.
    for widget in ("Text", "Listbox", "Menu"):
        root.option_add(f"*{widget}.font", FONT)
    root.option_add("*TCombobox*Listbox.font", FONT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    style.configure(".", font=FONT, background=BG, foreground=INK, bordercolor=BORDER, lightcolor=BG,
                    darkcolor=BG, troughcolor=BORDER, focuscolor=ACCENT, selectbackground=ACCENT,
                    selectforeground="#ffffff", insertcolor=INK)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1, bordercolor=BORDER)
    style.configure("Header.TFrame", background=SURFACE)
    style.configure("Inner.TFrame", background=SURFACE, borderwidth=0)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Title.TLabel", font=FONT_TITLE, foreground=INK, background=SURFACE)
    style.configure("Subtitle.TLabel", foreground=MUTED, background=SURFACE)
    style.configure("Muted.TLabel", foreground=MUTED, font=FONT_SMALL)
    for name, bg in (("Card", SURFACE), ("Header", SURFACE)):
        style.configure(f"{name}.TLabel", background=bg, foreground=INK)
        style.configure(f"{name}Muted.TLabel", background=bg, foreground=MUTED, font=FONT_SMALL)
        style.configure(f"{name}Heading.TLabel", background=bg, foreground=INK, font=FONT_H2)
        style.configure(f"{name}Bold.TLabel", background=bg, foreground=INK, font=FONT_BOLD)
    style.configure("Score.TLabel", background=SURFACE, foreground=ACCENT, font=FONT_BIG)
    style.configure("Pill.TLabel", background=ACCENT_SOFT, foreground=ACCENT, font=FONT_SMALL, padding=(8, 2))

    style.configure("TLabelframe", background=SURFACE, bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=SURFACE, foreground=INK, font=FONT_H2)
    style.configure("Section.TLabelframe", background=SURFACE, bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("Section.TLabelframe.Label", background=SURFACE, foreground=INK, font=FONT_H2)

    style.configure("TButton", background=SURFACE, foreground=INK, bordercolor=BORDER, lightcolor=SURFACE,
                    darkcolor=SURFACE, padding=(12, 6), relief="solid", borderwidth=1, focusthickness=0)
    style.map("TButton", background=[("pressed", "#e9edf3"), ("active", "#f4f6fa")],
              bordercolor=[("active", "#c5ccd8")])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", bordercolor=ACCENT,
                    lightcolor=ACCENT, darkcolor=ACCENT, font=FONT_BOLD, padding=(14, 8))
    style.map("Accent.TButton", background=[("disabled", "#a9b8ee"), ("pressed", ACCENT_DARK), ("active", ACCENT_DARK)],
              bordercolor=[("active", ACCENT_DARK)], foreground=[("disabled", "#ffffff")])
    style.configure("Ghost.TButton", background=BG, bordercolor=BG, lightcolor=BG, darkcolor=BG, padding=(8, 4))
    for name, bg in (("Link", SURFACE), ("LinkBg", BG)):
        style.configure(f"{name}.TButton", background=bg, foreground=ACCENT, bordercolor=bg, lightcolor=bg,
                        darkcolor=bg, relief="flat", borderwidth=0, padding=(0, 2), font=FONT_BOLD)
        style.map(f"{name}.TButton", background=[("active", bg), ("pressed", bg)], foreground=[("active", ACCENT_DARK)],
                  bordercolor=[("active", bg)])
    style.configure("Step.TLabel", background=ACCENT_SOFT, foreground=INK, padding=(12, 8))
    style.configure("Empty.TLabel", background=SURFACE, foreground=MUTED, font=("Segoe UI", 11), justify="center")
    style.map("Ghost.TButton", background=[("active", "#e6eaf1")])

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(widget, fieldbackground=SURFACE, background=SURFACE, bordercolor=BORDER, lightcolor=SURFACE,
                        darkcolor=SURFACE, padding=(6, 4), arrowcolor=MUTED)
        style.map(widget, bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  fieldbackground=[("readonly", SURFACE), ("disabled", "#f0f2f5")])
    for widget, bg in (("TCheckbutton", BG), ("TRadiobutton", BG), ("Card.TCheckbutton", SURFACE),
                       ("Card.TRadiobutton", SURFACE)):
        style.configure(widget, background=bg, indicatorbackground=SURFACE, indicatorforeground=ACCENT,
                        indicatorsize=16, indicatormargin=(0, 0, 8, 0))
        style.map(widget, background=[("active", bg)], indicatorbackground=[("selected", SURFACE)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(16, 8, 16, 0))
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 8), borderwidth=0, font=FONT_BOLD)
    style.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", ACCENT)],
              lightcolor=[("selected", SURFACE)], bordercolor=[("selected", BORDER)])

    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK, rowheight=28,
                    bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", INK)])
    style.configure("Treeview.Heading", background="#f7f8fb", foreground=MUTED, font=FONT_BOLD, relief="flat",
                    bordercolor=BORDER, padding=(6, 6))
    style.map("Treeview.Heading", background=[("active", "#eef1f6")])

    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor="#e6eaf1", bordercolor="#e6eaf1",
                    lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
    style.configure("Match.Horizontal.TProgressbar", background=ACCENT, troughcolor=ACCENT_SOFT,
                    bordercolor=ACCENT_SOFT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)
    style.configure("Vertical.TScrollbar", background=BG, troughcolor=SURFACE, bordercolor=SURFACE,
                    arrowcolor=MUTED, lightcolor=BG, darkcolor=BG, gripcount=0)
    style.configure("TPanedwindow", background=BG)
    style.configure("TSeparator", background=BORDER)


def card(parent: tk.Widget, padding: int | tuple = 14) -> ttk.Frame:
    return ttk.Frame(parent, style="Card.TFrame", padding=padding)


def autowrap(label: ttk.Label) -> ttk.Label:
    """Ajusta el texto al ancho real de la etiqueta (respeta el escalado de pantalla)."""
    label.configure(wraplength=240)  # tamaño inicial pequeño para no ensanchar la columna
    label.bind("<Configure>", lambda e: label.configure(wraplength=max(80, e.width - 4)), add="+")
    return label


def scrolled_text(parent: tk.Widget, **kwargs) -> tuple[ttk.Frame, tk.Text]:
    frame = ttk.Frame(parent, style="Card.TFrame", padding=1)
    options = dict(wrap="word", relief="flat", borderwidth=0, padx=12, pady=10, background=SURFACE, foreground=INK,
                   insertbackground=INK, selectbackground=ACCENT_SOFT, selectforeground=INK, highlightthickness=0,
                   spacing1=1, spacing3=1)
    options.update(kwargs)
    text = tk.Text(frame, **options)
    bar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=bar.set)
    text.grid(row=0, column=0, sticky="nsew")
    bar.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, text


def scrolled_tree(parent: tk.Widget, columns: dict[str, tuple[str, int]], height: int = 10) -> tuple[ttk.Frame, ttk.Treeview]:
    """columns: id -> (título, ancho)."""
    frame = ttk.Frame(parent, style="Card.TFrame", padding=1)
    tree = ttk.Treeview(frame, columns=list(columns), show="headings", height=height, selectmode="browse")
    scale = max(1.0, parent.winfo_fpixels("1i") / 96)  # anchos pensados a 100 %; se ajustan al escalado de Windows
    for column, (title, width) in columns.items():
        tree.heading(column, text=title, anchor="w")
        tree.column(column, width=int(width * scale), minwidth=int(40 * scale), anchor="w",
                    stretch=column == next(iter(columns)))
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


def placeholder(widget: tk.Text, hint: str) -> None:
    """Texto de ayuda gris en un tk.Text vacío; desaparece al enfocarlo."""
    widget.tag_configure("placeholder", foreground="#98a2b3")

    def show(_e=None) -> None:
        if not widget.get("1.0", "end-1c").strip():
            widget.delete("1.0", "end")
            widget.insert("1.0", hint, "placeholder")

    def hide(_e=None) -> None:
        if widget.tag_ranges("placeholder"):
            widget.delete("1.0", "end")

    widget.bind("<FocusIn>", hide, add="+")
    widget.bind("<FocusOut>", show, add="+")
    show()


def text_value(widget: tk.Text) -> str:
    """Contenido real de un tk.Text (sin el texto de ayuda)."""
    return "" if widget.tag_ranges("placeholder") else widget.get("1.0", "end-1c")


class Tooltip:
    """Ayuda breve al pasar el mouse sobre un control."""

    def __init__(self, widget: tk.Widget, text: str, delay_ms: int = 450) -> None:
        self._widget, self._text, self._delay = widget, text, delay_ms
        self._job: str | None = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._job = self._widget.after(self._delay, self._show)

    def _show(self) -> None:
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 8
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 6
        self._tip = tip = tk.Toplevel(self._widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(tip, text=self._text, background=INK, foreground="#ffffff", font=FONT_SMALL, padx=10, pady=6,
                 justify="left", wraplength=320).pack()

    def _hide(self, _event=None) -> None:
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        if self._tip:
            self._tip.destroy()
            self._tip = None


def tip(widget: tk.Widget, text: str) -> tk.Widget:
    Tooltip(widget, text)
    return widget


class Collapsible(ttk.Frame):
    """Sección que se abre y cierra con un clic («Opciones avanzadas ▸»)."""

    def __init__(self, parent: tk.Widget, title: str, style: str = "Card", opened: bool = False) -> None:
        super().__init__(parent, style="Inner.TFrame" if style == "Card" else "TFrame")
        self._title = title
        self._open = opened
        self._toggle = ttk.Button(self, style="Link.TButton" if style == "Card" else "LinkBg.TButton",
                                  command=self.toggle)
        self._toggle.pack(anchor="w")
        self.body = ttk.Frame(self, style="Inner.TFrame" if style == "Card" else "TFrame")
        self._render()

    def toggle(self) -> None:
        self._open = not self._open
        self._render()

    def _render(self) -> None:
        self._toggle.configure(text=("▾  " if self._open else "▸  ") + self._title)
        if self._open:
            self.body.pack(fill="x", pady=(6, 0))
        else:
            self.body.pack_forget()


# --- Componentes de app ----------------------------------------------------------------------------------

def page_header(parent: tk.Widget, title: str, subtitle: str) -> ttk.Frame:
    """Encabezado grande de cada pantalla."""
    box = ttk.Frame(parent)
    ttk.Label(box, text=title, font=("Segoe UI Semibold", 20), foreground=INK).pack(anchor="w")
    autowrap(ttk.Label(box, text=subtitle, foreground=MUTED, font=("Segoe UI", 10), justify="left")).pack(
        fill="x", pady=(2, 0))
    return box


def score_color(value: int) -> str:
    return OK if value >= 70 else ("#d97706" if value >= 40 else DANGER)


class ScoreRing(tk.Canvas):
    """Anillo con el porcentaje de coincidencia, como el de una app de fitness."""

    def __init__(self, parent: tk.Widget, size: int = 120, background: str = SURFACE) -> None:
        scale = max(1.0, parent.winfo_fpixels("1i") / 96)
        self._size = int(size * scale)
        self._ring = max(8, int(11 * scale))
        super().__init__(parent, width=self._size, height=self._size, background=background, highlightthickness=0)
        self.set(None)

    def set(self, value: int | None) -> None:
        self.delete("all")
        pad = self._ring / 2 + 2
        box = (pad, pad, self._size - pad, self._size - pad)
        self.create_oval(*box, outline="#e8ecf3", width=self._ring)
        if value is None:
            self.create_text(self._size / 2, self._size / 2, text="—", fill=MUTED, font=("Segoe UI Semibold", 20))
            return
        color = score_color(value)
        if value > 0:
            self.create_arc(*box, start=90, extent=-min(359.9, 3.6 * value), style="arc", outline=color, width=self._ring)
        self.create_text(self._size / 2, self._size / 2 - 6, text=f"{value}%", fill=INK, font=("Segoe UI Semibold", 20))
        self.create_text(self._size / 2, self._size / 2 + 18, text="de match", fill=MUTED, font=("Segoe UI", 8))


class StatCard(ttk.Frame):
    """Tarjeta con un número grande y una etiqueta («12 · listas para tu CV»)."""

    def __init__(self, parent: tk.Widget, label: str, color: str = INK) -> None:
        super().__init__(parent, style="Card.TFrame", padding=(18, 12))
        self._value = tk.Label(self, text="—", background=SURFACE, foreground=color, font=("Segoe UI Semibold", 22))
        self._value.pack(anchor="w")
        tk.Label(self, text=label, background=SURFACE, foreground=MUTED, font=("Segoe UI", 9)).pack(anchor="w")

    def set(self, value: int | str) -> None:
        self._value.configure(text=str(value))


class ProgressToast(tk.Frame):
    """Tarjeta flotante que dice qué se está haciendo, sin mostrar el registro técnico."""

    _SPIN = "◐◓◑◒"

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent, background=SURFACE, highlightthickness=1, highlightbackground=BORDER, padx=18, pady=14)
        top = tk.Frame(self, background=SURFACE)
        top.pack(fill="x")
        self._icon = tk.Label(top, text="◐", background=SURFACE, foreground=ACCENT, font=("Segoe UI Semibold", 14))
        self._icon.pack(side="left")
        self._title = tk.Label(top, text="", background=SURFACE, foreground=INK, font=("Segoe UI Semibold", 10),
                               anchor="w", justify="left", wraplength=340)
        self._title.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self._detail = tk.Label(self, text="", background=SURFACE, foreground=MUTED, font=("Segoe UI", 9),
                                anchor="w", justify="left", wraplength=380)
        self._detail.pack(fill="x", pady=(4, 6))
        self._bar = ttk.Progressbar(self, length=380, mode="indeterminate")
        self._bar.pack(fill="x")
        self._frame = 0
        self._job: str | None = None
        self._hide_job: str | None = None

    def show(self, title: str) -> None:
        if self._hide_job:
            self.after_cancel(self._hide_job)
            self._hide_job = None
        self._title.configure(text=title)
        self._detail.configure(text="")
        self._icon.configure(text=self._SPIN[0], foreground=ACCENT)
        self._bar.configure(mode="indeterminate", value=0)
        self._bar.start(14)
        self._bar.pack(fill="x")
        self.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        self.lift()
        if not self._job:
            self._spin()

    def _spin(self) -> None:
        self._frame = (self._frame + 1) % len(self._SPIN)
        self._icon.configure(text=self._SPIN[self._frame])
        self._job = self.after(180, self._spin)

    def step(self, title: str | None = None, detail: str | None = None) -> None:
        if title is not None:
            self._title.configure(text=title)
        if detail is not None:
            self._detail.configure(text=detail)

    def progress(self, done: int, total: int) -> None:
        self._bar.stop()
        self._bar.configure(mode="determinate", maximum=max(1, total), value=done)

    def finish(self, ok: bool, title: str) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self._bar.stop()
        self._bar.pack_forget()
        self._icon.configure(text="✔" if ok else "✖", foreground=OK if ok else DANGER)
        self._title.configure(text=title)
        self._detail.configure(text="")
        self._hide_job = self.after(3500 if ok else 6000, self.place_forget)
