# agent/notificaciones.py — Notificaciones por correo al negocio
# Generado por AgentKit

"""
Envía un correo al negocio cada vez que el agente aparta una reservación
nueva en el calendario, para que sepan que hay que confirmarla con el
cliente y registrar el anticipo cuando llegue.
"""

import os
import logging
import smtplib
from email.header import Header

logger = logging.getLogger("agentkit")


def _parsear_destinatarios(destino: str) -> list[str]:
    """
    Convierte "a@x.com, b@y.com" en ["a@x.com", "b@y.com"].
    Permite mandar el aviso a varias personas del negocio a la vez.
    """
    return [correo.strip() for correo in destino.split(",") if correo.strip()]


def _construir_mensaje(datos: dict, origen: str, destinatarios: list[str]) -> str:
    cuerpo = (
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
    asunto = Header(
        f"Nueva reservación: {datos['prefijo']} — {datos['nombre_completo']}", "utf-8"
    ).encode()
    encabezados = (
        f"From: {origen}\r\n"
        f"To: {', '.join(destinatarios)}\r\n"
        f"Subject: {asunto}\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: text/plain; charset="utf-8"\r\n'
        "Content-Transfer-Encoding: 8bit\r\n"
    )
    mensaje = encabezados + "\r\n" + cuerpo
    # Se normaliza a CRLF (RFC 5321): los encabezados ya usan \r\n pero el
    # cuerpo se construyó con \n simples.
    return mensaje.replace("\r\n", "\n").replace("\n", "\r\n")


def enviar_correo_nueva_reservacion(datos: dict, servidor_smtp=None) -> bool:
    """
    Envía el correo de notificación. `servidor_smtp` se puede inyectar en
    pruebas; en producción se conecta a Gmail vía SMTP con una contraseña
    de aplicación.
    """
    origen = os.getenv("NOTIFICACION_EMAIL_ORIGEN")
    password = os.getenv("NOTIFICACION_EMAIL_PASSWORD")
    destino = os.getenv("NOTIFICACION_EMAIL_DESTINO")

    if not all([origen, password, destino]):
        logger.warning("Variables de notificación por correo no configuradas; no se envía correo")
        return False

    destinatarios = _parsear_destinatarios(destino)
    if not destinatarios:
        logger.warning("NOTIFICACION_EMAIL_DESTINO no tiene ningún correo válido; no se envía correo")
        return False

    try:
        mensaje = _construir_mensaje(datos, origen, destinatarios)

        if servidor_smtp is not None:
            servidor_smtp.login(origen, password)
            servidor_smtp.sendmail(origen, destinatarios, mensaje)
        else:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as servidor:
                servidor.login(origen, password)
                # Se codifica a UTF-8 porque el mensaje incluye acentos y
                # smtplib solo acepta texto ASCII puro como str.
                servidor.sendmail(origen, destinatarios, mensaje.encode("utf-8"))
        return True
    except Exception as e:
        logger.error(f"Error enviando correo de notificación: {e}")
        return False
