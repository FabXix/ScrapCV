"""Canvas simulado para probar y demostrar ScrapCV sin token.

Implementa los mismos puertos que el adaptador real (LSP): el resto del
sistema no distingue entre uno y otro. Genera en memoria entregas con los
formatos que soporta el MVP, incluidas algunas problemáticas a propósito
(credenciales, PDF escaneado, .rar sin 7z) para mostrar cómo se marcan.
"""
from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from scrapcv.domain.models import Attachment, Comment, Course, Submission, UserInfo
from scrapcv.ports import AttachmentDownloader, CanvasReader

DEMO_HOST = "https://demo.canvas.local/files"


def _zip(files: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _targz(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _pdf(lines: list[str]) -> bytes:
    """PDF mínimo válido. Sin líneas simula un escaneo (no hay texto extraíble)."""

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    ops = ["BT /F1 12 Tf 72 720 Td 16 TL"] + [f"({esc(line)}) Tj T*" for line in lines] + ["ET"]
    stream = "\n".join(ops) if lines else "0 0 1 rg 72 72 400 600 re f"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
        "/Resources << /Font << /F1 4 0 R >> >> >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1"))
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def _docx(title: str, paragraphs: list[str], table: list[list[str]]) -> bytes:
    from docx import Document

    document = Document()
    document.add_heading(title, 1)
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    grid = document.add_table(rows=len(table), cols=len(table[0]))
    for r, row in enumerate(table):
        for c, value in enumerate(row):
            grid.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pptx(slides: list[tuple[str, str]]) -> bytes:
    from pptx import Presentation

    deck = Presentation()
    for title, body in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


def _notebook() -> str:
    cells = [
        {"cell_type": "markdown", "source": ["# Análisis de deserción estudiantil\n", "Exploración y modelo de clasificación."]},
        {"cell_type": "code", "source": ["import pandas as pd\n", "import seaborn as sns\n", "from sklearn.ensemble import RandomForestClassifier\n"]},
        {"cell_type": "code", "source": ["df = pd.read_csv('alumnos.csv')\n", "df.describe()\n"]},
        {"cell_type": "markdown", "source": ["## Modelo\n", "Se entrena un bosque aleatorio y se evalúa con validación cruzada."]},
        {"cell_type": "code", "source": ["model = RandomForestClassifier(n_estimators=200)\n", "model.fit(X_train, y_train)\n", "print(model.score(X_test, y_test))\n"]},
    ]
    return json.dumps({"cells": cells, "metadata": {"kernelspec": {"language": "python"}}, "nbformat": 4, "nbformat_minor": 5})


_PY_PROJECT = {
    "inventario/README.md": "# Inventario POO\n\nSistema de inventario para una tienda con clases Producto, Almacen y "
    "Reporte. Aplica patrón Strategy para calcular descuentos y Repository para persistir en SQLite.\n",
    "inventario/requirements.txt": "sqlalchemy==2.0.30\npytest==8.2.0\nrich==13.7.1\n",
    "inventario/.env": "DB_PASSWORD=super-secreto-no-leer\n",
    "inventario/src/main.py": "from almacen import Almacen\n\n\ndef main():\n    almacen = Almacen()\n    almacen.cargar()\n    almacen.reporte()\n\n\nif __name__ == '__main__':\n    main()\n",
    "inventario/src/almacen.py": "class Almacen:\n    def __init__(self):\n        self.productos = []\n\n    def agregar(self, producto):\n        self.productos.append(producto)\n\n    def cargar(self):\n        pass\n\n    def reporte(self):\n        for p in self.productos:\n            print(p)\n",
    "inventario/src/descuentos.py": "from abc import ABC, abstractmethod\n\n\nclass Descuento(ABC):\n    @abstractmethod\n    def aplicar(self, precio):\n        ...\n\n\nclass SinDescuento(Descuento):\n    def aplicar(self, precio):\n        return precio\n\n\nclass Porcentaje(Descuento):\n    def __init__(self, pct):\n        self.pct = pct\n\n    def aplicar(self, precio):\n        return precio * (1 - self.pct)\n",
    "inventario/tests/test_descuentos.py": "from descuentos import Porcentaje\n\n\ndef test_porcentaje():\n    assert Porcentaje(0.5).aplicar(10) == 5\n",
}

