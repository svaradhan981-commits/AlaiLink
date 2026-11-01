from datetime import datetime
from functools import lru_cache

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import Settings


class DatabaseConfigurationError(Exception):
    pass


class Base(DeclarativeBase):
    pass


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_key",
            "chunk_index",
            "embedding_provider",
            "embedding_model",
            "embedding_dimensions",
            name="uq_document_chunk_embedding",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(String(64), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    chunk_hash: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector())
    embedding_provider: Mapped[str] = mapped_column(String(50))
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dimensions: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    return create_async_engine(database_url, pool_pre_ping=True)


def get_session_factory(settings: Settings) -> async_sessionmaker:
    if not settings.database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured.")
    return async_sessionmaker(
        get_engine(settings.database_url.get_secret_value()),
        expire_on_commit=False,
    )


async def initialize_database(settings: Settings) -> None:
    if not settings.database_url:
        raise DatabaseConfigurationError("DATABASE_URL is not configured.")
    engine = get_engine(settings.database_url.get_secret_value())
    async with engine.begin() as connection:
        await connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        await connection.run_sync(Base.metadata.create_all)
