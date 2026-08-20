import importlib
from datetime import date

import pytest


@pytest.fixture
async def tools_module(memory_module):
    import agent.tools as tools
    importlib.reload(tools)
    return tools


async def test_verificar_disponibilidad_delega_a_calendar_service(tools_module, monkeypatch):
    tools = tools_module
    llamada = {}

    def falso_verificar(prefijo, entrada, salida, **kwargs):
        llamada["prefijo"] = prefijo
        llamada["entrada"] = entrada
        llamada["salida"] = salida
        return {"disponible": True, "ocupados": 0, "capacidad": 1}

    monkeypatch.setattr(tools.calendar_service, "verificar_disponibilidad", falso_verificar)

    resultado = await tools.verificar_disponibilidad("C6", "2026-09-12", "2026-09-13")

    assert resultado == {"disponible": True, "ocupados": 0, "capacidad": 1}
    assert llamada["prefijo"] == "C6"
    assert llamada["entrada"] == date(2026, 9, 12)
    assert llamada["salida"] == date(2026, 9, 13)


async def test_crear_reservacion_guarda_en_memoria_y_notifica(tools_module, monkeypatch):
    tools = tools_module

    monkeypatch.setattr(
        tools.calendar_service, "crear_reservacion_calendario",
        lambda *a, **k: {"event_id": "evt-1", "link": "https://calendar.google.com/evt-1"},
    )
    correos_enviados = []
    monkeypatch.setattr(
        tools.notificaciones, "enviar_correo_nueva_reservacion",
        lambda datos, **k: correos_enviados.append(datos) or True,
    )

    resultado = await tools.crear_reservacion(
        "C6", "2026-09-12", "2026-09-13", "Juan Pérez", "521234567890", 2,
    )

    assert resultado["event_id"] == "evt-1"
    assert "apartada" in resultado["mensaje"].lower()
    assert len(correos_enviados) == 1
    assert correos_enviados[0]["nombre_completo"] == "Juan Pérez"

    solicitudes = await tools.listar_solicitudes_reservacion(telefono="521234567890")
    assert len(solicitudes) == 1
    assert solicitudes[0]["event_id"] == "evt-1"


async def test_crear_reservacion_no_falla_si_el_correo_falla(tools_module, monkeypatch):
    tools = tools_module

    monkeypatch.setattr(
        tools.calendar_service, "crear_reservacion_calendario",
        lambda *a, **k: {"event_id": "evt-2", "link": "https://calendar.google.com/evt-2"},
    )
    monkeypatch.setattr(tools.notificaciones, "enviar_correo_nueva_reservacion", lambda datos, **k: False)

    resultado = await tools.crear_reservacion(
        "C7", "2026-10-01", "2026-10-02", "Ana Ruiz", "521111111111", 8,
    )

    assert resultado["event_id"] == "evt-2"


async def test_crear_reservacion_no_falla_si_sqlite_falla(tools_module, monkeypatch):
    tools = tools_module

    monkeypatch.setattr(
        tools.calendar_service, "crear_reservacion_calendario",
        lambda *a, **k: {"event_id": "evt-3", "link": "https://calendar.google.com/evt-3"},
    )
    monkeypatch.setattr(tools.notificaciones, "enviar_correo_nueva_reservacion", lambda datos, **k: True)

    def falla_sqlite(*a, **k):
        raise RuntimeError("db caída")

    monkeypatch.setattr(tools, "crear_solicitud_reservacion", falla_sqlite)

    resultado = await tools.crear_reservacion(
        "C6", "2026-11-01", "2026-11-02", "Luis Gómez", "521222222222", 3,
    )

    assert resultado["event_id"] == "evt-3"
