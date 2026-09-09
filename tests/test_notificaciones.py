from unittest.mock import MagicMock

from agent import notificaciones

DATOS_EJEMPLO = {
    "prefijo": "C6",
    "nombre_completo": "Juan Pérez",
    "telefono": "521234567890",
    "personas": 2,
    "fecha_entrada": "2026-09-12",
    "fecha_salida": "2026-09-13",
    "link": "https://calendar.google.com/evt-123",
}


def _respuesta_falsa(status_code, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    return r


def test_enviar_correo_sin_configuracion_retorna_false(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)
    monkeypatch.delenv("NOTIFICACION_EMAIL_DESTINO", raising=False)

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO)

    assert resultado is False


def test_enviar_correo_llama_a_resend_correctamente(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_falsa_123")
    monkeypatch.setenv("RESEND_FROM", "Quinta Esmeralda <onboarding@resend.dev>")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")

    cliente_falso = MagicMock()
    cliente_falso.post.return_value = _respuesta_falsa(200)

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, cliente_http=cliente_falso)

    assert resultado is True
    cliente_falso.post.assert_called_once()
    _, kwargs = cliente_falso.post.call_args
    assert kwargs["json"]["to"] == ["negocio@gmail.com"]
    assert kwargs["json"]["from"] == "Quinta Esmeralda <onboarding@resend.dev>"
    assert kwargs["headers"]["Authorization"] == "Bearer re_falsa_123"
    assert "Juan Pérez" in kwargs["json"]["text"]


def test_enviar_correo_a_varios_destinatarios(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_falsa_123")
    monkeypatch.setenv("RESEND_FROM", "Quinta Esmeralda <onboarding@resend.dev>")
    monkeypatch.setenv(
        "NOTIFICACION_EMAIL_DESTINO", "rbelmor@hotmail.com, reservaciones.qe@gmail.com"
    )

    cliente_falso = MagicMock()
    cliente_falso.post.return_value = _respuesta_falsa(200)

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, cliente_http=cliente_falso)

    assert resultado is True
    _, kwargs = cliente_falso.post.call_args
    assert kwargs["json"]["to"] == ["rbelmor@hotmail.com", "reservaciones.qe@gmail.com"]


def test_enviar_correo_con_error_de_resend_retorna_false(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_falsa_123")
    monkeypatch.setenv("RESEND_FROM", "Quinta Esmeralda <onboarding@resend.dev>")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")

    cliente_falso = MagicMock()
    cliente_falso.post.return_value = _respuesta_falsa(401, "invalid api key")

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, cliente_http=cliente_falso)

    assert resultado is False


def test_enviar_correo_con_excepcion_de_red_retorna_false(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_falsa_123")
    monkeypatch.setenv("RESEND_FROM", "Quinta Esmeralda <onboarding@resend.dev>")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")

    cliente_falso = MagicMock()
    cliente_falso.post.side_effect = Exception("network error")

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, cliente_http=cliente_falso)

    assert resultado is False
