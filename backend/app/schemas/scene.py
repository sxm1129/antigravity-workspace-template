from __future__ import annotations
"""Pydantic v2 schemas for Scene model."""

from typing import Optional

from pydantic import BaseModel, Field

from app.models.scene import SceneStatus


class SceneCreate(BaseModel):
    """Schema for creating a single scene."""

    sequence_order: int = 0
    dialogue_text: str | None = None
    prompt_visual: str | None = None
    prompt_motion: str | None = None
    sfx_text: str | None = None


class SceneBulkCreate(BaseModel):
    """Schema for bulk creating scenes from script parsing."""

    scenes: list[SceneCreate]


class SceneUpdate(BaseModel):
    """Schema for updating a scene."""

    sequence_order: int | None = None
    dialogue_text: str | None = None
    prompt_visual: str | None = None
    prompt_motion: str | None = None
    sfx_text: str | None = None
    status: SceneStatus | None = None


class SceneRead(BaseModel):
    """Schema for reading a scene."""

    id: str
    project_id: str
    episode_id: str | None = None
    sequence_order: int
    dialogue_text: str | None = None
    prompt_visual: str | None = None
    prompt_motion: str | None = None
    sfx_text: str | None = None
    local_audio_path: str | None = None
    local_image_path: str | None = None
    local_video_path: str | None = None
    status: str

    model_config = {"from_attributes": True}
