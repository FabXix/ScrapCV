"""Paso 1 · Conectar: de dónde salen las entregas, los datos del CV y la IA opcional."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from dataclasses import replace
from tkinter import filedialog, ttk
from typing import Callable

from scrapcv.infrastructure.config import TOKEN_ENV_VAR, Settings
from scrapcv.ui.controller import AppController
from scrapcv.ui.widgets import Collapsible, TaskStarter, autowrap, card, page_header, tip


class SettingsView(ttk.Frame):
    def __init__(self, parent: tk.Widget, controller: AppController, start: TaskStarter, on_applied: Callable[[], None]) -> None:
        super().__init__(parent, padding=(32, 26))
        self._controller = controller
        self._start = start
        self._on_applied = on_applied
        s = controller.settings
        self.demo = tk.BooleanVar(value=s.use_demo)
        self.canvas_url = tk.StringVar(value=s.canvas_url)
        self.token = tk.StringVar()
        self.remember = tk.BooleanVar(value=controller.can_remember_token)
        self.data_dir = tk.StringVar(value=s.data_dir)
        self.use_llm = tk.BooleanVar(value=s.use_llm)
        self.ollama_url = tk.StringVar(value=s.ollama_url)
        self.model = tk.StringVar(value=s.ollama_model)
        self.phone = tk.StringVar(value=s.phone)
        self.location = tk.StringVar(value=s.location)
        self.linkedin = tk.StringVar(value=s.linkedin)
        self.github = tk.StringVar(value=s.github)
        self.portfolio = tk.StringVar(value=s.portfolio)
        self.degree = tk.StringVar(value=s.degree)
        self.institution = tk.StringVar(value=s.institution)
        self.period = tk.StringVar(value=s.period)
        self.status = tk.StringVar(value="")
        self.ollama_status = tk.StringVar(value="Buscando Ollama…")
        self._models_found: "queue.Queue[list[str]]" = queue.Queue()
        self._build()
        self._toggle_source()
        self.after(200, self._refresh_models)

    # --- Construcción -------------------------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(0, weight=1, uniform="col")
        self.columnconfigure(1, weight=1, uniform="col")

        page_header(self, "Conecta tu Canvas",
                    "ScrapCV solo lee lo que tú entregaste. ¿Quieres ver cómo funciona antes? "
                    "Elige «Probar con datos de ejemplo» y presiona Continuar.").grid(
            row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))

        self._build_source().grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self._build_contact().grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self._build_ai().grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self._apply_btn = ttk.Button(actions, text="Guardar y continuar  →", style="Accent.TButton", command=self._apply)
        self._apply_btn.pack(side="left")
        ttk.Label(actions, textvariable=self.status, style="Muted.TLabel").pack(side="left", padx=12)

    def _build_source(self) -> ttk.Frame:
        box = card(self)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="¿De dónde saco tus entregas?", style="CardHeading.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        ttk.Radiobutton(box, text="Probar con datos de ejemplo (no necesitas nada)", variable=self.demo, value=True,
                        style="Card.TRadiobutton", command=self._toggle_source).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(box, text="Usar mi Canvas", variable=self.demo, value=False,
                        style="Card.TRadiobutton", command=self._toggle_source).grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 10))

        ttk.Label(box, text="Tu token de Canvas", style="Card.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10))
        self._token_entry = ttk.Entry(box, textvariable=self.token, show="•")
        self._token_entry.grid(row=3, column=1, sticky="ew", pady=3)
        self._token_help = tip(ttk.Button(box, text="¿Cómo lo consigo?", style="Link.TButton", command=self._open_token_page),
                               "Abre tu Canvas › Cuenta › Configuración. Baja a «Integraciones aprobadas» y presiona "
                               "«+ Nuevo token de acceso». Copia el token y pégalo aquí.")
        self._token_help.grid(row=3, column=2, sticky="w", padx=(10, 0))
        self._remember = ttk.Checkbutton(box, text="Recordarlo en esta computadora (llavero de Windows)",
                                         variable=self.remember, style="Card.TCheckbutton")
        self._remember.grid(row=4, column=1, columnspan=2, sticky="w", pady=(4, 0))
        hint = "El token solo se envía a tu Canvas por https y nunca se guarda en archivos."
        if self._controller.has_saved_token():
            hint = "✔ Ya tienes un token guardado: puedes dejar el campo vacío. " + hint
        elif not self._controller.can_remember_token:
            hint += " Para recordarlo instala «keyring»."
        autowrap(ttk.Label(box, text=hint, style="CardMuted.TLabel", justify="left")).grid(
            row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        advanced = Collapsible(box, "Opciones avanzadas")
        advanced.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        advanced.body.columnconfigure(1, weight=1)
        ttk.Label(advanced.body, text="Dirección de Canvas", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self._url_entry = ttk.Entry(advanced.body, textvariable=self.canvas_url)
        self._url_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(advanced.body, text="Carpeta de datos", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(advanced.body, textvariable=self.data_dir).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(advanced.body, text="Elegir…", command=self._choose_dir).grid(row=1, column=2, padx=(8, 0))
        autowrap(ttk.Label(advanced.body, style="CardMuted.TLabel", justify="left",
                           text=f"También puedes definir el token en la variable de entorno {TOKEN_ENV_VAR}. "
                                "Todo (entregas, análisis y CVs) se queda en esa carpeta, en tu computadora.")).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        return box

    def _build_contact(self) -> ttk.Frame:
        box = card(self)
        box.columnconfigure(1, weight=1)
        box.columnconfigure(3, weight=1)
        ttk.Label(box, text="Tus datos para el CV", style="CardHeading.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        autowrap(ttk.Label(box, text="Canvas no tiene estos datos. Todo es opcional, pero un CV sin contacto ni "
                                     "carrera pierde puntos.", style="CardMuted.TLabel", justify="left")).grid(
            row=1, column=0, columnspan=4, sticky="ew", pady=(2, 10))
        fields = (
            ("Carrera", self.degree, "Ingeniería en Sistemas Computacionales"),
            ("Universidad", self.institution, "ITESO"),
            ("Periodo", self.period, "2022 – 2026 (esperado)"),
            ("Ciudad", self.location, "Guadalajara, Jal."),
            ("Teléfono", self.phone, "33 1234 5678"),
            ("LinkedIn", self.linkedin, "linkedin.com/in/tu-nombre"),
            ("GitHub", self.github, "github.com/tu-usuario"),
            ("Portafolio", self.portfolio, "tu-sitio.dev"),
        )
        for i, (label, var, example) in enumerate(fields):
            row, col = divmod(i, 2)
            ttk.Label(box, text=label, style="Card.TLabel").grid(row=row + 2, column=col * 2, sticky="w",
                                                                padx=(0 if col == 0 else 14, 8))
            tip(ttk.Entry(box, textvariable=var), f"Ejemplo: {example}").grid(
                row=row + 2, column=col * 2 + 1, sticky="ew", pady=3)
        return box

    def _build_ai(self) -> ttk.Frame:
        box = card(self)
        box.columnconfigure(2, weight=1)
        ttk.Label(box, text="Redacción con IA (opcional)", style="CardHeading.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(box, text="Redactar con IA local (Ollama)", variable=self.use_llm,
                        style="Card.TCheckbutton").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(box, text="Modelo", style="Card.TLabel").grid(row=1, column=1, sticky="e", padx=(24, 8), pady=(8, 0))
        self._models = ttk.Combobox(box, textvariable=self.model, width=28)
        self._models.grid(row=1, column=2, sticky="w", pady=(8, 0))
        tip(ttk.Button(box, text="Buscar de nuevo", command=self._refresh_models),
            "Vuelve a preguntar a Ollama qué modelos tienes instalados.").grid(row=1, column=3, sticky="e", pady=(8, 0))
        ttk.Label(box, textvariable=self.ollama_status, style="CardMuted.TLabel").grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        autowrap(ttk.Label(box, style="CardMuted.TLabel", justify="left",
                           text="Sin IA el CV se arma con reglas a partir de tu evidencia y te marca qué personalizar. "
                                "Con IA las viñetas suenan más naturales. Nada sale de tu computadora. Si tu equipo "
                                "tiene poca memoria, un modelo pequeño (llama3.2, qwen2.5) es suficiente.")).grid(
            row=3, column=0, columnspan=4, sticky="ew", pady=(4, 0))
        advanced = Collapsible(box, "Opciones avanzadas")
        advanced.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        advanced.body.columnconfigure(1, weight=1)
        ttk.Label(advanced.body, text="Dirección de Ollama", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))
        ttk.Entry(advanced.body, textvariable=self.ollama_url, width=40).grid(row=0, column=1, sticky="w", pady=3)
        return box

    # --- Comportamiento --------------------------------------------------------------------------
    def _toggle_source(self) -> None:
        state = "disabled" if self.demo.get() else "normal"
        for widget in (self._url_entry, self._token_entry):
            widget.configure(state=state)
        can_remember = self._controller.can_remember_token and not self.demo.get()
        self._remember.configure(state="normal" if can_remember else "disabled")

    def _open_token_page(self) -> None:
        base = self.canvas_url.get().strip().rstrip("/")
        if base.startswith("https://"):
            webbrowser.open(f"{base}/profile/settings")

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
            degree=self.degree.get().strip(),
            institution=self.institution.get().strip(),
            period=self.period.get().strip(),
        )

    def _refresh_models(self) -> None:
        """Consulta ligera en su propio hilo: no ocupa el ejecutor de las etapas."""
        settings = self._current()
        self.ollama_status.set("Buscando Ollama…")
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
        if models:
            self.ollama_status.set(f"✔ Ollama está abierto · {len(models)} modelo(s) instalado(s).")
        else:
            self.ollama_status.set("✖ Ollama no está abierto. Ábrelo y presiona «Buscar de nuevo», o continúa sin IA.")

    def _apply(self) -> None:
        settings, token, remember = self._current(), self.token.get(), self.remember.get()
        if not settings.use_demo and not token.strip() and not self._controller.has_saved_token():
            self.status.set("Pega tu token de Canvas o elige «Probar con datos de ejemplo».")
            self._token_entry.focus_set()
            return
        self.token.set("")  # no se deja el token visible en memoria de la ventana

        def work(_progress):
            app = self._controller.apply(settings, token, remember)
            return app.check_connection(), app.profiler_name

        def done(result):
            user, _profiler = result
            self.status.set(f"✔ Conectado como {user}.")
            self._apply_btn.state(["!disabled"])
            self._on_applied()

        self.status.set("Conectando con Canvas…")
        self._apply_btn.state(["disabled"])
        self._start("Conectar", work, done)

    def task_failed(self) -> None:
        self._apply_btn.state(["!disabled"])
        self.status.set("")
