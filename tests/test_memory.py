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
