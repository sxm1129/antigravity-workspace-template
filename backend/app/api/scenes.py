from __future__ import annotations
"""Scene management API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.scene import Scene
from app.schemas.scene import SceneCreate, SceneRead, SceneUpdate, SceneBulkCreate

router = APIRouter()


@router.get("/", response_model=list[SceneRead])
async def list_scenes(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 200,
    offset: int = 0,
):
    """List all scenes for a project, ordered by sequence. Supports pagination."""
    result = await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.sequence_order)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/", response_model=SceneRead, status_code=201)
async def create_scene(
    project_id: str,
    data: SceneCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a single scene."""
    scene = Scene(
        id=uuid.uuid4().hex[:36],
        project_id=project_id,
        **data.model_dump(),
    )
    db.add(scene)
    await db.flush()
    await db.refresh(scene)
    return scene


@router.post("/bulk", response_model=list[SceneRead], status_code=201)
async def bulk_create_scenes(
    project_id: str,
    data: SceneBulkCreate,
    db: AsyncSession = Depends(get_db),
):
    """Bulk create scenes from script parsing output."""
    scenes = []
    for scene_data in data.scenes:
        scene = Scene(
            id=uuid.uuid4().hex[:36],
            project_id=project_id,
            **scene_data.model_dump(),
        )
        db.add(scene)
        scenes.append(scene)

    await db.flush()
    for s in scenes:
        await db.refresh(s)

    return scenes


@router.get("/{scene_id}", response_model=SceneRead)
async def get_scene(
    project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)
):
    """Get a scene by ID."""
    scene = await db.get(Scene, scene_id)
    if not scene or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.patch("/{scene_id}", response_model=SceneRead)
async def update_scene(
    project_id: str,
    scene_id: str,
    data: SceneUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a scene's fields."""
    scene = await db.get(Scene, scene_id)
    if not scene or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail="Scene not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(scene, key, value)

    await db.flush()
    await db.refresh(scene)
    return scene


@router.post("/reorder", response_model=list[SceneRead])
async def reorder_scenes(
    project_id: str,
    scene_ids: list[str],
    db: AsyncSession = Depends(get_db),
):
    """Reorder scenes by providing the scene IDs in desired order.

    Args:
        project_id: Project ID.
        scene_ids: List of scene IDs in the desired new order.
    """
    for i, scene_id in enumerate(scene_ids):
        await db.execute(
            update(Scene)
            .where(Scene.id == scene_id, Scene.project_id == project_id)
            .values(sequence_order=i)
        )

    await db.flush()

    result = await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.sequence_order)
    )
    return result.scalars().all()


@router.delete("/{scene_id}", status_code=204)
async def delete_scene(
    project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)
):
    """Delete a scene."""
    scene = await db.get(Scene, scene_id)
    if not scene or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail="Scene not found")
    await db.delete(scene)
