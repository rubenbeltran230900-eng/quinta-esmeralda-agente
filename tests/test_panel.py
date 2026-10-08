import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
async def cliente(memory_module, monkeypatch):
    monkeypatch.setenv("PANEL_USUARIO", "quinta")
    monkeypatch.setenv("PANEL_PASSWORD", "clave-de-prueba")
    from agent import panel

    await memory_module.guardar_mensaje("5212721234567", "user", "Hola <b>quiero</b> una cabaña")
    await memory_module.guardar_mensaje("5212721234567", "assistant", "Con gusto, ¿para qué fecha?")
    await memory_module.guardar_mensaje("5219990001111", "user", "Precios por favor")
    await memory_module.pausar_conversacion("5219990001111")

    app = FastAPI()
    app.include_router(panel.router)
    return TestClient(app)


AUTH = ("quinta", "clave-de-prueba")


async def test_panel_sin_credenciales_pide_login(cliente):
    r = cliente.get("/panel")

    assert r.status_code == 401
    assert "Basic" in r.headers["WWW-Authenticate"]


async def test_panel_con_password_incorrecta_rechaza(cliente):
    assert cliente.get("/panel", auth=("quinta", "otra")).status_code == 401
    assert cliente.get("/panel/5212721234567", auth=("quinta", "otra")).status_code == 401


async def test_panel_sin_password_configurada_queda_apagado(cliente, monkeypatch):
    monkeypatch.delenv("PANEL_PASSWORD")

    assert cliente.get("/panel", auth=("quinta", "")).status_code == 503


async def test_panel_lista_las_conversaciones_y_marca_las_pausadas(cliente):
    r = cliente.get("/panel", auth=AUTH)

    assert r.status_code == 200
    assert "+5212721234567" in r.text
    assert "+5219990001111" in r.text
    assert r.text.count("asistente en pausa") == 1
    # la mas reciente va primero
    assert r.text.index("5219990001111") < r.text.index("5212721234567")


async def test_panel_muestra_la_conversacion_escapando_html(cliente):
    r = cliente.get("/panel/5212721234567", auth=AUTH)

    assert r.status_code == 200
    assert "Con gusto, ¿para qué fecha?" in r.text
    assert "&lt;b&gt;quiero&lt;/b&gt;" in r.text
    assert "<b>quiero</b>" not in r.text


async def test_panel_conversacion_inexistente_da_404(cliente):
    assert cliente.get("/panel/000", auth=AUTH).status_code == 404
