from __future__ import annotations
"""Pydantic v2 schemas for Project model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    title: str = Field(..., min_length=1, max_length=255)
    logline: str | None = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project's content fields."""

    title: str | None = Field(None, max_length=255)
    logline: str | None = None
    world_outline: str | None = None
    full_script: str | None = None


class ProjectStatusUpdate(BaseModel):
    """Schema for advancing or rolling back a project's status."""

    target_status: ProjectStatus


class ProjectRead(BaseModel):
    """Schema for reading a project."""

    id: str
    title: str
    logline: str | None = None
    world_outline: str | None = None
    full_script: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
