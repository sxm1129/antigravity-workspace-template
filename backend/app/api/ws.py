"""WebSocket endpoint for real-time task progress.

Uses Redis Pub/Sub to receive notifications from Celery workers
and relay them to connected browser clients.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

# In-process registry: project_id -> set of active WebSocket connections
_project_connections: dict[str, set[WebSocket]] = {}


@router.websocket("/ws/{project_id}")
async def ws_project(ws: WebSocket, project_id: str):
    """WebSocket endpoint for a project's real-time updates.

    1. Accepts WebSocket connection
    2. Subscribes to Redis Pub/Sub channel for this project
    3. Relays messages from Redis to the WebSocket client
    4. Handles client pings/pongs
    """
    await ws.accept()

    # Register connection
    if project_id not in _project_connections:
        _project_connections[project_id] = set()
    _project_connections[project_id].add(ws)

    logger.info("WS connected: project=%s (total=%d)", project_id, len(_project_connections[project_id]))

    # Start Redis Pub/Sub listener task
    redis_client = None
    pubsub = None
    listener_task = None
    try:
        from app.services.pubsub import subscribe_project, listen_pubsub

        redis_client, pubsub = await subscribe_project(project_id)
        listener_task = asyncio.create_task(
            _relay_pubsub_to_ws(pubsub, ws, project_id)
        )

        # Keep connection alive — read client messages (pings, etc.)
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        logger.info("WS disconnected: project=%s", project_id)
    except Exception as exc:
        logger.warning("WS error for project=%s: %s", project_id, exc)
    finally:
        # Cleanup
        _project_connections.get(project_id, set()).discard(ws)
        if not _project_connections.get(project_id):
            _project_connections.pop(project_id, None)
        if listener_task:
            listener_task.cancel()
        if pubsub:
            await pubsub.unsubscribe()
            await pubsub.close()
        # NOTE: do NOT close redis_client — it's a shared singleton from pubsub.py


async def _relay_pubsub_to_ws(pubsub, ws: WebSocket, project_id: str):
    """Background task: read from Redis Pub/Sub and forward to WebSocket client."""
    try:
        from app.services.pubsub import listen_pubsub

        async for message in listen_pubsub(pubsub):
            try:
                await ws.send_json(message)
            except Exception:
                break  # WebSocket closed
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        logger.warning("Pub/Sub relay error for project=%s: %s", project_id, exc)


async def broadcast_to_project(project_id: str, message: dict[str, Any]) -> None:
    """Broadcast a message to all WebSocket clients connected to a project.

    This is for in-process use (e.g., from FastAPI endpoints).
    For cross-process notifications (from Celery), use pubsub.publish_* functions.
    """
    connections = _project_connections.get(project_id, set())
    dead = set()
    for ws in connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    connections -= dead
