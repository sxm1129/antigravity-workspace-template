from __future__ import annotations
"""Story AI endpoints — the Writer's Room.

POST /api/story/generate-outline
POST /api/story/generate-script
POST /api/story/parse-scenes

All endpoints follow the strict Human-in-the-Loop pattern:
- Generate content → return for human review → explicit APPROVE before next stage.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project
from app.models.scene import Scene
from app.services import ai_writer

router = APIRouter()


class GenerateOutlineRequest(BaseModel):
    project_id: str


class GenerateScriptRequest(BaseModel):
    project_id: str


class ParseScenesRequest(BaseModel):
    project_id: str


class StoryResponse(BaseModel):
    project_id: str
    status: str
    content: str | None = None
    scenes_count: int | None = None


@router.post("/generate-outline", response_model=StoryResponse)
async def generate_outline(
    req: GenerateOutlineRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 1: Generate world outline from logline using Gemini.

    Requires project in IDEATION status.
    After generation, advances to OUTLINE_REVIEW for human approval.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != "IDEATION":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in IDEATION status (current: {project.status})",
        )

    if not project.logline:
        raise HTTPException(status_code=400, detail="Project logline is empty")

    # CRITICAL: Read logline, then release DB before calling AI
    logline = project.logline
    project_id = project.id

    # Call AI writer (may be mock or real)
    outline = await ai_writer.generate_outline(logline)

    # Write result back with a new DB operation
    project.world_outline = outline
    project.status = "OUTLINE_REVIEW"
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project_id,
        status=project.status,
        content=outline,
    )


@router.post("/generate-script", response_model=StoryResponse)
async def generate_script(
    req: GenerateScriptRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 2: Generate full script from approved outline.

    Requires project in OUTLINE_REVIEW status (human has reviewed the outline).
    After generation, advances to SCRIPT_REVIEW.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != "OUTLINE_REVIEW":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in OUTLINE_REVIEW status (current: {project.status})",
        )

    if not project.world_outline:
        raise HTTPException(status_code=400, detail="No outline to expand")

    outline = project.world_outline

    # Call AI writer
    script = await ai_writer.generate_script(outline)

    project.full_script = script
    project.status = "SCRIPT_REVIEW"
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project.id,
        status=project.status,
        content=script,
    )


@router.post("/parse-scenes", response_model=StoryResponse)
async def parse_scenes(
    req: ParseScenesRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 3: Parse script into structured scene data.

    Requires project in SCRIPT_REVIEW status.
    Forces JSON mode on AI to extract visual/motion prompts.
    After parsing, advances to STORYBOARDING.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != "SCRIPT_REVIEW":
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in SCRIPT_REVIEW status (current: {project.status})",
        )

    if not project.full_script:
        raise HTTPException(status_code=400, detail="No script to parse")

    script = project.full_script

    # Parse scenes via AI
    scenes_data = await ai_writer.parse_scenes(script)

    # Bulk insert scenes
    for scene_data in scenes_data:
        scene = Scene(
            id=uuid.uuid4().hex[:36],
            project_id=project.id,
            sequence_order=scene_data.get("sequence_order", 0),
            dialogue_text=scene_data.get("dialogue_text"),
            prompt_visual=scene_data.get("prompt_visual"),
            prompt_motion=scene_data.get("prompt_motion"),
            sfx_text=scene_data.get("sfx_text"),
            status="PENDING",
        )
        db.add(scene)

    project.status = "STORYBOARDING"
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project.id,
        status=project.status,
        scenes_count=len(scenes_data),
    )
