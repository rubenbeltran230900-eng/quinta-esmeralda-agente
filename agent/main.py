# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp de Quinta Esmeralda.
Funciona con cualquier proveedor (Meta, Twilio) gracias a la capa de providers.
"""

import os
import asyncio
import logging
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db,
    guardar_mensaje,
    obtener_historial,
    marcar_evento_procesado,
    limpiar_eventos_viejos,
)
from agent.providers import obtener_proveedor

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Cuántos segundos se espera, sin recibir un mensaje nuevo de ese mismo
# número, antes de procesar lo que se acumuló. Es normal que alguien en
# WhatsApp escriba en varios mensajes cortos seguidos ("Ruben Beltran",
# luego el teléfono, luego "7") en vez de uno solo: sin esto, el agente
# respondería a cada fragmento por separado, sin ver el resto.
SEGUNDOS_DEBOUNCE = 6

# Mensajes de texto acumulados por teléfono, esperando a que pase el
# tiempo de "debounce" para procesarse juntos como un solo turno.
_buffer_mensajes: dict[str, list[str]] = defaultdict(list)

# La tarea de espera vigente por teléfono. Si llega un mensaje nuevo antes
# de que termine de esperar, se cancela y se agenda una tarea nueva —
# así el reloj se reinicia con cada mensaje.
_tareas_debounce: dict[str, asyncio.Task] = {}

# Un candado por teléfono: evita que dos ráfagas de mensajes del mismo
# número se procesen en paralelo y pisen el historial una de la otra.
_candados: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Teléfonos cuya ráfaga se está procesando AHORA MISMO (ya pasó la espera,
# ya está dentro del candado). Sirve para no cancelar a medias una
# reservación que ya se estaba creando: solo se cancelan tareas que
# todavía están esperando, nunca una que ya empezó a procesar.
_procesando: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    await limpiar_eventos_viejos()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="Quinta Esmeralda — WhatsApp AI Agent",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "quinta-esmeralda-agent"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp vía el proveedor configurado.

    Responde 200 de inmediato — NO espera a que Claude genere la respuesta
    ni a que se envíe de vuelta. Si el servidor tardara en contestar, Meta
    asumiría que el webhook falló y reintentaría el mismo mensaje hasta 7
    veces, lo que ya nos causó reservaciones duplicadas en el calendario.
    El trabajo de verdad ocurre en segundo plano, en _agendar_mensaje.
    """
    try:
        mensajes = await proveedor.parsear_webhook(request)
    except Exception as e:  # noqa: BLE001 — un payload raro no debe tumbar el webhook
        logger.error(f"Error leyendo el webhook: {e}")
        return {"status": "ignorado"}

    for msg in mensajes:
        if msg.es_propio or not msg.texto:
            continue

        # Meta entrega "al menos una vez": el mismo mensaje puede llegar
        # dos veces (reintento). Sin esto, cada reintento se procesaría
        # como si fuera un mensaje nuevo.
        if not await marcar_evento_procesado(msg.mensaje_id):
            logger.info(f"Mensaje repetido, se ignora: {msg.mensaje_id}")
            continue

        logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")
        _buffer_mensajes[msg.telefono].append(msg.texto)
        _agendar_procesamiento(msg.telefono)

    return {"status": "ok"}


def _agendar_procesamiento(telefono: str):
    """
    (Re)inicia el reloj de espera para ese teléfono.

    Si ya había una tarea esperando (todavía no procesando) para este
    número, se cancela — así un mensaje nuevo "reinicia" la espera en vez
    de disparar un procesamiento aparte para cada fragmento. Si la tarea
    previa YA está procesando (ver `_procesando`), no se toca: cancelarla
    a medias podría dejar una reservación a medio crear. El mensaje nuevo
    ya quedó en el buffer, así que lo recoge la tarea que se agenda abajo
    en cuanto la que está en curso libere el candado.
    """
    tarea_previa = _tareas_debounce.get(telefono)
    if tarea_previa is not None and not tarea_previa.done() and telefono not in _procesando:
        tarea_previa.cancel()
    _tareas_debounce[telefono] = asyncio.create_task(_esperar_y_procesar(telefono))


async def _esperar_y_procesar(telefono: str):
    """Espera SEGUNDOS_DEBOUNCE; si nadie la cancela, procesa lo acumulado."""
    try:
        await asyncio.sleep(SEGUNDOS_DEBOUNCE)
    except asyncio.CancelledError:
        return  # llegó otro mensaje: la tarea nueva se encarga

    async with _candados[telefono]:
        _procesando.add(telefono)
        try:
            mensajes_pendientes = _buffer_mensajes.pop(telefono, [])
            if not mensajes_pendientes:
                return  # ya los proceso otra tarea (no debería pasar, pero por si acaso)
            texto_combinado = "\n".join(mensajes_pendientes)
            await _procesar_mensaje(telefono, texto_combinado)
        finally:
            _procesando.discard(telefono)


async def _procesar_mensaje(telefono: str, texto: str):
    """Genera la respuesta con Claude y la manda de vuelta por WhatsApp."""
    try:
        # El historial se lee ANTES de guardar el mensaje actual
        # (brain.py agrega el mensaje actual, evitando duplicados)
        historial = await obtener_historial(telefono)

        respuesta = await generar_respuesta(texto, historial)

        await guardar_mensaje(telefono, "user", texto)
        await guardar_mensaje(telefono, "assistant", respuesta)

        enviado = await proveedor.enviar_mensaje(telefono, respuesta)
        if not enviado:
            logger.error(f"No se pudo enviar la respuesta a {telefono}")

        logger.info(f"Respuesta a {telefono}: {respuesta}")

    except Exception as e:  # noqa: BLE001 — un fallo aquí no debe tumbar el servidor
        logger.exception(f"Error procesando el mensaje de {telefono}: {e}")
