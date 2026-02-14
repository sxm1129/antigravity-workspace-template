from __future__ import annotations
"""WebSocket endpoint for real-time task progress broadcasting."""

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

# Active WebSocket connections keyed by project_id
_connections: dict[str, list[WebSocket]] = defaultdict(list)


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket connection for monitoring task progress on a project.

    Sends JSON messages with format:
    {
        "type": "scene_update" | "project_update" | "task_progress",
        "scene_id": "...",
        "status": "...",
        "data": { ... }
    }
    """
    await websocket.accept()
    _connections[project_id].append(websocket)
    logger.info("WebSocket connected: project=%s, total=%d", project_id, len(_connections[project_id]))

    try:
        while True:
            # Keep connection alive, listen for client messages if needed
            data = await websocket.receive_text()
            # Client can send ping or other commands
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        _connections[project_id].remove(websocket)
        logger.info("WebSocket disconnected: project=%s", project_id)
    except Exception:
        if websocket in _connections[project_id]:
            _connections[project_id].remove(websocket)


async def broadcast_to_project(project_id: str, message: dict) -> None:
    """Broadcast a message to all WebSocket connections for a project.

    Args:
        project_id: Target project.
        message: Dict to send as JSON.
    """
    msg_text = json.dumps(message, ensure_ascii=False)
    dead_connections = []

    for ws in _connections.get(project_id, []):
        try:
            await ws.send_text(msg_text)
        except Exception:
            dead_connections.append(ws)

    # Clean up dead connections
    for ws in dead_connections:
        if ws in _connections[project_id]:
            _connections[project_id].remove(ws)
