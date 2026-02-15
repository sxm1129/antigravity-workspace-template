from __future__ import annotations
"""Character CRUD API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.character import Character
from app.schemas.character import CharacterCreate, CharacterRead, CharacterUpdate

router = APIRouter()


@router.get("/", response_model=list[CharacterRead])
async def list_characters(
    project_id: str, db: AsyncSession = Depends(get_db)
):
    """List all characters for a project."""
    result = await db.execute(
        select(Character).where(Character.project_id == project_id)
    )
    return result.scalars().all()


@router.post("/", response_model=CharacterRead, status_code=201)
async def create_character(
    project_id: str,
    data: CharacterCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new character for a project."""
    character = Character(
        id=uuid.uuid4().hex[:36],
        project_id=project_id,
        name=data.name,
        appearance_prompt=data.appearance_prompt,
        nano_identity_refs=data.nano_identity_refs or [],
    )
    db.add(character)
    await db.flush()
    await db.refresh(character)
    return character


@router.get("/{character_id}", response_model=CharacterRead)
async def get_character(
    project_id: str, character_id: str, db: AsyncSession = Depends(get_db)
):
    """Get a character by ID."""
    character = await db.get(Character, character_id)
    if not character or character.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")
    return character


@router.patch("/{character_id}", response_model=CharacterRead)
async def update_character(
    project_id: str,
    character_id: str,
    data: CharacterUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a character's fields."""
    character = await db.get(Character, character_id)
    if not character or character.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(character, key, value)

    await db.flush()
    await db.refresh(character)
    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    project_id: str, character_id: str, db: AsyncSession = Depends(get_db)
):
    """Delete a character."""
    character = await db.get(Character, character_id)
    if not character or character.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")
    await db.delete(character)


@router.post("/{character_id}/generate-reference")
async def generate_character_ref(
    project_id: str, character_id: str, db: AsyncSession = Depends(get_db)
):
    """Generate a reference image for a character using AI."""
    character = await db.get(Character, character_id)
    if not character or character.project_id != project_id:
        raise HTTPException(status_code=404, detail="Character not found")

    if not character.appearance_prompt:
        raise HTTPException(status_code=400, detail="No appearance_prompt set for this character")

    from app.services.character_ref_gen import generate_character_reference

    ref_path = await generate_character_reference(
        character_name=character.name,
        appearance_prompt=character.appearance_prompt,
        project_id=project_id,
        character_id=character_id,
        style=character.project.style_preset or "default" if character.project else "default",
    )
    character.reference_image_path = ref_path
    await db.flush()
    await db.refresh(character)

    return {
        "character_id": character_id,
        "reference_image_path": ref_path,
    }

