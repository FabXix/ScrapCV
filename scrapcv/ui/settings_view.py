"""Pestaña de configuración: fuente de datos, token, carpeta y modelo local."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import replace
from tkinter import filedialog, ttk
from typing import Callable

from scrapcv.infrastructure.config import TOKEN_ENV_VAR, Settings
from scrapcv.ui.controller import AppController
from scrapcv.ui.widgets import TaskStarter


class SettingsView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter, on_applied: Callable[[], None]) -> None:
        super().__init__(parent, padding=16)
        self._controller = controller
        self._start = start
        self._on_applied = on_applied
        s = controller.settings
        self.demo = tk.BooleanVar(value=s.use_demo)
        self.canvas_url = tk.StringVar(value=s.canvas_url)
        self.token = tk.StringVar()
        self.remember = tk.BooleanVar(value=False)
        self.data_dir = tk.StringVar(value=s.data_dir)
        self.use_llm = tk.BooleanVar(value=s.use_llm)
        self.ollama_url = tk.StringVar(value=s.ollama_url)
        self.model = tk.StringVar(value=s.ollama_model)
        self.phone = tk.StringVar(value=s.phone)
        self.location = tk.StringVar(value=s.location)
        self.linkedin = tk.StringVar(value=s.linkedin)
        self.github = tk.StringVar(value=s.github)
        self.portfolio = tk.StringVar(value=s.portfolio)
        self.status = tk.StringVar(value="Configura la fuente de datos y presiona «Aplicar».")
        self._models_found: "queue.Queue[list[str]]" = queue.Queue()
        self._build()
        self._toggle_source()
        self.after(200, self._refresh_models)

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)

        source = ttk.LabelFrame(self, text="Fuente de las entregas", style="Section.TLabelframe", padding=12)
        source.grid(row=0, column=0, sticky="ew")
        source.columnconfigure(1, weight=1)
        ttk.Radiobutton(source, text="Datos de demostración (no necesita token)", variable=self.demo, value=True,
                        command=self._toggle_source).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(source, text="Mi Canvas (API oficial con token personal)", variable=self.demo, value=False,
                        command=self._toggle_source).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
        ttk.Label(source, text="URL de Canvas").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self._url_entry = ttk.Entry(source, textvariable=self.canvas_url)
        self._url_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(source, text="Token de acceso").grid(row=3, column=0, sticky="w", padx=(0, 8))
        self._token_entry = ttk.Entry(source, textvariable=self.token, show="•")
        self._token_entry.grid(row=3, column=1, sticky="ew", pady=2)
        self._remember = ttk.Checkbutton(source, text="Recordar en ~/.scrapcv", variable=self.remember)
        self._remember.grid(row=3, column=2, sticky="w", padx=(8, 0))
        hint = (f"Genera el token en Canvas › Cuenta › Configuración › «Nuevo token de acceso». "
                f"También puedes definir la variable de entorno {TOKEN_ENV_VAR}. El token nunca se escribe en registros.")
        if self._controller.has_saved_token():
            hint = "Ya hay un token guardado o en la variable de entorno; deja el campo vacío para usarlo. " + hint
        ttk.Label(source, text=hint, style="Muted.TLabel", wraplength=760, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

        storage = ttk.LabelFrame(self, text="Carpeta de datos (todo queda en tu computadora)", style="Section.TLabelframe", padding=12)
        storage.grid(row=1, column=0, sticky="ew", pady=12)
        storage.columnconfigure(0, weight=1)
        ttk.Entry(storage, textvariable=self.data_dir).grid(row=0, column=0, sticky="ew")
        ttk.Button(storage, text="Elegir…", command=self._choose_dir).grid(row=0, column=1, padx=(8, 0))

        llm = ttk.LabelFrame(self, text="Modelo de lenguaje local (Ollama)", style="Section.TLabelframe", padding=12)
        llm.grid(row=2, column=0, sticky="ew")
        llm.columnconfigure(1, weight=1)
        ttk.Checkbutton(llm, text="Usar Ollama para resumir proyectos (si no, se usa un perfil estático)",
                        variable=self.use_llm).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Label(llm, text="URL").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(llm, textvariable=self.ollama_url).grid(row=1, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Label(llm, text="Modelo").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self._models = ttk.Combobox(llm, textvariable=self.model)
        self._models.grid(row=2, column=1, sticky="ew", pady=2)
        ttk.Button(llm, text="Actualizar lista", command=self._refresh_models).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(llm, text="Solo se acepta un servidor en esta computadora; ningún trabajo se envía a la nube.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        contact = ttk.LabelFrame(self, text="Datos del currículum (encabezado)", style="Section.TLabelframe", padding=12)
        contact.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        contact.columnconfigure(1, weight=1)
        contact.columnconfigure(3, weight=1)
        for i, (label, var) in enumerate((
            ("Teléfono", self.phone), ("Ciudad", self.location),
            ("LinkedIn", self.linkedin), ("GitHub", self.github), ("Portafolio", self.portfolio),
        )):
            row, col = divmod(i, 2)
            ttk.Label(contact, text=label).grid(row=row, column=col * 2, sticky="w", padx=(0 if col == 0 else 16, 8))
            ttk.Entry(contact, textvariable=var).grid(row=row, column=col * 2 + 1, sticky="ew", pady=2)
        ttk.Label(contact, text="Se guardan solo en tu computadora y se usan en el encabezado del currículum.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        actions = ttk.Frame(self)
        actions.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        ttk.Button(actions, text="Aplicar y probar conexión", style="Accent.TButton", command=self._apply).pack(side="left")
        ttk.Label(actions, textvariable=self.status, style="Muted.TLabel").pack(side="left", padx=12)

    def _toggle_source(self) -> None:
        state = "disabled" if self.demo.get() else "normal"
        for widget in (self._url_entry, self._token_entry, self._remember):
            widget.configure(state=state)

    def _choose_dir(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.data_dir.get() or ".")
        if folder:
            self.data_dir.set(folder)

    def _current(self) -> Settings:
        return replace(
            self._controller.settings,
            canvas_url=self.canvas_url.get().strip(),
            data_dir=self.data_dir.get().strip(),
            use_demo=self.demo.get(),
            ollama_url=self.ollama_url.get().strip(),
            ollama_model=self.model.get().strip(),
            use_llm=self.use_llm.get(),
            phone=self.phone.get().strip(),
            location=self.location.get().strip(),
            linkedin=self.linkedin.get().strip(),
            github=self.github.get().strip(),
            portfolio=self.portfolio.get().strip(),
        )

    def _refresh_models(self) -> None:
        """Consulta ligera en su propio hilo: no ocupa el ejecutor de las etapas."""
        settings = self._current()
        threading.Thread(
            target=lambda: self._models_found.put(self._controller.available_models(settings)), daemon=True
        ).start()
        self.after(200, self._await_models)

    def _await_models(self) -> None:
        try:
            self._show_models(self._models_found.get_nowait())
        except queue.Empty:
            self.after(200, self._await_models)

    def _show_models(self, models: list[str]) -> None:
        self._models.configure(values=models)
        if models and not self.model.get():
            self.model.set(models[0])
        if not models:
            self.status.set("Ollama no respondió: se usará el perfil estático hasta que esté disponible.")

    def _apply(self) -> None:
        settings, token, remember = self._current(), self.token.get(), self.remember.get()
        self.token.set("")  # no se deja el token visible en memoria de la ventana

        def work(_progress):
            app = self._controller.apply(settings, token, remember)
            return app.check_connection(), app.profiler_name

        def done(result):
            user, profiler = result
            self.status.set(f"✔ Conectado como {user}. Perfiles: {profiler}.")
            self._on_applied()

        self.status.set("Probando conexión…")
        self._start("conexión", work, done)
