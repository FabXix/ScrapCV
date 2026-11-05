# ScrapCV — MVP con interfaz gráfica

De Canvas a Currículum: un CV construido con la evidencia de tus entregas.
Implementa las fases 1 a 3 del Documento de Visión y Alcances (CAR-01 a CAR-27 y CAR-31).
El único cambio respecto al documento es que la línea de comandos se sustituyó por una interfaz de escritorio
simple (Tkinter, incluida en Python). Todo sigue corriendo en local.

## Instalación y uso

```bash
python -m venv .venv            # Python 3.11 o superior
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python main.py
```

1. **Configuración**: elige *Datos de demostración* (sin token) o *Mi Canvas* y pega tu token personal
   (o define `CANVAS_TOKEN`). Si tienes Ollama, elige el modelo; si no, se usa un perfil estático.
2. **Evidencia**: *Ejecutar todo* descarga, extrae hechos y genera perfiles. Cada etapa también tiene su propio botón.
   Selecciona una entrega para ver su `facts.json`, su `perfil.json` y los motivos de lo que quedó marcado.
3. **Currículum**: elige el puesto (o uno personalizado con palabras clave), las materias y el máximo de proyectos.
   Edita el borrador y apruébalo como final.

Pruebas: `pip install -r requirements-dev.txt` y luego `python -m pytest`.

## Qué queda en disco

```
data/raw/<materia>/<tarea>/       evidencia: adjuntos, submission.json, texto_en_linea.html, enlaces.json
data/analysis/<materia>/<tarea>/  facts.json, contexto.json, perfil.json, unpacked/
data/index.json                   estado de cada entrega por etapa, con motivos
data/cv/cv_<puesto>.md            borrador;  cv_<puesto>_final.md  aprobado
data/logs/scrapcv.log             registros (el token se censura)
```

## Arquitectura

```
ui/  (Tkinter)  ──►  application/facade.py  ──►  servicios por etapa  ──►  ports.py (interfaces)
                                                                             ▲
bootstrap.py (raíz de composición) ── conecta ──► infrastructure/ · extraction/ · analysis/ · ranking/ · writing/
```

| Capa | Contenido |
|---|---|
| `domain/` | Entidades puras: `Submission`, `IndexEntry`, `Facts`, `ProjectProfile`. |
| `ports.py` | Interfaces pequeñas: `CanvasReader`, `AttachmentDownloader`, `IndexRepository`, `AnalysisStore`, `LanguageModel`, `ProjectProfiler`, `ProgressListener`… |
| `infrastructure/` | Adaptadores: API de Canvas, Canvas simulado, disco (JSON), Ollama, configuración y registros. |
| `extraction/` | Analizador estático y un extractor por formato. |
| `analysis/` | Contexto acotado, perfiles (LLM / estático / con respaldo) y guardas de veracidad. |
| `ranking/` | Puestos, criterios de puntuación y filtros. |
| `writing/` | Composición del CV y renderizado a Markdown. |
| `application/` | Casos de uso: ingesta, extracción, perfiles, CV y la fachada. |
| `ui/` | Ventana, pestañas, controlador y ejecución en segundo plano. |

### Principios SOLID en el código

- **S (responsabilidad única)**: `CanvasHttpClient` solo habla HTTP (paginación, reintentos); `CanvasApiGateway`
  solo traduce JSON a entidades; `StaticAnalyzer` recorre y delega; `FactsPhraser` es la única fuente de cifras
  del CV; `CvComposer` decide qué dice el CV y `MarkdownCvRenderer` cómo se ve.
- **O (abierto/cerrado)**: un formato nuevo es una clase `FormatExtractor` registrada en `extraction/factory.py`
  (ver `test_new_format_only_needs_a_new_class`). Un criterio de ranking nuevo es un `ProjectScorer`; un puesto
  nuevo es un `JobRole`; un formato de salida nuevo (DOCX/PDF, fase 4) es otro `CvRenderer`.
