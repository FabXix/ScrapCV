"""Traduce errores técnicos a mensajes que dicen qué pasó y qué hacer."""
from __future__ import annotations

from scrapcv.bootstrap import MissingTokenError
from scrapcv.infrastructure.canvas.http_client import CanvasAuthError, CanvasHttpError, InsecureCanvasUrl
from scrapcv.infrastructure.logging_setup import REDACTOR
from scrapcv.infrastructure.ollama import LanguageModelError, RemoteModelRejected
from scrapcv.infrastructure.storage import CorruptDataError


def friendly_error(error: BaseException) -> tuple[str, str]:
    """(título corto, explicación con el siguiente paso)."""
    detail = REDACTOR.redact(str(error) or error.__class__.__name__)
    if isinstance(error, CanvasAuthError):
        return ("Canvas rechazó tu token",
                "El token no es válido o ya expiró. Genera uno nuevo en Canvas › Cuenta › Configuración › "
                "«Nuevo token de acceso» y pégalo en el paso 1.")
    if isinstance(error, MissingTokenError):
        return ("Falta tu token de Canvas",
                "Pega tu token en el paso 1 · Conectar, o elige «Probar con datos de ejemplo».")
    if isinstance(error, InsecureCanvasUrl):
        return ("La dirección de Canvas no es segura",
                "Debe empezar con https:// (por ejemplo https://canvas.iteso.mx). Cámbiala en Opciones avanzadas.")
    if isinstance(error, CanvasHttpError):
        return ("No se pudo hablar con Canvas",
                f"Revisa tu conexión a internet e inténtalo de nuevo. Lo que ya se descargó no se pierde.\n\n{detail}")
    if isinstance(error, RemoteModelRejected):
        return ("Ollama debe estar en tu computadora",
                "Por privacidad solo se acepta Ollama local (http://localhost:11434). Cámbialo en Opciones avanzadas.")
    if isinstance(error, LanguageModelError):
        return ("La IA no respondió",
                "Abre Ollama y vuelve a intentarlo, o desactiva «Redactar con IA» en el paso 1: el CV se arma igual "
                f"con reglas.\n\n{detail}")
    if isinstance(error, CorruptDataError):
        return ("Un archivo de datos está dañado", detail)
    if isinstance(error, PermissionError):
        return ("No se pudo escribir el archivo",
                "Probablemente está abierto en otro programa (Word o el navegador). Ciérralo e inténtalo de nuevo.")
    if isinstance(error, ValueError):
        return ("Revisa los datos", detail)
    return ("Algo salió mal", f"{detail}\n\nLos detalles quedaron en el registro (botón «Ver registro»).")
