"""PostgreSQL connection (SQLAlchemy 2.0 async + asyncpg)."""
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
    """Create tables. Retries because Docker Postgres may take a moment to accept connections on first boot."""
    import app.models  # noqa: F401  (register models on metadata)

    last = None
    for _ in range(retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:  # still starting up
            last = e
            await asyncio.sleep(delay)
    raise RuntimeError(f"Could not connect to database: {last}")
