# agent/tools.py — Herramientas del agente
# Generado por AgentKit

"""
Herramientas específicas del negocio de Quinta Esmeralda.
Cubren los 3 casos de uso elegidos: responder FAQ, agendar reservaciones
y atender ventas de cabañas/eventos.
"""

import os
import yaml
import logging
from contextvars import ContextVar
from datetime import date
from pathlib import Path

from agent import calendar_service, notificaciones
from agent.memory import crear_solicitud_reservacion, listar_solicitudes_reservacion
from agent.memory import pausar_conversacion as pausar_conversacion_db

logger = logging.getLogger("agentkit")

# Teléfono del cliente al que se está atendiendo. main.py lo fija antes de
# llamar al cerebro, para que las herramientas sepan a quién enviarle archivos.
telefono_actual: ContextVar[str] = ContextVar("telefono_actual", default="")

DOCUMENTOS = {
    "informacion": {
        "ruta": Path(__file__).resolve().parent.parent / "assets" / "Quinta-Esmeralda-Informacion.pdf",
        "archivo": "Quinta Esmeralda - Informacion.pdf",
        "texto": "Información de Quinta Esmeralda: cabañas, eventos, precios y reglamento.",
    },
}


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención del negocio."""
    info = cargar_info_negocio()
    return {
        "horario": info.get("negocio", {}).get("horario", "No disponible"),
        "agente_disponible": "24/7",
    }


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    Se usa para responder preguntas frecuentes (precios, reglamento, menú, etc.)
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                # Búsqueda simple por coincidencia de texto
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


# ════════════════════════════════════════════════════════════
# Herramientas de RESERVACIONES / VENTAS
# (cabañas, eventos, campamentos, sesión de fotos, experiencias)
# Usan el calendario real de Google — ver agent/calendar_service.py
# ════════════════════════════════════════════════════════════

async def verificar_disponibilidad(prefijo: str, fecha_entrada: str, fecha_salida: str) -> dict:
    """
    Consulta el calendario real de Quinta Esmeralda. SIEMPRE se debe
    llamar esta función antes de prometerle una fecha a un cliente.

    Args:
        prefijo: uno de "C1", "C2", "C6", "C7", "FAMILIAR", "EVENTO",
                 "CAMPA", "PICNIC"
        fecha_entrada: fecha de entrada, formato YYYY-MM-DD
        fecha_salida: fecha de salida, formato YYYY-MM-DD
    """
    entrada = date.fromisoformat(fecha_entrada)
    salida = date.fromisoformat(fecha_salida)
    return calendar_service.verificar_disponibilidad(prefijo, entrada, salida)


async def crear_reservacion(
    prefijo: str,
    fecha_entrada: str,
    fecha_salida: str,
    nombre_completo: str,
    telefono: str,
    personas: int,
    extras: str = "",
    notas: str = "",
) -> dict:
    """
    Aparta la reservación en el calendario (gris, sin anticipo) y notifica
    por correo al negocio. Solo llamar después de confirmar disponibilidad
    con verificar_disponibilidad Y de que el cliente confirmó que quiere
    apartar.
    """
    entrada = date.fromisoformat(fecha_entrada)
    salida = date.fromisoformat(fecha_salida)

    resultado_calendario = calendar_service.crear_reservacion_calendario(
        prefijo, entrada, salida, nombre_completo, telefono, personas, extras, notas,
    )

    datos_correo = {
        "prefijo": prefijo,
        "nombre_completo": nombre_completo,
        "telefono": telefono,
        "personas": personas,
        "fecha_entrada": fecha_entrada,
        "fecha_salida": fecha_salida,
        "link": resultado_calendario["link"],
    }
    correo_enviado = notificaciones.enviar_correo_nueva_reservacion(datos_correo)
    if not correo_enviado:
        logger.warning(
            f"No se pudo enviar el correo de notificación para la reservación {resultado_calendario['event_id']}"
        )

    try:
        await crear_solicitud_reservacion(
            telefono=telefono,
            tipo=prefijo,
            detalle=f"{personas} personas. {extras}".strip(),
            fecha_solicitada=f"{fecha_entrada} a {fecha_salida}",
            nombre_contacto=nombre_completo,
            event_id=resultado_calendario["event_id"],
        )
    except Exception as e:
        logger.error(
            f"Reservación creada en el calendario ({resultado_calendario['event_id']}) pero "
            f"no se pudo guardar la copia local en SQLite: {e}"
        )

    logger.info(
        f"Reservación completada: {resultado_calendario['event_id']} — {prefijo} para {telefono}"
    )

    return {
        "event_id": resultado_calendario["event_id"],
        "link": resultado_calendario["link"],
        "mensaje": (
            "Su solicitud quedó apartada en nuestro calendario. Nuestro equipo se "
            "pondrá en contacto para confirmar el anticipo. Recuerde que, por "
            "política de la empresa, no se realizan cancelaciones ni devoluciones "
            "en cabañas ni eventos."
        ),
    }


async def consultar_mis_solicitudes(telefono: str) -> list[dict]:
    """Devuelve las solicitudes de reservación previas de un cliente."""
    return await listar_solicitudes_reservacion(telefono=telefono)


def obtener_contacto_humano() -> dict:
    """Retorna los datos de contacto para escalar a una persona del equipo."""
    return {
        "whatsapp": "272 258 6606",
        "llamadas": "272 783 0327",
        "mensaje": "Puede escribir a este WhatsApp o llamar al 272 783 0327 (solo llamadas).",
    }


async def enviar_documento(nombre: str) -> dict:
    """Envía por WhatsApp al cliente actual un documento del negocio."""
    doc = DOCUMENTOS.get(nombre)
    telefono = telefono_actual.get()
    if doc is None:
        return {"enviado": False, "error": f"Documento desconocido: {nombre}"}
    if not telefono:
        return {"enviado": False, "error": "No se sabe a qué cliente enviarlo"}
    from agent.providers import obtener_proveedor
    ok = await obtener_proveedor().enviar_documento(telefono, str(doc["ruta"]), doc["archivo"], doc["texto"])
    return {"enviado": True} if ok else {"enviado": False, "error": "No se pudo enviar el archivo"}

async def pausar_conversacion(motivo: str = "") -> dict:
    """Pone en pausa al asistente para el cliente actual (despedida o pide una persona)."""
    telefono = telefono_actual.get()
    if not telefono:
        return {"pausada": False, "error": "No se sabe a qué cliente pausar"}
    await pausar_conversacion_db(telefono)
    logger.info(f"Asistente en pausa para {telefono}: {motivo}")
    return {"pausada": True}
