"""Punto de entrada de ScrapCV con interfaz gráfica."""
from __future__ import annotations

import sys
import tkinter as tk

from scrapcv.bootstrap import build_app, list_ollama_models
from scrapcv.infrastructure.config import SettingsStore
from scrapcv.ui.controller import AppController
from scrapcv.ui.main_window import MainWindow


def main() -> int:
    if sys.version_info < (3, 11):
        print("ScrapCV necesita Python 3.11 o superior.", file=sys.stderr)
        return 1
    if sys.platform == "win32":  # texto nítido en pantallas con escalado
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    controller = AppController(SettingsStore(), build_app, list_ollama_models)
    MainWindow(root, controller)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
