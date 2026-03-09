"""Job queue service — Redis-backed ingestion queue.

Uses a simple Redis list. Producers call enqueue(); the worker calls dequeue().
Queue key: rag:ingest:queue
"""

from typing import Any

import redis

from app.config import settings

QUEUE_KEY = "rag:ingest:queue"


def _client() -> Any:
    return redis.from_url(settings.redis_url, decode_responses=True)


def enqueue(document_id: str) -> None:
    """Push a document_id onto the ingestion queue."""
    _client().lpush(QUEUE_KEY, document_id)


def dequeue(timeout: int = 5) -> str | None:
    """Block for up to `timeout` seconds. Returns document_id or None on timeout."""
    # redis-py stubs are incomplete; sync brpop returns list[tuple] | None
    raw: tuple[str, str] | None = _client().brpop(QUEUE_KEY, timeout=timeout)
    if raw is None:
        return None
    return raw[1]
