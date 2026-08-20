import types
from unittest.mock import AsyncMock

from agent import brain


def _bloque_texto(texto):
    return types.SimpleNamespace(type="text", text=texto)


def _bloque_tool_use(nombre, entrada, id_="tool-1"):
    return types.SimpleNamespace(type="tool_use", name=nombre, input=entrada, id=id_)


def _respuesta(content, stop_reason, in_tokens=10, out_tokens=10):
    return types.SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=types.SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
    )


async def test_generar_respuesta_ejecuta_herramienta_y_devuelve_texto_final(monkeypatch):
    monkeypatch.setattr(brain, "cargar_system_prompt", lambda: "Eres un asistente de prueba.")

    llamada_verificar = {}

    async def falsa_verificar(prefijo, fecha_entrada, fecha_salida):
        llamada_verificar["prefijo"] = prefijo
        return {"disponible": True, "ocupados": 0, "capacidad": 1}

    monkeypatch.setitem(brain.DISPATCH_HERRAMIENTAS, "verificar_disponibilidad", falsa_verificar)

    respuestas = [
        _respuesta(
            [_bloque_tool_use("verificar_disponibilidad", {
                "prefijo": "C6", "fecha_entrada": "2026-09-12", "fecha_salida": "2026-09-13",
            })],
            stop_reason="tool_use",
        ),
        _respuesta([_bloque_texto("Sí hay disponibilidad para C6 esas fechas.")], stop_reason="end_turn"),
    ]

    mock_create = AsyncMock(side_effect=respuestas)
    monkeypatch.setattr(brain.client.messages, "create", mock_create)

    resultado = await brain.generar_respuesta("¿Hay cabaña para 2 el 12 de septiembre?", [])

    assert resultado == "Sí hay disponibilidad para C6 esas fechas."
    assert llamada_verificar["prefijo"] == "C6"
    assert mock_create.call_count == 2


async def test_generar_respuesta_ejecuta_crear_reservacion_real_hasta_sqlite(monkeypatch, tools_module):
    monkeypatch.setattr(brain, "cargar_system_prompt", lambda: "Eres un asistente de prueba.")

    monkeypatch.setattr(
        tools_module.calendar_service, "crear_reservacion_calendario",
        lambda *a, **k: {"event_id": "evt-integracion", "link": "https://calendar.google.com/evt-integracion"},
    )
    monkeypatch.setattr(
        tools_module.notificaciones, "enviar_correo_nueva_reservacion",
        lambda datos, **k: True,
    )

    # brain.DISPATCH_HERRAMIENTAS se construye UNA sola vez, cuando agent.brain
    # se importa por primera vez (al inicio de la sesión de pruebas), apuntando
    # al objeto función original de agent.tools.crear_reservacion en ese
    # momento. El fixture tools_module hace importlib.reload(tools) en cada
    # prueba, lo cual SÍ actualiza en el mismo diccionario del módulo (mismo
    # objeto de módulo, reutilizado por reload) los nombres calendar_service /
    # notificaciones / crear_solicitud_reservacion — por lo que, en teoría, la
    # función vieja seguiría resolviendo esos globals correctamente. Pero
    # depender de ese detalle de implementación de importlib.reload es frágil
    # y no está garantizado por el fixture. Para no depender de esa sutileza,
    # apuntamos explícitamente la tabla de despacho de brain al objeto función
    # reconstruido por el reload de este test.
    monkeypatch.setitem(brain.DISPATCH_HERRAMIENTAS, "crear_reservacion", tools_module.crear_reservacion)

    respuestas = [
        _respuesta(
            [_bloque_tool_use("crear_reservacion", {
                "prefijo": "C6", "fecha_entrada": "2026-09-12", "fecha_salida": "2026-09-13",
                "nombre_completo": "Prueba Integracion", "telefono": "521234567890", "personas": 2,
            })],
            stop_reason="tool_use",
        ),
        _respuesta([_bloque_texto("Su reservacion quedo apartada.")], stop_reason="end_turn"),
    ]
    mock_create = AsyncMock(side_effect=respuestas)
    monkeypatch.setattr(brain.client.messages, "create", mock_create)

    resultado = await brain.generar_respuesta("Quiero reservar la cabana", [])

    assert resultado == "Su reservacion quedo apartada."

    solicitudes = await tools_module.listar_solicitudes_reservacion(telefono="521234567890")
    assert len(solicitudes) == 1
    assert solicitudes[0]["event_id"] == "evt-integracion"


async def test_generar_respuesta_sin_herramientas_devuelve_texto_directo(monkeypatch):
    monkeypatch.setattr(brain, "cargar_system_prompt", lambda: "Eres un asistente de prueba.")

    respuestas = [_respuesta([_bloque_texto("Hola, bienvenido.")], stop_reason="end_turn")]
    mock_create = AsyncMock(side_effect=respuestas)
    monkeypatch.setattr(brain.client.messages, "create", mock_create)

    resultado = await brain.generar_respuesta("Hola", [])

    assert resultado == "Hola, bienvenido."
    assert mock_create.call_count == 1
