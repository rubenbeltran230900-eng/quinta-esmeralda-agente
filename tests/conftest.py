# tests/conftest.py — Fixtures compartidos para pruebas del agente
# Generado por AgentKit

"""
Fixture compartido que aisla cada test contra una base de datos SQLite
temporal, en vez de la base de datos real del proyecto (agentkit.db).
Recarga agent.memory para que tome la nueva DATABASE_URL, y cierra el
engine al terminar para no dejar conexiones colgadas.
"""

import importlib

import pytest


@pytest.fixture
async def memory_module(tmp_path, monkeypatch):
    db_path = tmp_path / "test_memory.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    import agent.memory as memory
    importlib.reload(memory)
    await memory.inicializar_db()
    yield memory
    await memory.engine.dispose()


@pytest.fixture
async def tools_module(memory_module):
    import agent.tools as tools
    importlib.reload(tools)
    return tools
