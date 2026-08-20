# agent/calendar_service.py — Integración con Google Calendar (disponibilidad real)
# Generado por AgentKit

"""
Consulta y actualiza el calendario de Google que ya usa Quinta Esmeralda
para llevar sus reservaciones. Ver docs/calendario-reservas.html para la
convención completa de nomenclatura, colores y descripción de eventos —
este módulo la reproduce en código, no la reinventa.
"""

import os
import json
import logging
from datetime import date

from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger("agentkit")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Color "Grafito" en Google Calendar — el gris de "apartado sin anticipo"
COLOR_ID_GRIS = "8"

# Prefijo -> capacidad real. "grupo" agrupa recursos intercambiables (las
# dos cabañas de 4 personas son idénticas: lo que importa es cuántas de
# las dos quedan libres, no cuál en particular). CAMPA y PICNIC no ocupan
# un recurso físico limitado, así que su capacidad es efectivamente
# ilimitada — nunca bloquean disponibilidad por sí mismos, pero sí quedan
# bloqueados si hay un evento exclusivo ese día.
RECURSOS = {
    "C1": {"unidades": 1, "grupo": "cabana_4p"},
    "C2": {"unidades": 1, "grupo": "cabana_4p"},
    "C6": {"unidades": 1, "grupo": None},
    "C7": {"unidades": 1, "grupo": None},
    "FAMILIAR": {"unidades": 1, "grupo": None},
    "EVENTO": {"unidades": 3, "grupo": None},
    "CAMPA": {"unidades": 9999, "grupo": None},
    "PICNIC": {"unidades": 9999, "grupo": None},
}

_cliente = None


def obtener_servicio():
    """Crea (una sola vez) el cliente autenticado de la API de Google Calendar."""
    global _cliente
    if _cliente is not None:
        return _cliente
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON no configurado en .env")
    info = json.loads(creds_json)
    credenciales = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    _cliente = build("calendar", "v3", credentials=credenciales)
    return _cliente


def _obtener_calendar_id(calendar_id: str | None) -> str:
    if calendar_id:
        return calendar_id
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID")
    if not calendar_id:
        raise RuntimeError("GOOGLE_CALENDAR_ID no configurado en .env")
    return calendar_id


def _capacidad_total(prefijo: str) -> int:
    if prefijo not in RECURSOS:
        raise ValueError(f"Prefijo de recurso desconocido: {prefijo}")
    grupo = RECURSOS[prefijo]["grupo"]
    if grupo:
        return sum(1 for r in RECURSOS.values() if r["grupo"] == grupo)
    return RECURSOS[prefijo]["unidades"]


def _prefijos_del_grupo(prefijo: str) -> list[str]:
    grupo = RECURSOS[prefijo]["grupo"]
    if grupo:
        return [p for p, r in RECURSOS.items() if r["grupo"] == grupo]
    return [prefijo]


def _listar_eventos_rango(servicio, calendar_id: str, fecha_entrada: date, fecha_salida: date) -> list[dict]:
    time_min = f"{fecha_entrada.isoformat()}T00:00:00-06:00"
    time_max = f"{fecha_salida.isoformat()}T00:00:00-06:00"
    resultado = servicio.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return resultado.get("items", [])


def _hay_evento_exclusivo(eventos: list[dict]) -> bool:
    return any("EXCLUSIVO" in evento.get("description", "") for evento in eventos)


def _titulo_pertenece_a_prefijo(titulo: str, prefijo: str) -> bool:
    titulo_limpio = titulo.lstrip("?").strip()
    return titulo_limpio == prefijo or titulo_limpio.startswith(f"{prefijo} ")


def verificar_disponibilidad(
    prefijo: str,
    fecha_entrada: date,
    fecha_salida: date,
    servicio=None,
    calendar_id: str | None = None,
) -> dict:
    """
    Revisa el calendario real y dice si hay unidades libres de `prefijo`
    entre `fecha_entrada` (incluida) y `fecha_salida` (el día de salida —
    el evento cubre las noches entre ambas fechas, no ese último día).
    """
    servicio = servicio or obtener_servicio()
    calendar_id = _obtener_calendar_id(calendar_id)

    eventos = _listar_eventos_rango(servicio, calendar_id, fecha_entrada, fecha_salida)

    if _hay_evento_exclusivo(eventos):
        return {"disponible": False, "razon": "evento_exclusivo", "ocupados": None, "capacidad": None}

    prefijos_grupo = _prefijos_del_grupo(prefijo)
    ocupados = sum(
        1 for evento in eventos
        if any(_titulo_pertenece_a_prefijo(evento.get("summary", ""), p) for p in prefijos_grupo)
    )
    capacidad = _capacidad_total(prefijo)

    return {"disponible": ocupados < capacidad, "ocupados": ocupados, "capacidad": capacidad}


def _construir_descripcion(nombre_completo: str, telefono: str, personas: int, extras: str, notas: str) -> str:
    return (
        f"Cliente:   {nombre_completo}\n"
        f"Teléfono:  {telefono}\n"
        f"Personas:  {personas}\n"
        f"Anticipo:  $______   (fecha y forma de pago)\n"
        f"Resta:     $______\n"
        f"Extras:    {extras}\n"
        f"Notas:     {notas}"
    )


def crear_reservacion_calendario(
    prefijo: str,
    fecha_entrada: date,
    fecha_salida: date,
    nombre_completo: str,
    telefono: str,
    personas: int,
    extras: str = "",
    notas: str = "",
    servicio=None,
    calendar_id: str | None = None,
) -> dict:
    """
    Crea el evento de reservación en gris ("apartado sin anticipo"), con
    signo de interrogación al inicio del título, siguiendo exactamente la
    convención de docs/calendario-reservas.html.
    """
    servicio = servicio or obtener_servicio()
    calendar_id = _obtener_calendar_id(calendar_id)

    titulo = f"? {prefijo} · {nombre_completo} · {personas}p"
    descripcion = _construir_descripcion(nombre_completo, telefono, personas, extras, notas)

    body = {
        "summary": titulo,
        "description": descripcion,
        "start": {"date": fecha_entrada.isoformat()},
        "end": {"date": fecha_salida.isoformat()},
        "colorId": COLOR_ID_GRIS,
    }

    evento_creado = servicio.events().insert(calendarId=calendar_id, body=body).execute()
    logger.info(f"Reservación creada en calendario: {evento_creado['id']} — {titulo}")

    return {"event_id": evento_creado["id"], "link": evento_creado.get("htmlLink", "")}
