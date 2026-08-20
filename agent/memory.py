# agent/memory.py — Memoria de conversaciones con SQLite
# Generado por AgentKit

"""
Sistema de memoria del agente. Guarda el historial de conversaciones
por número de teléfono usando SQLite (local) o PostgreSQL (producción).
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, DateTime, select, Integer
from dotenv import load_dotenv

load_dotenv()

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./agentkit.db")

# Si es PostgreSQL en producción, ajustar el esquema de URL
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Mensaje(Base):
    """Modelo de mensaje en la base de datos."""
    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" o "assistant"
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SolicitudReservacion(Base):
    """Modelo de una solicitud de reservación registrada por el agente."""
    __tablename__ = "solicitudes_reservacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    tipo: Mapped[str] = mapped_column(String(50))          # cabana, evento, campamento, sesion_fotos, experiencia
    detalle: Mapped[str] = mapped_column(Text)              # descripción libre (qué opción, cuántas personas, etc.)
    fecha_solicitada: Mapped[str] = mapped_column(String(50))  # fecha que pidió el cliente (texto libre)
    nombre_contacto: Mapped[str] = mapped_column(String(150), default="")
    event_id: Mapped[str] = mapped_column(String(200), default="")
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente, confirmada, cancelada
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db():
    """Crea las tablas si no existen."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def guardar_mensaje(telefono: str, role: str, content: str):
    """Guarda un mensaje en el historial de conversación."""
    async with async_session() as session:
        mensaje = Mensaje(
            telefono=telefono,
            role=role,
            content=content,
            timestamp=datetime.utcnow()
        )
        session.add(mensaje)
        await session.commit()


async def obtener_historial(telefono: str, limite: int = 20) -> list[dict]:
    """
    Recupera los últimos N mensajes de una conversación.

    Args:
        telefono: Número de teléfono del cliente
        limite: Máximo de mensajes a recuperar (default: 20)

    Returns:
        Lista de diccionarios con role y content
    """
    async with async_session() as session:
        query = (
            select(Mensaje)
            .where(Mensaje.telefono == telefono)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
        )
        result = await session.execute(query)
        mensajes = result.scalars().all()

        # Invertir para orden cronológico (los más recientes están primero)
        mensajes.reverse()

        return [
            {"role": msg.role, "content": msg.content}
            for msg in mensajes
        ]


async def limpiar_historial(telefono: str):
    """Borra todo el historial de una conversación."""
    async with async_session() as session:
        query = select(Mensaje).where(Mensaje.telefono == telefono)
        result = await session.execute(query)
        mensajes = result.scalars().all()
        for msg in mensajes:
            session.delete(msg)
        await session.commit()


async def crear_solicitud_reservacion(
    telefono: str,
    tipo: str,
    detalle: str,
    fecha_solicitada: str,
    nombre_contacto: str = "",
    event_id: str = "",
) -> int:
    """Guarda una solicitud de reservación pendiente de confirmación humana."""
    async with async_session() as session:
        solicitud = SolicitudReservacion(
            telefono=telefono,
            tipo=tipo,
            detalle=detalle,
            fecha_solicitada=fecha_solicitada,
            nombre_contacto=nombre_contacto,
            event_id=event_id,
            estado="pendiente",
            timestamp=datetime.utcnow(),
        )
        session.add(solicitud)
        await session.commit()
        await session.refresh(solicitud)
        return solicitud.id


async def listar_solicitudes_reservacion(telefono: str | None = None) -> list[dict]:
    """Lista solicitudes de reservación, opcionalmente filtradas por teléfono."""
    async with async_session() as session:
        query = select(SolicitudReservacion).order_by(SolicitudReservacion.timestamp.desc())
        if telefono:
            query = query.where(SolicitudReservacion.telefono == telefono)
        result = await session.execute(query)
        solicitudes = result.scalars().all()
        return [
            {
                "id": s.id,
                "telefono": s.telefono,
                "tipo": s.tipo,
                "detalle": s.detalle,
                "fecha_solicitada": s.fecha_solicitada,
                "nombre_contacto": s.nombre_contacto,
                "event_id": s.event_id,
                "estado": s.estado,
                "timestamp": s.timestamp.isoformat(),
            }
            for s in solicitudes
        ]
