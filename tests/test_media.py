import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("WHATSAPP_PROVIDER", "meta")

from agent import notificaciones  # noqa: E402
from agent.providers.base import MensajeEntrante  # noqa: E402
from agent.providers.meta import ProveedorMeta  # noqa: E402


class SolicitudFalsa:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    async def json(self):
        return self._cuerpo


def _payload(mensaje):
    return {"entry": [{"changes": [{"value": {"messages": [mensaje]}}]}]}


async def test_meta_parsea_una_imagen_con_su_texto():
    mensajes = await ProveedorMeta().parsear_webhook(SolicitudFalsa(_payload({
        "from": "5212721234567", "id": "wamid.1", "type": "image",
        "image": {"id": "media-9", "mime_type": "image/jpeg", "caption": "mi comprobante"},
    })))

    assert len(mensajes) == 1
    assert mensajes[0].tipo == "image"
    assert mensajes[0].media_id == "media-9"
    assert mensajes[0].texto == "mi comprobante"


async def test_meta_sigue_parseando_texto_igual():
    mensajes = await ProveedorMeta().parsear_webhook(SolicitudFalsa(_payload({
        "from": "5212721234567", "id": "wamid.2", "type": "text", "text": {"body": "hola"},
    })))

    assert mensajes[0].tipo == "text"
    assert mensajes[0].texto == "hola"


def test_correo_de_archivo_adjunta_el_contenido(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_falsa_123")
    monkeypatch.setenv("RESEND_FROM", "Quinta Esmeralda <onboarding@resend.dev>")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")
    cliente = MagicMock()
    cliente.post.return_value = MagicMock(status_code=200, text="")

    ok = notificaciones.enviar_correo_archivo_cliente(
        "5212721234567", "mi comprobante", b"abc", "archivo.jpg", cliente_http=cliente,
    )

    assert ok is True
    cuerpo = cliente.post.call_args.kwargs["json"]
    assert cuerpo["attachments"] == [{"filename": "archivo.jpg", "content": "YWJj"}]
    assert "5212721234567" in cuerpo["subject"]
    assert "mi comprobante" in cuerpo["text"]


class ProveedorFalso:
    def __init__(self):
        self.enviados = []

    async def descargar_media(self, media_id):
        return b"abc", "image/jpeg"

    async def enviar_mensaje(self, telefono, mensaje):
        self.enviados.append(mensaje)
        return True


@pytest.fixture
async def main_module(memory_module, monkeypatch):
    from agent import main
    falso = ProveedorFalso()
    correos = []
    monkeypatch.setattr(main, "proveedor", falso)
    monkeypatch.setattr(
        main.notificaciones, "enviar_correo_archivo_cliente",
        lambda telefono, texto, contenido, nombre: correos.append((telefono, contenido, nombre)) or True,
    )
    main._ultimo_acuse.clear()
    return main, falso, correos


def _imagen(mensaje_id="wamid.1"):
    return MensajeEntrante(telefono="521111", texto="", mensaje_id=mensaje_id, es_propio=False,
                           tipo="image", media_id="media-9")


async def test_imagen_avisa_por_correo_y_confirma_al_cliente(main_module, memory_module):
    main, proveedor, correos = main_module

    await main._procesar_no_texto(_imagen())

    assert correos == [("521111", b"abc", "archivo-521111.jpg")]
    assert proveedor.enviados == [main.MENSAJE_ARCHIVO_RECIBIDO]
    historial = await memory_module.obtener_historial("521111")
    assert historial[0] == {"role": "user", "content": "[El cliente envió una imagen]"}


async def test_imagen_se_reenvia_aunque_el_asistente_este_en_pausa(main_module, memory_module):
    main, proveedor, correos = main_module
    await memory_module.pausar_conversacion("521111")

    await main._procesar_no_texto(_imagen())

    assert len(correos) == 1
    assert proveedor.enviados == [main.MENSAJE_ARCHIVO_RECIBIDO]
    assert await memory_module.esta_pausada("521111") is True


async def test_varias_imagenes_seguidas_un_correo_cada_una_y_un_solo_acuse(main_module):
    main, proveedor, correos = main_module

    await main._procesar_no_texto(_imagen("wamid.1"))
    await main._procesar_no_texto(_imagen("wamid.2"))

    assert len(correos) == 2
    assert len(proveedor.enviados) == 1


async def test_audio_pide_escribir_y_no_manda_correo(main_module):
    main, proveedor, correos = main_module
    audio = MensajeEntrante(telefono="521111", texto="", mensaje_id="wamid.3", es_propio=False, tipo="audio")

    await main._procesar_no_texto(audio)

    assert correos == []
    assert proveedor.enviados == [main.MENSAJE_SOLO_TEXTO]


async def test_audio_con_asistente_en_pausa_no_contesta(main_module, memory_module):
    main, proveedor, correos = main_module
    await memory_module.pausar_conversacion("521111")
    audio = MensajeEntrante(telefono="521111", texto="", mensaje_id="wamid.4", es_propio=False, tipo="audio")

    await main._procesar_no_texto(audio)

    assert proveedor.enviados == []
