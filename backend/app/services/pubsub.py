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


def publish_compose_progress(project_id: str, rendered: int, total: int) -> None:
    """Publish compose render progress from a Celery worker (sync context)."""
    percent = round(rendered / total * 100) if total > 0 else 0
    _publish_sync(project_id, {
        "type": "compose_progress",
        "rendered": rendered,
        "total": total,
        "percent": percent,
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

_async_client: aioredis.Redis | None = None


def _get_async_client() -> aioredis.Redis:
    """Lazy-init a module-level async Redis client (singleton)."""
    global _async_client
    if _async_client is None:
        settings = get_settings()
        _async_client = aioredis.from_url(settings.REDIS_URL)
    return _async_client


async def subscribe_project(project_id: str) -> tuple[aioredis.Redis, aioredis.client.PubSub]:
    """Create an async Redis PubSub subscription for a project channel.

    Returns the shared client and a new pubsub instance.
    Caller should close the pubsub when done, but NOT the client.
    """
    r = _get_async_client()
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
