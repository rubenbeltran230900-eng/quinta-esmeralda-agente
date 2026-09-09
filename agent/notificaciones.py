# agent/notificaciones.py — Notificaciones por correo al negocio (vía Resend)
# Generado por AgentKit

"""
Envía un correo al negocio cada vez que el agente aparta una reservación
nueva en el calendario, para que sepan que hay que confirmarla con el
cliente y registrar el anticipo cuando llegue.

Usa la API HTTP de Resend en vez de SMTP: en Railway, las conexiones SMTP
salientes (probamos los puertos 465 y 587) fallaron de forma intermitente
con "Network is unreachable" — HTTPS es mucho más confiable en la mayoría
de plataformas de hosting, que sí suelen dejar pasar tráfico web normal
aunque bloqueen SMTP.
"""

import os
import logging
import httpx

logger = logging.getLogger("agentkit")

RESEND_API_URL = "https://api.resend.com/emails"


def _parsear_destinatarios(destino: str) -> list[str]:
    """
    Convierte "a@x.com, b@y.com" en ["a@x.com", "b@y.com"].
    Permite mandar el aviso a varias personas del negocio a la vez.
    """
    return [correo.strip() for correo in destino.split(",") if correo.strip()]


def _construir_cuerpo(datos: dict) -> str:
    return (
        "Nueva solicitud de reservación por WhatsApp\n\n"
        f"Recurso:        {datos['prefijo']}\n"
        f"Cliente:        {datos['nombre_completo']}\n"
        f"Teléfono:       {datos['telefono']}\n"
        f"Personas:       {datos['personas']}\n"
        f"Fecha entrada:  {datos['fecha_entrada']}\n"
        f"Fecha salida:   {datos['fecha_salida']}\n"
        f"Evento en calendario: {datos['link']}\n\n"
        "Está apartada en gris (sin anticipo). Confirma con el cliente y,\n"
        "cuando llegue el anticipo, actualiza el evento a color según la guía."
    )


def enviar_correo_nueva_reservacion(datos: dict, cliente_http=None) -> bool:
    """
    Envía el correo de notificación vía la API de Resend.

    `cliente_http` se puede inyectar en pruebas — debe exponer un método
    `.post(url, json=..., headers=...)` que retorne un objeto con
    `.status_code` y `.text`. En producción se usa un `httpx.Client` real.
    """
    api_key = os.getenv("RESEND_API_KEY")
    origen = os.getenv("RESEND_FROM")
    destino = os.getenv("NOTIFICACION_EMAIL_DESTINO")

    if not all([api_key, origen, destino]):
        logger.warning("Variables de notificación por correo (Resend) no configuradas; no se envía correo")
        return False

    destinatarios = _parsear_destinatarios(destino)
    if not destinatarios:
        logger.warning("NOTIFICACION_EMAIL_DESTINO no tiene ningún correo válido; no se envía correo")
        return False

    payload = {
        "from": origen,
        "to": destinatarios,
        "subject": f"Nueva reservación: {datos['prefijo']} — {datos['nombre_completo']}",
        "text": _construir_cuerpo(datos),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        if cliente_http is not None:
            respuesta = cliente_http.post(RESEND_API_URL, json=payload, headers=headers)
        else:
            with httpx.Client(timeout=10) as cliente:
                respuesta = cliente.post(RESEND_API_URL, json=payload, headers=headers)

        if respuesta.status_code >= 400:
            logger.error(f"Resend rechazó el correo [{respuesta.status_code}]: {respuesta.text[:300]}")
            return False
        return True
    except Exception as e:
        logger.error(f"Error enviando correo de notificación (Resend): {e}")
        return False
