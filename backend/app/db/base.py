"""
Project : AEGIS
Company : Honeydewnuts Nigerian Limited
File    : app/db/base.py

Async SQLAlchemy engine + session factory, backing CredentialVaultService
and SubscriptionService. Replaces the earlier SQLite-file-per-service
approach - that worked for a single instance but doesn't hold up once
you run more than one API process/replica (each would see a different
file). Postgres was already provisioned in docker-compose from the start
and simply wasn't wired up until now.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


def _to_async_url(url: str) -> str:
    """Accepts a plain postgresql:// URL (as used by non-async tools like
    Alembic's default template) and normalizes it to the asyncpg driver
    URL SQLAlchemy's async engine needs, so .env only needs one URL."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Base(DeclarativeBase):
    pass


engine = create_async_engine(_to_async_url(settings.DATABASE_URL), pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncSession:
    """FastAPI dependency - not used by the services (which manage their
    own sessions internally, see below), but handy for any router that
    wants direct DB access later."""
    async with async_session_factory() as session:
        yield session
