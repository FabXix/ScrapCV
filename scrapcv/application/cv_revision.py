"""Revisión del borrador del CV con el modelo local, a partir de una instrucción libre."""
from __future__ import annotations

import re

from scrapcv.ports import LanguageModel

_SYSTEM = (
    "Eres un editor de currículums. Recibes un CV en Markdown y una instrucción del usuario. "
    "Aplica la instrucción y devuelve el CV completo modificado. Reglas estrictas: conserva el formato Markdown, "
    "las rutas de evidencia y los puntos marcados «Verificar»; NO inventes tecnologías, empresas, fechas ni cifras; "
    "no agregues números que no estén en el texto original. "
    'Responde SOLO con un objeto JSON: {"markdown": "<CV completo>"}.'
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class RevisionRejected(ValueError):
    pass


class CvReviser:
    def __init__(self, model: LanguageModel) -> None:
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model.name

    def revise(self, markdown: str, instruction: str) -> str:
        if not instruction.strip():
            raise RevisionRejected("Escribe qué quieres cambiar.")
        prompt = f"INSTRUCCIÓN:\n{instruction.strip()}\n\nCV ACTUAL:\n{markdown}"
        data = self._model.complete_json(_SYSTEM, prompt)
        revised = data.get("markdown")
        if not isinstance(revised, str) or not revised.strip():
            raise RevisionRejected("El modelo no devolvió un CV válido.")
        invented = set(_NUMBER.findall(revised)) - set(_NUMBER.findall(markdown)) - set(_NUMBER.findall(instruction))
        if invented:
            raise RevisionRejected(
                "El modelo agregó cifras que no están en el CV (" + ", ".join(sorted(invented)[:5]) + "). Cambio descartado."
            )
        return revised.strip() + "\n"
