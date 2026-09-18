# agent/providers/meta.py — Adaptador para Meta WhatsApp Cloud API
# Generado por AgentKit

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN")
        self.phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
        self.verify_token = os.getenv("META_VERIFY_TOKEN", "agentkit-verify")
        self.api_version = "v21.0"

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Meta requiere verificación GET con hub.verify_token."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        if mode == "subscribe" and token == self.verify_token:
            # Meta espera el challenge como respuesta en texto plano
            return int(challenge)
        return None

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload anidado de Meta Cloud API."""
        body = await request.json()
        mensajes = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        mensajes.append(MensajeEntrante(
                            telefono=msg.get("from", ""),
                            texto=msg.get("text", {}).get("body", ""),
                            mensaje_id=msg.get("id", ""),
                            es_propio=False,  # Meta solo envía mensajes entrantes
                        ))
        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Meta WhatsApp Cloud API."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.error(f"Error Meta API: {r.status_code} — {r.text}")
            return r.status_code == 200

    async def enviar_documento(self, telefono: str, ruta: str, nombre_archivo: str, texto: str = "") -> bool:
        """Sube un PDF a Meta y lo envía como documento de WhatsApp."""
        if not self.access_token or not self.phone_number_id:
            logger.warning("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados")
            return False
        base = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            with open(ruta, "rb") as f:
                contenido = f.read()
            async with httpx.AsyncClient(timeout=60) as client:
                subida = await client.post(
                    f"{base}/media",
                    headers=headers,
                    data={"messaging_product": "whatsapp", "type": "application/pdf"},
                    files={"file": (nombre_archivo, contenido, "application/pdf")},
                )
                if subida.status_code != 200:
                    logger.error(f"Error subiendo documento a Meta: {subida.status_code} — {subida.text}")
                    return False
                documento = {"id": subida.json().get("id"), "filename": nombre_archivo}
                if texto:
                    documento["caption"] = texto
                r = await client.post(
                    f"{base}/messages",
                    headers=headers,
                    json={
                        "messaging_product": "whatsapp",
                        "to": telefono,
                        "type": "document",
                        "document": documento,
                    },
                )
                if r.status_code != 200:
                    logger.error(f"Error enviando documento por Meta: {r.status_code} — {r.text}")
                return r.status_code == 200
        except Exception as e:
            logger.error(f"No se pudo enviar el documento: {e}")
            return False
