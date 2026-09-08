# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente. Lee el system prompt de prompts.yaml y genera
respuestas usando la API de Anthropic Claude, con acceso a herramientas
(tool use) para consultar disponibilidad real y crear reservaciones.
"""

import os
import yaml
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

from agent import tools as agent_tools

load_dotenv()
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

MODELO = "claude-sonnet-5"
MAX_ITERACIONES_HERRAMIENTAS = 5
ZONA_HORARIA_NEGOCIO = ZoneInfo("America/Mexico_City")

DIAS_SEMANA = [
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
]

TOOLS_SCHEMA = [
    {
        "name": "verificar_disponibilidad",
        "description": (
            "Verifica si hay disponibilidad real en el calendario del negocio "
            "para una cabaña o un evento en un rango de fechas. SIEMPRE se debe "
            "llamar esta herramienta antes de prometerle a un cliente que una "
            "fecha está disponible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prefijo": {
                    "type": "string",
                    "enum": ["C1", "C2", "C6", "C7", "FAMILIAR", "EVENTO", "CAMPA", "PICNIC"],
                    "description": (
                        "C1 o C2 = cabaña para 4 personas (hay dos idénticas), "
                        "C6 = cabaña para 2 personas, C7 = cabaña para 10 "
                        "personas, FAMILIAR = cabaña para 15 personas, "
                        "EVENTO = palapa para evento no exclusivo (hay 3), "
                        "CAMPA = campamento de grupo, PICNIC = picnic o "
                        "experiencia especial."
                    ),
                },
                "fecha_entrada": {"type": "string", "description": "Fecha de entrada, formato YYYY-MM-DD"},
                "fecha_salida": {"type": "string", "description": "Fecha de salida, formato YYYY-MM-DD"},
            },
            "required": ["prefijo", "fecha_entrada", "fecha_salida"],
        },
    },
    {
        "name": "crear_reservacion",
        "description": (
            "Aparta una reservación en el calendario del negocio (sin "
            "anticipo, pendiente de confirmación) y notifica al equipo. Solo "
            "usar después de confirmar disponibilidad con "
            "verificar_disponibilidad Y de que el cliente ya confirmó que "
            "quiere apartar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prefijo": {"type": "string", "enum": ["C1", "C2", "C6", "C7", "FAMILIAR", "EVENTO", "CAMPA", "PICNIC"]},
                "fecha_entrada": {"type": "string", "description": "Formato YYYY-MM-DD"},
                "fecha_salida": {"type": "string", "description": "Formato YYYY-MM-DD"},
                "nombre_completo": {"type": "string"},
                "telefono": {"type": "string"},
                "personas": {"type": "integer"},
                "extras": {"type": "string", "description": "Opcional: noche romántica, picnic, decoración"},
                "notas": {"type": "string", "description": "Opcional: cualquier detalle adicional"},
            },
            "required": ["prefijo", "fecha_entrada", "fecha_salida", "nombre_completo", "telefono", "personas"],
        },
    },
]

DISPATCH_HERRAMIENTAS = {
    "verificar_disponibilidad": agent_tools.verificar_disponibilidad,
    "crear_reservacion": agent_tools.crear_reservacion,
}


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def _nota_fecha_actual(ahora: datetime | None = None) -> str:
    """
    Construye la nota que le dice a Claude qué día es hoy.

    Sin esto, Claude no tiene forma de saber la fecha real: cuando un
    cliente dice "el 18 de septiembre" sin año, Claude tiene que inventar
    uno — y puede inventar un año que ya pasó, mandando la reservación al
    pasado (donde nunca la vuelve a encontrar verificar_disponibilidad).
    """
    ahora = ahora or datetime.now(ZONA_HORARIA_NEGOCIO)
    dia_semana = DIAS_SEMANA[ahora.weekday()]
    mes = MESES[ahora.month - 1]
    return (
        "\n\n## Fecha y hora actual\n"
        f"Hoy es {dia_semana} {ahora.day} de {mes} de {ahora.year}, "
        f"{ahora.strftime('%H:%M')} hrs (hora de Veracruz).\n"
        "Cuando el cliente mencione una fecha sin decir el año (por "
        "ejemplo \"el 18 de septiembre\" o \"el próximo sábado\"), calcula "
        "el año usando la fecha de hoy: si esa fecha ya pasó este año, es "
        "del año que sigue; si todavía no llega, es de este año. NUNCA "
        "asumas un año fijo de memoria — siempre calcúlalo a partir de la "
        "fecha de hoy que se te dio arriba."
    )


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def _ejecutar_herramienta(nombre: str, entrada: dict):
    funcion = DISPATCH_HERRAMIENTAS.get(nombre)
    if funcion is None:
        return {"error": f"Herramienta desconocida: {nombre}"}
    try:
        return await funcion(**entrada)
    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return {"error": str(e)}


async def generar_respuesta(mensaje: str, historial: list[dict]) -> str:
    """
    Genera una respuesta usando Claude API, ejecutando las herramientas
    que Claude decida invocar (consultar disponibilidad, crear
    reservaciones) antes de devolver el texto final al cliente.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant", "content": "..."}]

    Returns:
        La respuesta final en texto generada por Claude
    """
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt() + _nota_fecha_actual()

    mensajes = [{"role": m["role"], "content": m["content"]} for m in historial]
    mensajes.append({"role": "user", "content": mensaje})

    try:
        for _ in range(MAX_ITERACIONES_HERRAMIENTAS):
            response = await client.messages.create(
                model=MODELO,
                max_tokens=1024,
                system=system_prompt,
                messages=mensajes,
                tools=TOOLS_SCHEMA,
            )

            if response.stop_reason != "tool_use":
                respuesta = next(
                    (bloque.text for bloque in response.content if bloque.type == "text"),
                    None,
                )
                if not respuesta:
                    logger.error(f"Respuesta de Claude sin bloque de texto: {response.content}")
                    return obtener_mensaje_error()
                logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
                return respuesta

            mensajes.append({"role": "assistant", "content": response.content})

            resultados_herramientas = []
            for bloque in response.content:
                if bloque.type != "tool_use":
                    continue
                resultado = await _ejecutar_herramienta(bloque.name, bloque.input)
                resultados_herramientas.append({
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": str(resultado),
                })
            mensajes.append({"role": "user", "content": resultados_herramientas})

        logger.error("Se alcanzó el máximo de iteraciones de herramientas sin respuesta final")
        return obtener_mensaje_error()

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
