"""Storyboard editor API — drag-drop reorder + shot configuration."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import get_db
from app.services import storyboard_editor
from app.services.image_quality import upscale_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/storyboard", tags=["Storyboard"])


class SceneOrderItem(BaseModel):
    scene_id: str
    sequence_order: int


class ReorderRequest(BaseModel):
    scene_order: list[SceneOrderItem]


class ShotConfigRequest(BaseModel):
    prompt_visual: str | None = None
    prompt_motion: str | None = None
    sfx_text: str | None = None
    dialogue_text: str | None = None


class UpscaleRequest(BaseModel):
    local_image_path: str = Field(..., description="Relative path in media_volume")
    scale: int = Field(2, ge=2, le=4, description="Upscale factor")

    @field_validator("local_image_path")
    @classmethod
    def validate_path_safety(cls, v: str) -> str:
        """Reject path traversal attempts at API boundary."""
        import os
        if os.path.isabs(v):
            raise ValueError("Absolute paths not allowed")
        if ".." in v:
            raise ValueError("Path traversal (..) not allowed")
        return v


@router.post("/{project_id}/reorder")
async def reorder_scenes(
    project_id: str, req: ReorderRequest, db=Depends(get_db),
) -> dict[str, Any]:
    """Batch reorder scenes (drag-drop)."""
    result = await storyboard_editor.batch_reorder_scenes(
        db, project_id,
        [item.model_dump() for item in req.scene_order],
    )
    return {"scenes": result}


@router.put("/scene/{scene_id}/config")
async def update_shot_config(
    scene_id: str, req: ShotConfigRequest, db=Depends(get_db),
) -> dict[str, Any]:
    """Update shot configuration for a single scene panel."""
    try:
        return await storyboard_editor.update_shot_config(
            db, scene_id,
            prompt_visual=req.prompt_visual,
            prompt_motion=req.prompt_motion,
            sfx_text=req.sfx_text,
            dialogue_text=req.dialogue_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{project_id}/summary")
async def get_storyboard_summary(
    project_id: str, episode_id: str | None = None, db=Depends(get_db),
) -> dict[str, Any]:
    """Get storyboard summary view for the editor UI."""
    return await storyboard_editor.get_storyboard_summary(db, project_id, episode_id)


@router.post("/upscale")
async def api_upscale_image(req: UpscaleRequest) -> dict[str, Any]:
    """Upscale an image using AI or FFmpeg fallback."""
    try:
        result_path = await upscale_image(req.local_image_path, scale=req.scale)
        return {"original": req.local_image_path, "upscaled": result_path, "scale": req.scale}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
