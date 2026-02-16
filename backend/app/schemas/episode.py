from __future__ import annotations
"""Pydantic v2 schemas for Episode model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.episode import EpisodeStatus


class EpisodeCreate(BaseModel):
    """Schema for creating an episode (internal use during extraction)."""

    project_id: str
    episode_number: int = 1
    title: str = Field(..., min_length=1, max_length=255)
    synopsis: str | None = None


class EpisodeUpdate(BaseModel):
    """Schema for updating an episode's content fields."""

    title: str | None = Field(None, max_length=255)
    synopsis: str | None = None
    full_script: str | None = None


class EpisodeStatusUpdate(BaseModel):
    """Schema for advancing or rolling back an episode's status."""

    target_status: EpisodeStatus


class EpisodeRead(BaseModel):
    """Schema for reading an episode."""

    id: str
    project_id: str
    episode_number: int
    title: str
    synopsis: str | None = None
    full_script: str | None = None
    final_video_path: str | None = None
    status: str
    scenes_count: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