_WEB_INNER = {
    "tienda-web/package.json": json.dumps(
        {"name": "tienda-web", "dependencies": {"react": "^18.3.1", "react-router-dom": "^6.22.0", "axios": "^1.6.0"},
         "devDependencies": {"vite": "^5.2.0"}}, indent=2),
    "tienda-web/README.md": "# Tienda Web\n\nSPA en React con carrito de compras, rutas y consumo de una API REST de productos.\n",
    "tienda-web/src/App.jsx": "import { BrowserRouter, Routes, Route } from 'react-router-dom';\nimport Catalogo from './Catalogo';\n\nexport default function App() {\n  return (\n    <BrowserRouter>\n      <Routes>\n        <Route path='/' element={<Catalogo />} />\n      </Routes>\n    </BrowserRouter>\n  );\n}\n",
    "tienda-web/src/Catalogo.jsx": "import { useEffect, useState } from 'react';\nimport axios from 'axios';\n\nexport default function Catalogo() {\n  const [items, setItems] = useState([]);\n  useEffect(() => { axios.get('/api/productos').then(r => setItems(r.data)); }, []);\n  return <ul>{items.map(i => <li key={i.id}>{i.nombre}</li>)}</ul>;\n}\n",
    "tienda-web/src/styles.css": "body { font-family: sans-serif; }\nul { list-style: none; }\n",
    "tienda-web/node_modules/react/index.js": "// dependencia de terceros: se ignora\n",
}

_JAVA_PROJECT = {
    "banco/README.md": "# Banco\n\nSimulación de cuentas bancarias con hilos concurrentes y sincronización.\n",
    "banco/pom.xml": "<project><dependencies><dependency><artifactId>junit-jupiter</artifactId></dependency></dependencies></project>\n",
    "banco/src/main/java/Main.java": "public class Main {\n    public static void main(String[] args) {\n        Banco banco = new Banco();\n        banco.simular();\n    }\n}\n",
    "banco/src/main/java/Banco.java": "import java.util.concurrent.*;\n\npublic class Banco {\n    private final ExecutorService pool = Executors.newFixedThreadPool(4);\n\n    public synchronized void transferir(Cuenta a, Cuenta b, double monto) {\n        a.retirar(monto);\n        b.depositar(monto);\n    }\n\n    public void simular() {\n        pool.shutdown();\n    }\n}\n",
    "banco/src/main/java/Cuenta.java": "public class Cuenta {\n    private double saldo;\n    public void retirar(double m) { saldo -= m; }\n    public void depositar(double m) { saldo += m; }\n}\n",
}


