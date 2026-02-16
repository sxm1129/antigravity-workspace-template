from __future__ import annotations
"""Episode API endpoints — CRUD and status management for episodes."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.episode import Episode, EpisodeStatus, EPISODE_VALID_TRANSITIONS
from app.models.scene import Scene
from app.schemas.episode import EpisodeRead, EpisodeUpdate, EpisodeStatusUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


def _episode_to_read(episode: Episode, scenes_count: int = 0) -> dict:
    """Convert Episode ORM object to EpisodeRead-compatible dict with scenes_count."""
    return {
        "id": episode.id,
        "project_id": episode.project_id,
        "episode_number": episode.episode_number,
        "title": episode.title,
        "synopsis": episode.synopsis,
        "full_script": episode.full_script,
        "final_video_path": episode.final_video_path,
        "status": episode.status,
        "scenes_count": scenes_count,
        "created_at": episode.created_at,
        "updated_at": episode.updated_at,
    }


@router.get("/projects/{project_id}/episodes", response_model=list[EpisodeRead])
async def list_episodes(project_id: str, db: AsyncSession = Depends(get_db)):
    """List all episodes for a project, ordered by episode_number."""
    # Subquery for scenes count per episode
    scenes_count_sq = (
        select(Scene.episode_id, sa_func.count(Scene.id).label("cnt"))
        .where(Scene.episode_id.isnot(None))
        .group_by(Scene.episode_id)
        .subquery()
    )

    result = await db.execute(
        select(Episode, scenes_count_sq.c.cnt)
        .outerjoin(scenes_count_sq, Episode.id == scenes_count_sq.c.episode_id)
        .where(Episode.project_id == project_id)
        .order_by(Episode.episode_number)
    )
    rows = result.all()
    return [_episode_to_read(ep, cnt or 0) for ep, cnt in rows]


@router.get("/episodes/{episode_id}", response_model=EpisodeRead)
async def get_episode(episode_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single episode by ID."""
    episode = await db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Count scenes
    result = await db.execute(
        select(sa_func.count(Scene.id)).where(Scene.episode_id == episode_id)
    )
    scenes_count = result.scalar() or 0

    return _episode_to_read(episode, scenes_count)


@router.patch("/episodes/{episode_id}", response_model=EpisodeRead)
async def update_episode(
    episode_id: str, data: EpisodeUpdate, db: AsyncSession = Depends(get_db)
):
    """Update an episode's content fields."""
    episode = await db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(episode, key, value)

    await db.flush()
    await db.refresh(episode)

    # Compute scenes_count for consistent response
    count_result = await db.execute(
        select(sa_func.count(Scene.id)).where(Scene.episode_id == episode_id)
    )
    scenes_count = count_result.scalar() or 0

    return _episode_to_read(episode, scenes_count)


@router.post("/episodes/{episode_id}/advance-status", response_model=EpisodeRead)
async def advance_episode_status(
    episode_id: str,
    data: EpisodeStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Advance or rollback an episode's status."""
    episode = await db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    target = data.target_status.value

    if not episode.can_transition_to(target):
        try:
            current_enum = EpisodeStatus(episode.status)
            valid_targets = EPISODE_VALID_TRANSITIONS.get(current_enum, set())
            valid_names = [s.value for s in valid_targets] if valid_targets else ["none"]
        except ValueError:
            valid_names = ["none"]

        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {episode.status} to {target}. "
                   f"Valid targets: {', '.join(valid_names)}",
        )

    episode.status = target
    await db.flush()
    await db.refresh(episode)

    # Compute scenes_count for consistent EpisodeRead response
    count_result = await db.execute(
        select(sa_func.count(Scene.id)).where(Scene.episode_id == episode_id)
    )
    scenes_count = count_result.scalar() or 0

    return _episode_to_read(episode, scenes_count)


@router.get("/episodes/{episode_id}/scenes")
async def list_episode_scenes(episode_id: str, db: AsyncSession = Depends(get_db)):
    """List all scenes for a specific episode."""
    result = await db.execute(
        select(Scene)
        .where(Scene.episode_id == episode_id)
        .order_by(Scene.sequence_order)
    )
    return result.scalars().all()