- **L (sustitución de Liskov)**: `DemoCanvasGateway` y `CanvasApiGateway` son intercambiables;
  `LlmProjectProfiler`, `StaticProjectProfiler` y `FallbackProjectProfiler` cumplen el mismo contrato.
- **I (segregación de interfaces)**: leer de Canvas (`CanvasReader`) está separado de descargar
  (`AttachmentDownloader`); la evidencia cruda (`RawEvidenceStore`) está separada del análisis (`AnalysisStore`),
  del índice y del CV.
- **D (inversión de dependencias)**: los servicios reciben interfaces por constructor. Solo `bootstrap.py`
  conoce las clases concretas. La interfaz gráfica recibe la fábrica de la aplicación por inyección.

### Patrones de diseño

Adapter (Canvas, Ollama) · Strategy (perfiles, criterios de ranking, renderers) · Registry (extractores) ·
Template Method (`_ArchiveExtractor`: reglas de seguridad comunes y `_unpack` por formato) · Chain de guardas
(`ProfileValidator`) · Observer (`ProgressListener` → `QueueProgress` → ventana) · Facade (`ScrapCvFacade`) ·
Composition Root (`bootstrap.py`). En todo el diseño se prefiere composición sobre herencia.

## Cómo se cumplen las restricciones del documento

| Requisito | Implementación |
|---|---|
| Solo la API oficial (6.1) | `CanvasApiGateway`: `users/self`, `courses`, `courses/:id/students/submissions`. Sin scraping. |
| Token seguro (CAR-01) | Variable `CANVAS_TOKEN`, `~/.scrapcv/config.json` (permisos 600) o la ventana. `SecretRedactingFilter` lo censura en registros y mensajes. Las descargas a otro dominio (p. ej. S3) no llevan el token. |
| Límites de la API (CAR-06) | Paginación con la cabecera `Link`; ante 429/403 por límite de tasa espera (`Retry-After` o espera exponencial) y reintenta. |
| Errores sin detener (CAR-31) | Cada entrega y cada archivo fallan solos; el motivo queda en `index.json`. |
| Descompresión segura (CAR-09) | Bloquea rutas fuera de la carpeta, rutas absolutas, enlaces simbólicos, zip bombs (tamaño, número de archivos, tasa de compresión) y anidamiento excesivo. |
| .rar/.7z (CAR-10) | Usa `7z` si está instalado; si no, se marca. |
| Credenciales (CAR-19) | `CredentialPolicy`: `.env`, llaves, `credentials*`… se cuentan pero nunca se abren ni van al modelo. |
| Privacidad (6.1) | `OllamaLanguageModel` rechaza cualquier servidor que no sea local. Las etapas 2 a 5 no usan la red. |
| Cifras veraces (6.1, 7.1) | `NumberGuard` elimina números del texto del modelo; las cifras del CV salen de `facts.json` o de la calificación de Canvas. `TechnologyEvidenceGuard` rechaza tecnologías sin respaldo. |
| Datos dudosos (CAR-21) | El perfil lleva una lista `dudoso` que se muestra en el CV como «⚠ Verificar». |
| Trabajo en equipo (N5) | Los proyectos grupales se marcan en el CV y en el perfil; el porcentaje por commits queda como extensión futura. |
| Rastreabilidad (CAR-26) | Cada viñeta lleva la ruta de la entrega y del archivo que la respalda (`raw/<materia>/<tarea>` → `zip!/ruta/archivo`). |
| Reanudación (9.4) | Los adjuntos ya descargados no se vuelven a bajar; el índice se guarda de forma incremental. |

## Fuera de alcance en este MVP

Lo mismo que marca el documento: clonar repositorios y calcular la aportación por commits (solo se registra el
enlace y se detecta `.git`), OCR, exportación a DOCX/PDF y caché (fase 4).
