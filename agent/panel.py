# agent/panel.py — Panel de solo lectura para ver las conversaciones

"""
Página protegida con usuario y contraseña donde el equipo puede leer las
conversaciones que el asistente ha tenido con los clientes. Es de SOLO
LECTURA: desde aquí no se envía ni se modifica nada.

Se activa definiendo PANEL_PASSWORD (y opcionalmente PANEL_USUARIO) en las
variables de entorno. Sin contraseña configurada, el panel queda apagado.
"""

import os
import secrets
from datetime import timezone
from html import escape
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, select

from agent import memory

router = APIRouter()
_seguridad = HTTPBasic(auto_error=False)
ZONA = ZoneInfo("America/Mexico_City")

ESTILOS = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<style>
  body{font-family:system-ui,sans-serif;margin:0;background:#f2f4f1;color:#1c2b22}
  header{background:#1f5c3d;color:#fff;padding:14px 16px;font-weight:600}
  header a{color:#fff;text-decoration:none}
  main{max-width:720px;margin:0 auto;padding:12px 16px 40px}
  .chat{display:block;background:#fff;border-radius:10px;padding:12px 14px;margin:10px 0;
        text-decoration:none;color:inherit;box-shadow:0 1px 2px rgba(0,0,0,.08)}
  .chat b{display:block}
  .chat small,.hora{color:#6b7a70;font-size:12px}
  .previa{color:#44524a;font-size:14px;margin-top:4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
  .pausa{background:#fde9b8;color:#6b4a00;border-radius:6px;padding:1px 6px;font-size:12px;margin-left:6px}
  .msg{max-width:82%;padding:8px 11px;border-radius:10px;margin:8px 0;white-space:pre-wrap;word-wrap:break-word;font-size:15px}
  .user{background:#fff;margin-right:auto}
  .assistant{background:#d9f2df;margin-left:auto}
  .aviso{background:#fde9b8;border-radius:10px;padding:10px 12px;margin:10px 0;font-size:14px}
</style>
"""


def _verificar_acceso(credenciales: HTTPBasicCredentials | None = Depends(_seguridad)):
    password = os.getenv("PANEL_PASSWORD") or ""
    usuario = os.getenv("PANEL_USUARIO") or "quinta"
    if not password:
        raise HTTPException(status_code=503, detail="Panel no configurado")
    ok = (
        credenciales is not None
        and secrets.compare_digest(credenciales.username.encode(), usuario.encode())
        and secrets.compare_digest(credenciales.password.encode(), password.encode())
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Acceso restringido",
            headers={"WWW-Authenticate": 'Basic realm="Quinta Esmeralda"'},
        )


def _hora_local(fecha) -> str:
    """Los timestamps se guardan en UTC sin zona; se muestran en hora de Veracruz."""
    if fecha is None:
        return ""
    return fecha.replace(tzinfo=timezone.utc).astimezone(ZONA).strftime("%d/%m/%Y %H:%M")


def _pagina(titulo: str, cuerpo: str) -> HTMLResponse:
    html = (
        f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{escape(titulo)}</title>"
        f"{ESTILOS}</head><body>{cuerpo}</body></html>"
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


async def listar_conversaciones() -> list[dict]:
    """Una fila por cliente, con su último mensaje, de la más reciente a la más antigua."""
    async with memory.async_session() as session:
        ultimos = (
            select(memory.Mensaje.telefono, func.max(memory.Mensaje.id).label("ultimo_id"))
            .group_by(memory.Mensaje.telefono)
            .subquery()
        )
        filas = (
            await session.execute(
                select(memory.Mensaje)
                .join(ultimos, memory.Mensaje.id == ultimos.c.ultimo_id)
                .order_by(memory.Mensaje.id.desc())
            )
        ).scalars().all()
        pausados = set(
            (await session.execute(select(memory.PausaConversacion.telefono))).scalars().all()
        )
    return [
        {
            "telefono": m.telefono,
            "ultimo": m.content,
            "fecha": m.timestamp,
            "pausada": m.telefono in pausados,
        }
        for m in filas
    ]


async def obtener_conversacion(telefono: str, limite: int = 300) -> list[dict]:
    """Los últimos mensajes de un cliente, en orden cronológico."""
    async with memory.async_session() as session:
        filas = (
            await session.execute(
                select(memory.Mensaje)
                .where(memory.Mensaje.telefono == telefono)
                .order_by(memory.Mensaje.id.desc())
                .limit(limite)
            )
        ).scalars().all()
    return [
        {"role": m.role, "content": m.content, "fecha": m.timestamp}
        for m in reversed(filas)
    ]


@router.get("/panel", response_class=HTMLResponse, dependencies=[Depends(_verificar_acceso)])
async def panel_lista():
    conversaciones = await listar_conversaciones()
    if not conversaciones:
        items = "<p>Todavía no hay conversaciones.</p>"
    else:
        items = "".join(
            f"<a class='chat' href='/panel/{escape(c['telefono'], quote=True)}'>"
            f"<b>+{escape(c['telefono'])}"
            f"{'<span class=pausa>asistente en pausa</span>' if c['pausada'] else ''}</b>"
            f"<small>{_hora_local(c['fecha'])}</small>"
            f"<div class='previa'>{escape(c['ultimo'][:120])}</div></a>"
            for c in conversaciones
        )
    return _pagina(
        "Conversaciones — Quinta Esmeralda",
        f"<header>Conversaciones de WhatsApp</header><main>{items}</main>",
    )


@router.get("/panel/{telefono}", response_class=HTMLResponse, dependencies=[Depends(_verificar_acceso)])
async def panel_conversacion(telefono: str):
    mensajes = await obtener_conversacion(telefono)
    if not mensajes:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    aviso = ""
    if await memory.esta_pausada(telefono):
        aviso = (
            "<div class='aviso'>El asistente está en pausa en este chat. Solo vuelve a "
            "responder si el cliente escribe ASISTENTE.</div>"
        )
    burbujas = "".join(
        f"<div class='msg {'user' if m['role'] == 'user' else 'assistant'}'>"
        f"{escape(m['content'])}<div class='hora'>"
        f"{'Cliente' if m['role'] == 'user' else 'Asistente'} · {_hora_local(m['fecha'])}</div></div>"
        for m in mensajes
    )
    return _pagina(
        f"+{telefono}",
        f"<header><a href='/panel'>← Conversaciones</a> · +{escape(telefono)}</header>"
        f"<main>{aviso}{burbujas}</main>",
    )
