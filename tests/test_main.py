# tests/test_main.py — Deduplicación, agrupamiento y no-cancelación en el webhook
# Generado por AgentKit

import asyncio
from unittest.mock import AsyncMock

import pytest

from agent import main as main_module
from agent.providers.base import MensajeEntrante


class ProveedorFalso:
    """Proveedor de WhatsApp de mentira: devuelve los mensajes que le digamos
    y guarda lo que el agente intente enviar de vuelta."""

    def __init__(self):
        self.mensajes_a_devolver: list[MensajeEntrante] = []
        self.enviados: list[tuple[str, str]] = []

    async def parsear_webhook(self, request):
        return self.mensajes_a_devolver

    async def enviar_mensaje(self, telefono, mensaje):
        self.enviados.append((telefono, mensaje))
        return True


@pytest.fixture(autouse=True)
def debounce_rapido(monkeypatch):
    # 6 segundos reales harian las pruebas lentisimas; se acorta.
    monkeypatch.setattr(main_module, "SEGUNDOS_DEBOUNCE", 0.05)


@pytest.fixture
def proveedor_falso(monkeypatch):
    fake = ProveedorFalso()
    monkeypatch.setattr(main_module, "proveedor", fake)
    return fake


@pytest.fixture(autouse=True)
def limpiar_estado_global():
    # El buffer, las tareas de espera y los candados son estado global del
    # modulo (uno por telefono) — se limpian antes y despues de cada prueba
    # para que una prueba no contamine la siguiente.
    main_module._buffer_mensajes.clear()
    main_module._tareas_debounce.clear()
    main_module._candados.clear()
    main_module._procesando.clear()
    yield
    main_module._buffer_mensajes.clear()
    main_module._tareas_debounce.clear()
    main_module._candados.clear()
    main_module._procesando.clear()


async def test_mensaje_repetido_por_id_se_ignora(proveedor_falso, monkeypatch):
    vistos = set()

    async def falso_marcar(mensaje_id):
        if mensaje_id in vistos:
            return False
        vistos.add(mensaje_id)
        return True

    monkeypatch.setattr(main_module, "marcar_evento_procesado", falso_marcar)

    msg = MensajeEntrante(telefono="521234567890", texto="Hola", mensaje_id="wamid.1", es_propio=False)
    proveedor_falso.mensajes_a_devolver = [msg]

    resultado = await main_module.webhook_handler(request=None)
    assert resultado == {"status": "ok"}
    assert main_module._buffer_mensajes["521234567890"] == ["Hola"]

    # La misma entrega otra vez (reintento de Meta) — no debe duplicarse en el buffer
    await main_module.webhook_handler(request=None)
    assert main_module._buffer_mensajes["521234567890"] == ["Hola"]


async def test_mensajes_seguidos_se_agrupan_en_un_solo_turno(proveedor_falso, monkeypatch):
    monkeypatch.setattr(main_module, "marcar_evento_procesado", AsyncMock(return_value=True))
    monkeypatch.setattr(main_module, "obtener_historial", AsyncMock(return_value=[]))
    monkeypatch.setattr(main_module, "guardar_mensaje", AsyncMock())

    textos_recibidos = []

    async def falsa_generar_respuesta(mensaje, historial):
        textos_recibidos.append(mensaje)
        return "respuesta unica"

    monkeypatch.setattr(main_module, "generar_respuesta", falsa_generar_respuesta)

    telefono = "521234567890"

    proveedor_falso.mensajes_a_devolver = [
        MensajeEntrante(telefono=telefono, texto="Ruben Beltran", mensaje_id="wamid.1", es_propio=False)
    ]
    await main_module.webhook_handler(request=None)

    await asyncio.sleep(0.02)  # menos que el debounce (0.05): no debe procesar todavia

    proveedor_falso.mensajes_a_devolver = [
        MensajeEntrante(telefono=telefono, texto="2721393338", mensaje_id="wamid.2", es_propio=False)
    ]
    await main_module.webhook_handler(request=None)

    # el segundo mensaje reinicio el reloj: hay que esperar el debounce completo desde el
    await asyncio.sleep(0.12)

    assert textos_recibidos == ["Ruben Beltran\n2721393338"]
    assert proveedor_falso.enviados == [(telefono, "respuesta unica")]


async def test_mensaje_que_llega_mientras_se_procesa_no_cancela_la_reservacion_en_curso(
    proveedor_falso, monkeypatch
):
    """
    Reproduce el escenario real que causo la reservacion doble: un mensaje
    nuevo llega justo cuando el lote anterior ya esta a la mitad de
    _procesar_mensaje (por ejemplo, esperando la respuesta de Claude o del
    calendario). Ese procesamiento en curso NUNCA debe cancelarse.
    """
    monkeypatch.setattr(main_module, "marcar_evento_procesado", AsyncMock(return_value=True))
    monkeypatch.setattr(main_module, "obtener_historial", AsyncMock(return_value=[]))
    monkeypatch.setattr(main_module, "guardar_mensaje", AsyncMock())

    empezo_a_procesar = asyncio.Event()
    dejar_continuar = asyncio.Event()
    llamadas = []

    async def falsa_generar_respuesta(mensaje, historial):
        llamadas.append(mensaje)
        empezo_a_procesar.set()
        await dejar_continuar.wait()  # simula que Claude/el calendario tardan
        return "reservacion confirmada"

    monkeypatch.setattr(main_module, "generar_respuesta", falsa_generar_respuesta)

    telefono = "521234567890"
    proveedor_falso.mensajes_a_devolver = [
        MensajeEntrante(telefono=telefono, texto="primer mensaje", mensaje_id="wamid.1", es_propio=False)
    ]
    await main_module.webhook_handler(request=None)

    # dejar pasar el debounce para que entre a _procesar_mensaje y quede
    # "colgado" dentro de falsa_generar_respuesta hasta que se le permita seguir
    await asyncio.wait_for(empezo_a_procesar.wait(), timeout=1)
    assert telefono in main_module._procesando

    # ahora, mientras sigue procesando, llega un mensaje nuevo del mismo telefono
    proveedor_falso.mensajes_a_devolver = [
        MensajeEntrante(telefono=telefono, texto="segundo mensaje", mensaje_id="wamid.2", es_propio=False)
    ]
    await main_module.webhook_handler(request=None)

    # dejar que el primer procesamiento termine
    dejar_continuar.set()
    await asyncio.sleep(0.02)

    # el primer procesamiento SI debio completarse (no se cancelo a medias)
    assert llamadas == ["primer mensaje"]
    assert (telefono, "reservacion confirmada") in proveedor_falso.enviados

    # el segundo mensaje quedo agendado para su propia ronda, no se perdio
    await asyncio.sleep(0.12)
    assert "segundo mensaje" in llamadas
