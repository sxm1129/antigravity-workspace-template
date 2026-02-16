"""Redis Pub/Sub bridge for cross-process WebSocket notifications.

Celery workers publish messages to a Redis channel.
FastAPI's WebSocket handler subscribes and relays to connected clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "motionweaver:ws:"

# ──────── Sync connection pool (used by Celery workers) ────────

_sync_pool: redis.ConnectionPool | None = None


def _get_sync_pool() -> redis.ConnectionPool:
    """Lazy-init a module-level sync Redis ConnectionPool."""
    global _sync_pool
    if _sync_pool is None:
        settings = get_settings()
        _sync_pool = redis.ConnectionPool.from_url(settings.REDIS_URL)
    return _sync_pool


# ──────── Publisher (used by Celery workers — sync) ────────

def publish_scene_update(project_id: str, scene_id: str, status: str) -> None:
    """Publish a scene status update from a Celery worker (sync context)."""
    _publish_sync(project_id, {
        "type": "scene_update",
        "scene_id": scene_id,
        "status": status,
    })


def publish_project_update(project_id: str, status: str) -> None:
    """Publish a project status update from a Celery worker (sync context)."""
    _publish_sync(project_id, {
        "type": "project_update",
        "status": status,
    })


def _publish_sync(project_id: str, message: dict[str, Any]) -> None:
    """Publish a message to the Redis channel for a project (sync, for Celery).

    Uses a shared ConnectionPool to avoid creating a new connection per call.
    """
    try:
        r = redis.Redis(connection_pool=_get_sync_pool())
        channel = f"{CHANNEL_PREFIX}{project_id}"
        r.publish(channel, json.dumps(message))
    except Exception:
        # Best-effort: don't crash the Celery task
        logger.warning("Failed to publish WS notification for project %s", project_id, exc_info=True)


# ──────── Subscriber (used by FastAPI — async) ────────

async def subscribe_project(project_id: str) -> tuple[aioredis.Redis, aioredis.client.PubSub]:
    """Create an async Redis PubSub subscription for a project channel.

    Returns both the client and pubsub so the caller can close both.
    """
    settings = get_settings()
    r = aioredis.from_url(settings.REDIS_URL)
    pubsub = r.pubsub()
    channel = f"{CHANNEL_PREFIX}{project_id}"
    await pubsub.subscribe(channel)
    return r, pubsub


async def listen_pubsub(pubsub: aioredis.client.PubSub):
    """Async generator that yields parsed messages from a PubSub subscription."""
    async for raw_message in pubsub.listen():
        if raw_message["type"] == "message":
            try:
                data = json.loads(raw_message["data"])
                yield data
            except (json.JSONDecodeError, TypeError):
                continue
