# agent/pausa.py — Pausa del asistente y palabra para reactivarlo

"""
Cuando la conversación termina (despedida) o el cliente pide hablar con una
persona, el asistente se pone en pausa y deja de responder ese chat. Solo se
reactiva si el cliente escribe la palabra clave (por defecto "asistente").
"""

import os
import re
import unicodedata

from agent import memory

MENSAJE_PAUSA = (
    "El asistente virtual está en pausa en esta conversación. Si desea que "
    "le atienda de nuevo, escriba la palabra ASISTENTE. Si prefiere hablar "
    "con una persona, puede llamar al 272 783 0327."
)


def palabra_reactivar() -> str:
    return (os.getenv("PALABRA_REACTIVAR") or "asistente").strip().lower()


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in sin_acentos if unicodedata.category(c) != "Mn")


def contiene_palabra_reactivar(texto: str) -> bool:
    palabra = re.escape(_normalizar(palabra_reactivar()))
    return re.search(rf"\b{palabra}\b", _normalizar(texto)) is not None


async def evaluar(telefono: str, texto: str) -> str:
    """
    Decide qué hacer con un mensaje entrante:
      "atender"  -> responde el asistente (no había pausa, o la palabra la quitó)
      "recordar" -> hay pausa y aún no se le avisó al cliente: mandar MENSAJE_PAUSA
      "ignorar"  -> hay pausa y ya se le avisó: no responder
    """
    if not await memory.esta_pausada(telefono):
        return "atender"
    if contiene_palabra_reactivar(texto):
        await memory.reactivar_conversacion(telefono)
        return "atender"
    if await memory.marcar_recordatorio_pausa(telefono):
        return "recordar"
    return "ignorar"
