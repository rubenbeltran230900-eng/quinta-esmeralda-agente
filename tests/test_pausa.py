from agent import pausa


async def test_sin_pausa_atiende(memory_module):
    assert await pausa.evaluar("521111", "hola") == "atender"


async def test_en_pausa_avisa_una_sola_vez_y_luego_ignora(memory_module):
    await memory_module.pausar_conversacion("521111")

    assert await pausa.evaluar("521111", "hola?") == "recordar"
    assert await pausa.evaluar("521111", "hay alguien?") == "ignorar"
    assert await pausa.evaluar("521111", "buenas tardes") == "ignorar"


async def test_palabra_clave_reactiva(memory_module):
    await memory_module.pausar_conversacion("521111")

    assert await pausa.evaluar("521111", "ASISTENTE") == "atender"
    assert await memory_module.esta_pausada("521111") is False
    assert await pausa.evaluar("521111", "quiero una cabaña") == "atender"


async def test_palabra_clave_ignora_mayusculas_y_acentos(memory_module):
    await memory_module.pausar_conversacion("521111")

    assert await pausa.evaluar("521111", "Hola, Asisténte por favor") == "atender"


async def test_palabra_dentro_de_otra_no_reactiva(memory_module):
    await memory_module.pausar_conversacion("521111")

    assert await pausa.evaluar("521111", "asistentes") == "recordar"


async def test_pausa_es_por_telefono(memory_module):
    await memory_module.pausar_conversacion("521111")

    assert await pausa.evaluar("522222", "hola") == "atender"


async def test_herramienta_pausar_conversacion_pausa_al_cliente_actual(tools_module, memory_module):
    tools_module.telefono_actual.set("521111")

    resultado = await tools_module.pausar_conversacion("despedida")

    assert resultado == {"pausada": True}
    assert await memory_module.esta_pausada("521111") is True
