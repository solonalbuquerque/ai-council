"""Conexão com o PostgreSQL (SQLAlchemy 2.0 async + asyncpg)."""
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/aicouncil",
)

engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(retries: int = 30, delay: float = 2.0):
    """Cria as tabelas. Tenta várias vezes porque o Postgres do Docker pode
    demorar a aceitar conexões na primeira subida."""
    import app.models  # noqa: F401  (registra os modelos no metadata)

    last = None
    for _ in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:  # ainda subindo
            last = e
            await asyncio.sleep(delay)
    raise RuntimeError(f"Não consegui conectar ao banco: {last}")
