"""Pantalla de bienvenida: qué hace la app en tres pasos y un botón para empezar (o probar con un ejemplo)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from scrapcv.ui.widgets import ACCENT, ACCENT_SOFT, BG, INK, MUTED, SURFACE

_STEPS = (
    ("1", "Conecta tu Canvas", "Con un token que generas en tu cuenta. Todo se queda en tu computadora."),
    ("2", "Trae tus entregas", "ScrapCV lee tus proyectos, reportes y código, y entiende qué hiciste en cada uno."),
    ("3", "Pega una vacante", "Arma un CV a la medida con tus mejores proyectos y te dice qué tanto encajas."),
)


class WelcomeView(ttk.Frame):
    def __init__(self, parent: tk.Widget, on_start: Callable[[], None], on_demo: Callable[[], None]) -> None:
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=2)
        hero = tk.Frame(self, background=BG)
        hero.grid(row=1, column=0)

        tk.Label(hero, text="BIENVENIDO A SCRAPCV", background=BG, foreground=ACCENT,
                 font=("Segoe UI Semibold", 9)).pack()
        tk.Label(hero, text="Tu CV, armado con lo que ya hiciste en clase", background=BG, foreground=INK,
                 font=("Segoe UI Semibold", 26)).pack(pady=(6, 4))
        tk.Label(hero, text="Sin plantillas vacías ni frases inventadas: cada línea sale de tus entregas reales.",
                 background=BG, foreground=MUTED, font=("Segoe UI", 12)).pack()

        scale = max(1.0, self.winfo_fpixels("1i") / 96)
        cards = tk.Frame(hero, background=BG)
        cards.pack(pady=(32, 32))
        for number, title, text in _STEPS:
            card = tk.Frame(cards, background=SURFACE, highlightthickness=1, highlightbackground="#e3e8f0",
                            padx=22, pady=20, width=int(270 * scale), height=int(175 * scale))
            card.pack(side="left", padx=10)
            card.pack_propagate(False)
            tk.Label(card, text=number, background=ACCENT_SOFT, foreground=ACCENT, font=("Segoe UI Semibold", 13),
                     width=3).pack(anchor="w")
            tk.Label(card, text=title, background=SURFACE, foreground=INK,
                     font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(12, 4))
            tk.Label(card, text=text, background=SURFACE, foreground=MUTED, font=("Segoe UI", 9), justify="left",
                     wraplength=int(225 * scale)).pack(anchor="w")

        actions = tk.Frame(hero, background=BG)
        actions.pack()
        ttk.Button(actions, text="Comenzar  →", style="Accent.TButton", command=on_start).pack(side="left", padx=6)
        ttk.Button(actions, text="Probar con datos de ejemplo", command=on_demo).pack(side="left", padx=6)
        tk.Label(hero, text="El ejemplo no necesita token: verás un CV completo en menos de un minuto.",
                 background=BG, foreground=MUTED, font=("Segoe UI", 9)).pack(pady=(10, 0))
