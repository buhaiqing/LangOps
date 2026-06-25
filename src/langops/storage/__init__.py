"""LangOps storage layer — pluggable persistence with SQLAlchemy."""

import asyncio

from langops.storage.base import (
    AlertRepository,
    AnalysisRepository,
    DedupRepository,
    RemediationRepository,
    Storage,
)
from langops.storage.sql import SqlStorage

__all__ = [
    "Storage",
    "AlertRepository",
    "AnalysisRepository",
    "DedupRepository",
    "RemediationRepository",
    "SqlStorage",
    "get_storage",
]

_storage_instance: Storage | None = None
_storage_lock = asyncio.Lock()


async def get_storage() -> Storage:
    """Return the global storage instance (lazy-initialized).

    Uses asyncio.Lock (not threading.Lock) because FastAPI runs on a single
    event loop thread. A threading.Lock would block the event loop during await.
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance
    async with _storage_lock:
        if _storage_instance is None:
            from langops.core.config import settings

            instance = SqlStorage(
                url=settings.storage.url,
                echo=settings.storage.echo,
            )
            await instance.initialize()
            _storage_instance = instance
    return _storage_instance


async def close_storage() -> None:
    """Shut down the global storage instance."""
    global _storage_instance
    async with _storage_lock:
        if _storage_instance is not None:
            await _storage_instance.close()
            _storage_instance = None
