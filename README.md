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
   (o define `CANVAS_TOKEN`). La URL de Canvas debe ser `https://`. «Recordar» guarda el token en el llavero del
   sistema (`keyring`), nunca en un archivo. Si tienes Ollama, elige el modelo; si no, el CV se arma con reglas.
   Completa también carrera, institución, periodo, LinkedIn y GitHub (Canvas no los tiene).
2. **Evidencia**: *Ejecutar todo* descarga, extrae hechos y genera perfiles. Cada etapa también tiene su propio botón.
3. **Currículum** (el principio de *Resume Optimizer* de PartyRock, al revés: la vacante genera el CV):
   - **Vacante**: pega la descripción completa. ScrapCV separa requisitos indispensables, deseables, habilidades
     blandas y otras condiciones (inglés, semestre…) y elige los proyectos que los demuestran.
   - **Currículum**: el CV a la medida, editable, con *Vista previa / PDF* (HTML listo para imprimir) y *Word*.
     Puedes pedir cambios al asesor (Ollama) en lenguaje natural.
   - **Análisis**: porcentaje de coincidencia (calculado con la evidencia, no estimado por el modelo), lo que ya
     demuestras, brechas, sugerencias y lo que debes revisar antes de enviarlo.

   Sin vacante, elige un puesto del catálogo o uno personalizado con palabras clave.

Pruebas: `pip install -r requirements-dev.txt` y luego `python -m pytest`.

## Qué queda en disco

```
data/raw/<materia>/<tarea>/       evidencia: adjuntos, submission.json, texto_en_linea.html, enlaces.json
data/analysis/<materia>/<tarea>/  facts.json, contexto.json, perfil.json, unpacked/
data/index.json                   estado de cada entrega por etapa, con motivos
data/cv/cv_<puesto>.md            borrador;  cv_<puesto>_final.md  aprobado
data/cv/cv_<puesto>.evidencia.json  de dónde sale cada proyecto y habilidad del CV (fuera del documento)
data/cv/cv_<puesto>.html | .docx  exportaciones para enviar
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
| `domain/` | Entidades puras: `Submission`, `IndexEntry`, `Facts`, `ProjectProfile`, `JobPosting` y el catálogo de tecnologías. |
| `ports.py` | Interfaces pequeñas: `CanvasReader`, `AttachmentDownloader`, `IndexRepository`, `AnalysisStore`, `LanguageModel`, `ProjectProfiler`, `ProgressListener`… |
| `infrastructure/` | Adaptadores: API de Canvas, Canvas simulado, disco (JSON), Ollama, configuración y registros. |
| `extraction/` | Analizador estático y un extractor por formato. |
| `analysis/` | Contexto acotado, perfiles y lectura de vacantes (LLM / reglas / con respaldo), guardas de veracidad. |
| `ranking/` | Puestos o vacante, criterios de puntuación, filtros de elegibilidad y cálculo del match. |
| `writing/` | Plantillas, prompts, escritores (IA / reglas), armado del CV, formato y exportación HTML/DOCX. |
| `application/` | Casos de uso: ingesta, extracción, perfiles, CV y la fachada. |
| `ui/` | Ventana, pestañas, controlador y ejecución en segundo plano. |

### Principios SOLID en el código

- **S (responsabilidad única)**: `CanvasHttpClient` solo habla HTTP (paginación, reintentos); `CanvasApiGateway`
  solo traduce JSON a entidades; `StaticAnalyzer` recorre y delega. En el CV: `prompts.py` solo guarda el texto
  para el modelo, `LlmResumeWriter` solo llama al modelo, `RuleBasedResumeWriter` solo arma los textos de respaldo,
  `WriterChain` decide a quién preguntar, `ResumeBuilder` solo ordena y da formato y `CvAdvisor` compara con la
  vacante. `bootstrap.py` crea el modelo de lenguaje una sola vez (`_language_model`) y lo pasa a cada pieza.
- **O (abierto/cerrado)**: un formato nuevo es una clase `FormatExtractor` registrada en `extraction/factory.py`
  (ver `test_new_format_only_needs_a_new_class`). Un criterio de ranking nuevo es un `ProjectScorer`; una regla
  de elegibilidad es un `CandidateFilter`; un formato de exportación es un `CvExporter`; otro proveedor de IA es
  otro `LanguageModel` (los escritores no cambian); una tecnología nueva es una línea en `domain/skills.py`.
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
| Token seguro (CAR-01) | Variable `CANVAS_TOKEN`, la ventana o el llavero del sistema (`keyring`); nunca en texto plano. Un token que versiones anteriores dejaron en `config.json` se mueve al llavero y se borra del archivo. `config.json` nace con permisos 600 (escritura atómica). `SecretRedactingFilter` lo censura en registros y mensajes. |
| Token solo a Canvas | `CanvasHttpClient` exige `https://` y solo envía `Authorization` al mismo host por https: la paginación (`Link: next`), las URL absolutas y las descargas a otro dominio (p. ej. S3) no lo llevan. |
| Límites de la API (CAR-06) | Paginación con la cabecera `Link`; ante 429/403 por límite de tasa espera (`Retry-After` o espera exponencial) y reintenta. |
| Errores sin detener (CAR-31) | Cada entrega y cada archivo fallan solos; el motivo queda en `index.json`. |
| Descompresión segura (CAR-09) | Bloquea rutas fuera de la carpeta, rutas absolutas, enlaces simbólicos, zip bombs (tamaño, número de archivos, tasa de compresión) y anidamiento excesivo. |
| .rar/.7z (CAR-10) | Usa `7z` si está instalado; si no, se marca. Aplica los mismos límites que .zip/.tar, con los tamaños declarados (antes de extraer) y con lo que quedó en disco (después); rechaza enlaces simbólicos. |
| Datos guardados | Un JSON dañado (`index.json`, perfiles, hechos) no se confunde con uno vacío: se aparta como `*.danado-<fecha>` y el proceso se detiene, así el siguiente guardado no borra el índice. |
| Credenciales (CAR-19) | `CredentialPolicy`: `.env`, llaves, `credentials*`… se cuentan pero nunca se abren ni van al modelo. |
| Privacidad (6.1) | `OllamaLanguageModel` rechaza cualquier servidor que no sea local. Las etapas 2 a 5 no usan la red. |
| Cifras veraces (6.1, 7.1) | `NumberGuard` elimina números del texto del modelo; las cifras del CV salen de `facts.json` o de la calificación de Canvas. `TechnologyEvidenceGuard` rechaza tecnologías sin respaldo. |
| Datos dudosos (CAR-21) | El perfil lleva una lista `dudoso`; se muestra en el panel «Antes de enviarlo», fuera del CV. |
| Vacante sin invención | Lo que el modelo extrae de la vacante debe aparecer en su texto; el % de match se calcula con la evidencia. |
| Trabajo en equipo (N5) | Los proyectos grupales se marcan en el CV y en el perfil; el porcentaje por commits queda como extensión futura. |
| Rastreabilidad (CAR-26) | El CV para enviar guarda su evidencia en `cv_<puesto>.evidencia.json`; el formato «Borrador con evidencia» muestra la ruta en cada viñeta (`raw/<materia>/<tarea>` → `zip!/ruta/archivo`). |
| Reanudación (9.4) | Los adjuntos ya descargados no se vuelven a bajar; el índice se guarda de forma incremental. |

## Fuera de alcance en este MVP

Lo mismo que marca el documento: clonar repositorios y calcular la aportación por commits (solo se registra el
enlace y se detecta `.git`), OCR y caché (fase 4). La exportación a Word y a HTML imprimible (PDF desde el
navegador) ya está disponible.
