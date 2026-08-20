from datetime import date
from unittest.mock import MagicMock

import pytest

from agent import calendar_service


def _mock_servicio(items):
    servicio = MagicMock()
    servicio.events.return_value.list.return_value.execute.return_value = {"items": items}
    return servicio


def test_verificar_disponibilidad_sin_eventos_esta_disponible():
    servicio = _mock_servicio([])
    resultado = calendar_service.verificar_disponibilidad(
        "C6", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is True
    assert resultado["ocupados"] == 0
    assert resultado["capacidad"] == 1


def test_verificar_disponibilidad_c1_ocupada_pero_c2_libre():
    eventos = [{"summary": "C1 · Luis Nava · 4p", "description": ""}]
    servicio = _mock_servicio(eventos)
    resultado = calendar_service.verificar_disponibilidad(
        "C2", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is True
    assert resultado["ocupados"] == 1
    assert resultado["capacidad"] == 2


def test_verificar_disponibilidad_c1_y_c2_ocupadas():
    eventos = [
        {"summary": "C1 · Luis Nava · 4p", "description": ""},
        {"summary": "? C2 · Iván Ortiz · 4p", "description": ""},
    ]
    servicio = _mock_servicio(eventos)
    resultado = calendar_service.verificar_disponibilidad(
        "C1", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is False
    assert resultado["ocupados"] == 2
    assert resultado["capacidad"] == 2


def test_verificar_disponibilidad_evento_permite_hasta_tres():
    eventos = [
        {"summary": "EVENTO · Dan Solís · 30p", "description": ""},
        {"summary": "EVENTO · Ana Ruiz · 50p", "description": ""},
    ]
    servicio = _mock_servicio(eventos)
    resultado = calendar_service.verificar_disponibilidad(
        "EVENTO", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is True
    assert resultado["ocupados"] == 2
    assert resultado["capacidad"] == 3


def test_verificar_disponibilidad_campamento_nunca_se_llena():
    eventos = [{"summary": "CAMPA · Grupo Juvenil · 40p", "description": ""}]
    servicio = _mock_servicio(eventos)
    resultado = calendar_service.verificar_disponibilidad(
        "CAMPA", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is True


def test_verificar_disponibilidad_bloqueada_por_evento_exclusivo():
    eventos = [{"summary": "EVENTO EXCLUSIVO · Congreso ABC", "description": "Notas: EXCLUSIVO"}]
    servicio = _mock_servicio(eventos)
    resultado = calendar_service.verificar_disponibilidad(
        "C6", date(2026, 9, 12), date(2026, 9, 13),
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado["disponible"] is False
    assert resultado["razon"] == "evento_exclusivo"


def test_verificar_disponibilidad_prefijo_desconocido_lanza_value_error():
    servicio = _mock_servicio([])
    with pytest.raises(ValueError, match="Prefijo de recurso desconocido"):
        calendar_service.verificar_disponibilidad(
            "PREFIJO_INEXISTENTE", date(2026, 9, 12), date(2026, 9, 13),
            servicio=servicio, calendar_id="cal-test",
        )


def test_crear_reservacion_calendario_crea_evento_gris_con_signo_de_interrogacion():
    servicio = MagicMock()
    servicio.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt-123",
        "htmlLink": "https://calendar.google.com/evt-123",
    }
    resultado = calendar_service.crear_reservacion_calendario(
        "C6", date(2026, 9, 12), date(2026, 9, 13),
        nombre_completo="Juan Pérez", telefono="521234567890", personas=2,
        servicio=servicio, calendar_id="cal-test",
    )
    assert resultado == {"event_id": "evt-123", "link": "https://calendar.google.com/evt-123"}
    _, kwargs = servicio.events.return_value.insert.call_args
    body = kwargs["body"]
    assert body["summary"] == "? C6 · Juan Pérez · 2p"
    assert body["colorId"] == "8"
    assert body["start"] == {"date": "2026-09-12"}
    assert body["end"] == {"date": "2026-09-13"}
    assert "Juan Pérez" in body["description"]
    assert "521234567890" in body["description"]
