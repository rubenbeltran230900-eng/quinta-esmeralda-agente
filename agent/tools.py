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
from datetime import date

from agent import calendar_service, notificaciones
from agent.memory import crear_solicitud_reservacion, listar_solicitudes_reservacion

logger = logging.getLogger("agentkit")


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

    await crear_solicitud_reservacion(
        telefono=telefono,
        tipo=prefijo,
        detalle=f"{personas} personas. {extras}".strip(),
        fecha_solicitada=f"{fecha_entrada} a {fecha_salida}",
        nombre_contacto=nombre_completo,
        event_id=resultado_calendario["event_id"],
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
        "telefonos": ["4152 3137", "6185 1364", "272 783 0327"],
        "mensaje": "Puede comunicarse directamente al equipo de Quinta Esmeralda a estos números.",
    }
