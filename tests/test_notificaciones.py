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


def test_enviar_correo_sin_configuracion_retorna_false(monkeypatch):
    monkeypatch.delenv("NOTIFICACION_EMAIL_ORIGEN", raising=False)
    monkeypatch.delenv("NOTIFICACION_EMAIL_PASSWORD", raising=False)
    monkeypatch.delenv("NOTIFICACION_EMAIL_DESTINO", raising=False)

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO)

    assert resultado is False


def test_enviar_correo_llama_login_y_sendmail(monkeypatch):
    monkeypatch.setenv("NOTIFICACION_EMAIL_ORIGEN", "negocio@gmail.com")
    monkeypatch.setenv("NOTIFICACION_EMAIL_PASSWORD", "app-password-falsa")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")

    servidor_falso = MagicMock()
    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, servidor_smtp=servidor_falso)

    assert resultado is True
    servidor_falso.login.assert_called_once_with("negocio@gmail.com", "app-password-falsa")
    assert servidor_falso.sendmail.call_count == 1
    remitente, destinatarios, cuerpo = servidor_falso.sendmail.call_args[0]
    assert remitente == "negocio@gmail.com"
    assert destinatarios == ["negocio@gmail.com"]
    assert "Juan Pérez" in cuerpo


def test_enviar_correo_con_error_smtp_retorna_false(monkeypatch):
    monkeypatch.setenv("NOTIFICACION_EMAIL_ORIGEN", "negocio@gmail.com")
    monkeypatch.setenv("NOTIFICACION_EMAIL_PASSWORD", "app-password-falsa")
    monkeypatch.setenv("NOTIFICACION_EMAIL_DESTINO", "negocio@gmail.com")

    servidor_falso = MagicMock()
    servidor_falso.login.side_effect = Exception("credenciales inválidas")

    resultado = notificaciones.enviar_correo_nueva_reservacion(DATOS_EJEMPLO, servidor_smtp=servidor_falso)

    assert resultado is False
