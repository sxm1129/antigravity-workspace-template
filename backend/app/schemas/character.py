from __future__ import annotations
"""Pydantic v2 schemas for Character model."""

from pydantic import BaseModel, Field


class CharacterCreate(BaseModel):
    """Schema for creating a character."""

    name: str = Field(..., min_length=1, max_length=100)
    appearance_prompt: str | None = None
    nano_identity_refs: list[str] | None = None


class CharacterUpdate(BaseModel):
    """Schema for updating a character."""

    name: str | None = Field(None, max_length=100)
    appearance_prompt: str | None = None
    nano_identity_refs: list[str] | None = None


class CharacterRead(BaseModel):
    """Schema for reading a character."""

    id: str
    project_id: str
    name: str
    appearance_prompt: str | None = None
    nano_identity_refs: list[str] | None = None

    model_config = {"from_attributes": True}