class DemoCanvasGateway(CanvasReader, AttachmentDownloader):
    def __init__(self) -> None:
        self._files: dict[str, Callable[[], bytes]] = {}
        self._courses = [
            Course(101, "Programación Orientada a Objetos", "POO-2025O", "Otoño 2025", "completed"),
            Course(102, "Desarrollo de Aplicaciones Web", "WEB-2026P", "Primavera 2026", "completed"),
            Course(103, "Ciencia de Datos", "CDD-2026P", "Primavera 2026", "completed"),
            Course(104, "Sistemas Concurrentes", "SC-2026O", "Otoño 2026", "active"),
            Course(105, "Ingeniería de Requisitos", "IR-2026O", "Otoño 2026", "active"),
        ]
        self._submissions = self._build()

    # --- Puertos ---------------------------------------------------------------
    def current_user(self) -> UserInfo:
        return UserInfo(id=1, name="Estudiante Demo", email="estudiante.demo@iteso.mx")

    def list_courses(self) -> list[Course]:
        return list(self._courses)

    def list_submissions(self, course: Course) -> list[Submission]:
        return [s for s in self._submissions if s.course.id == course.id]

    def download(self, url: str, destination: Path) -> None:
        factory = self._files.get(url)
        if factory is None:
            raise FileNotFoundError(f"Enlace caído: {url}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(factory())

    # --- Datos simulados -----------------------------------------------------------
    def _file(self, file_id: int, name: str, factory: Callable[[], bytes]) -> Attachment:
        url = f"{DEMO_HOST}/{file_id}/{name}"
        self._files[url] = factory
        return Attachment(file_id, name, url, 0)

    def _build(self) -> list[Submission]:
        poo, web, cdd, sc, ir = self._courses
        return [
            Submission(
                1, poo, 1001, "Proyecto final: Sistema de inventario", "2025-11-28T23:00:00Z", 95, "95", 100,
                "online_upload",
                attachments=(self._file(1, "inventario.zip", lambda: _zip(_PY_PROJECT)),),
                comments=(Comment("Prof. Martínez", "Muy buena aplicación del patrón Strategy."),),
            ),
            Submission(
                2, poo, 1002, "Tarea 3: Herencia y polimorfismo", "2025-09-15T23:00:00Z", 80, "80", 100,
                "online_text_entry",
                body="<p>Implementé una jerarquía Figura → Círculo, Rectángulo con método area() polimórfico.</p>",
            ),
            Submission(
                3, web, 2001, "Proyecto en equipo: Tienda en línea", "2026-05-20T23:00:00Z", 92, "92", 100,
                "online_upload",
                body="<p>Repositorio: https://github.com/equipo-demo/tienda-web</p>",
                attachments=(
                    self._file(3, "entrega.zip", lambda: _zip({"tienda-web.zip": _zip(_WEB_INNER), "LEEME.txt": "Código anidado en tienda-web.zip"})),
                    self._file(4, "captura-carrito.png", lambda: b"\x89PNG\r\n\x1a\n" + b"0" * 64),
                ),
                is_group=True,
            ),
            Submission(
                4, web, 2002, "Prototipo de interfaz", "2026-02-10T23:00:00Z", 100, "100", 100, "online_url",
                url="https://www.figma.com/file/demo/prototipo-tienda",
            ),
            Submission(
                5, cdd, 3001, "Proyecto: Predicción de deserción", "2026-05-30T23:00:00Z", 88, "88", 100,
                "online_upload",
                attachments=(
                    self._file(5, "desercion.ipynb", lambda: _notebook().encode()),
                    self._file(6, "reporte.docx", lambda: _docx(
                        "Reporte de deserción",
                        ["Se analizaron registros académicos para predecir deserción.",
                         "Se usó limpieza de datos, ingeniería de variables y un modelo RandomForest."],
                        [["Métrica", "Valor"], ["Exactitud", "0.87"], ["F1", "0.81"]])),
                    self._file(7, "presentacion.pptx", lambda: _pptx([
                        ("Predicción de deserción", "Motivación y datos"),
                        ("Resultados", "Modelo de clasificación con validación cruzada")])),
                ),
            ),
            Submission(
                6, sc, 4001, "Práctica: Banco concurrente", "2026-09-30T23:00:00Z", 90, "90", 100,
                "online_upload",
                attachments=(self._file(8, "banco.tar.gz", lambda: _targz(_JAVA_PROJECT)),),
            ),
            Submission(
                7, sc, 4002, "Reporte de laboratorio escaneado", "2026-10-05T23:00:00Z", 70, "70", 100,
                "online_upload",
                attachments=(
                    self._file(9, "reporte-escaneado.pdf", lambda: _pdf([])),
                    self._file(10, "codigo-extra.rar", lambda: b"Rar!\x1a\x07\x00" + b"0" * 32),
                ),
            ),
            Submission(
                8, ir, 5001, "Documento de visión del producto", "2026-10-16T23:00:00Z", 97, "97", 100,
                "online_upload",
                attachments=(self._file(11, "vision.pdf", lambda: _pdf([
                    "Documento de vision: plataforma de reservas de laboratorios.",
                    "Incluye partes interesadas, casos de uso y criterios de aceptacion.",
                    "Se modelaron requisitos funcionales y no funcionales con historias de usuario."])),),
            ),
            Submission(
                9, ir, 5002, "Entrevistas a usuarios", "2026-10-20T23:00:00Z", None, None, 50, "online_upload",
                attachments=(Attachment(99, "entrevistas.docx", f"{DEMO_HOST}/99/enlace-caido", 0),),
            ),
        ]
