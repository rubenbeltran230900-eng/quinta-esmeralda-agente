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
# ════════════════════════════════════════════════════════════

TIPOS_RESERVACION_VALIDOS = {
    "cabana",
    "evento_palapa",
    "evento_exclusivo",
    "campamento",
    "sesion_fotos",
    "noche_romantica",
    "picnic",
}


async def registrar_solicitud_reservacion(
    telefono: str,
    tipo: str,
    detalle: str,
    fecha_solicitada: str,
    nombre_contacto: str = "",
) -> dict:
    """
    Registra una solicitud de reservación pendiente de confirmación.

    Quinta Esmeralda no cuenta con un calendario de disponibilidad en
    tiempo real, así que el agente SIEMPRE registra la solicitud como
    "pendiente" y el equipo humano la confirma por su cuenta (llamando o
    escribiendo al cliente).

    Args:
        telefono: número de WhatsApp del cliente
        tipo: uno de TIPOS_RESERVACION_VALIDOS (si no aplica, usar el más
              cercano, ej. "evento_palapa" para cumpleaños en palapa)
        detalle: descripción libre — qué opción eligió, cuántas personas,
                 si quiere decoración, etc.
        fecha_solicitada: fecha/rango que pidió el cliente, en texto libre
        nombre_contacto: nombre del cliente si lo compartió

    Returns:
        dict con el id de la solicitud y un mensaje de confirmación
    """
    if tipo not in TIPOS_RESERVACION_VALIDOS:
        logger.warning(f"Tipo de reservación no reconocido: {tipo}")

    solicitud_id = await crear_solicitud_reservacion(
        telefono=telefono,
        tipo=tipo,
        detalle=detalle,
        fecha_solicitada=fecha_solicitada,
        nombre_contacto=nombre_contacto,
    )

    logger.info(f"Nueva solicitud de reservación #{solicitud_id} de {telefono}: {tipo} — {detalle}")

    return {
        "solicitud_id": solicitud_id,
        "estado": "pendiente",
        "mensaje": (
            "Su solicitud fue registrada. Nuestro equipo se pondrá en contacto "
            "para confirmar disponibilidad. Recuerde que, por políticas de la "
            "empresa, no se realizan cancelaciones ni devoluciones en cabañas "
            "ni eventos."
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
