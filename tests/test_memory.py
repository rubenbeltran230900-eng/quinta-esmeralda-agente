async def test_crear_solicitud_reservacion_guarda_event_id(memory_module):
    memory = memory_module
    solicitud_id = await memory.crear_solicitud_reservacion(
        telefono="521234567890",
        tipo="C6",
        detalle="2 personas",
        fecha_solicitada="2026-09-12 a 2026-09-13",
        nombre_contacto="Juan Pérez",
        event_id="evento-abc-123",
    )

    solicitudes = await memory.listar_solicitudes_reservacion(telefono="521234567890")

    assert len(solicitudes) == 1
    assert solicitudes[0]["id"] == solicitud_id
    assert solicitudes[0]["event_id"] == "evento-abc-123"
    assert solicitudes[0]["estado"] == "pendiente"


async def test_marcar_evento_procesado_primera_vez_retorna_true(memory_module):
    resultado = await memory_module.marcar_evento_procesado("wamid.ABC123")
    assert resultado is True


async def test_marcar_evento_procesado_repetido_retorna_false(memory_module):
    primera = await memory_module.marcar_evento_procesado("wamid.ABC123")
    segunda = await memory_module.marcar_evento_procesado("wamid.ABC123")
    assert primera is True
    assert segunda is False


async def test_marcar_evento_procesado_sin_id_siempre_procesa(memory_module):
    primera = await memory_module.marcar_evento_procesado("")
    segunda = await memory_module.marcar_evento_procesado("")
    assert primera is True
    assert segunda is True
