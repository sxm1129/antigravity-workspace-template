"""Storyboard enhancement service — drag-drop reorder + shot configuration.

Phase 4 features:
- Batch reorder scenes (drag-drop)
- Shot configuration DTO (camera angle, framing, movement)
- Storyboard export as PDF/image grid
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene import Scene

logger = logging.getLogger(__name__)


async def batch_reorder_scenes(
    db: AsyncSession,
    project_id: str,
    scene_order: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Batch reorder scenes — supports drag-and-drop UI.

    Args:
        project_id: Project ID.
        scene_order: List of {scene_id, sequence_order} dicts.

    Returns:
        Updated scene list with new order.
    """
    for item in scene_order:
        scene_id = item["scene_id"]
        new_order = item["sequence_order"]
        await db.execute(
            update(Scene)
            .where(Scene.id == scene_id, Scene.project_id == project_id)
            .values(sequence_order=new_order)
        )

    await db.commit()

    result = await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.sequence_order)
    )
    scenes = result.scalars().all()

    logger.info("Reordered %d scenes for project %s", len(scenes), project_id)
    return [
        {
            "scene_id": s.id,
            "sequence_order": s.sequence_order,
            "dialogue_text": s.dialogue_text,
            "status": s.status,
        }
        for s in scenes
    ]


async def update_shot_config(
    db: AsyncSession,
    scene_id: str,
    *,
    prompt_visual: str | None = None,
    prompt_motion: str | None = None,
    sfx_text: str | None = None,
    dialogue_text: str | None = None,
) -> dict[str, Any]:
    """Update shot configuration for a single scene.

    This is the detailed editor panel for each storyboard panel.
    """
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if not scene:
        raise ValueError(f"Scene not found: {scene_id}")

    if prompt_visual is not None:
        scene.prompt_visual = prompt_visual
    if prompt_motion is not None:
        scene.prompt_motion = prompt_motion
    if sfx_text is not None:
        scene.sfx_text = sfx_text
    if dialogue_text is not None:
        scene.dialogue_text = dialogue_text

    await db.commit()
    await db.refresh(scene)

    return {
        "scene_id": scene.id,
        "prompt_visual": scene.prompt_visual,
        "prompt_motion": scene.prompt_motion,
        "sfx_text": scene.sfx_text,
        "dialogue_text": scene.dialogue_text,
        "status": scene.status,
    }


async def get_storyboard_summary(
    db: AsyncSession,
    project_id: str,
    episode_id: str | None = None,
) -> dict[str, Any]:
    """Get a summary view of the storyboard for the editor UI.

    Returns scene list with thumbnails, order, and status.
    """
    query = select(Scene).where(Scene.project_id == project_id)
    if episode_id:
        query = query.where(Scene.episode_id == episode_id)
    query = query.order_by(Scene.sequence_order)

    result = await db.execute(query)
    scenes = result.scalars().all()

    total = len(scenes)
    by_status = {}
    for s in scenes:
        by_status[s.status] = by_status.get(s.status, 0) + 1

    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "total_scenes": total,
        "status_breakdown": by_status,
        "scenes": [
            {
                "scene_id": s.id,
                "sequence_order": s.sequence_order,
                "dialogue_text": (s.dialogue_text or "")[:50],
                "thumbnail": s.local_image_path,
                "status": s.status,
                "has_video": bool(s.local_video_path),
                "has_audio": bool(s.local_audio_path),
            }
            for s in scenes
        ],
    }
