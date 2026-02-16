from __future__ import annotations
"""Story AI endpoints — the Writer's Room.

POST /api/story/generate-outline
POST /api/story/generate-script        (legacy, kept for backward compat)
POST /api/story/parse-scenes            (legacy, kept for backward compat)
POST /api/story/extract-and-generate    (new: episode-based batch flow)
POST /api/story/parse-episode-scenes    (new: per-episode scene parsing)

All endpoints follow the strict Human-in-the-Loop pattern:
- Generate content → return for human review → explicit APPROVE before next stage.
"""

import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project, ProjectStatus
from app.models.episode import Episode, EpisodeStatus
from app.models.scene import Scene, SceneStatus
from app.services import ai_writer

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateOutlineRequest(BaseModel):
    project_id: str


class GenerateScriptRequest(BaseModel):
    project_id: str


class ParseScenesRequest(BaseModel):
    project_id: str


class ExtractAndGenerateRequest(BaseModel):
    """Request for the new episode-based flow."""
    project_id: str


class ParseEpisodeScenesRequest(BaseModel):
    """Request to parse scenes for a single episode."""
    episode_id: str


class StoryResponse(BaseModel):
    project_id: str
    status: str
    content: str | None = None
    scenes_count: int | None = None
    episodes_count: int | None = None


@router.post("/generate-outline", response_model=StoryResponse)
async def generate_outline(
    req: GenerateOutlineRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 1: Generate world outline from logline using Gemini.

    Requires project in DRAFT status.
    After generation, advances to OUTLINE_REVIEW for human approval.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.DRAFT.value:
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in DRAFT status (current: {project.status})",
        )

    if not project.logline:
        raise HTTPException(status_code=400, detail="Project logline is empty")

    # CRITICAL: Read logline + style, then release DB before calling AI
    logline = project.logline
    style = project.style_preset or "default"

    # Call AI writer (may be mock or real)
    outline = await ai_writer.generate_outline(logline, style=style)

    # Write result back with a new DB operation
    project.world_outline = outline
    project.status = ProjectStatus.OUTLINE_REVIEW.value
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project.id,
        status=project.status,
        content=outline,
    )


@router.post("/extract-and-generate", response_model=StoryResponse)
async def extract_episodes_and_generate_scripts(
    req: ExtractAndGenerateRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 2 (episode-based): Extract episodes from outline and batch generate scripts.

    Requires project in OUTLINE_REVIEW status.
    1. Extracts episode titles/synopses from the outline via AI
    2. Creates Episode records
    3. Generates a script for each episode sequentially
    4. Advances project to IN_PRODUCTION
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.OUTLINE_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in OUTLINE_REVIEW status (current: {project.status})",
        )

    if not project.world_outline:
        raise HTTPException(status_code=400, detail="No outline to extract episodes from")

    outline = project.world_outline

    # Step 1: Extract episodes from outline
    logger.info("Extracting episodes from outline for project %s", project.id)
    episodes_data = await ai_writer.extract_episodes(outline)

    if not episodes_data:
        raise HTTPException(status_code=500, detail="AI failed to extract any episodes from outline")

    # Step 2: Clear existing episodes for this project
    await db.execute(delete(Episode).where(Episode.project_id == project.id))

    # Step 3: Create Episode records and generate scripts
    created_episodes = []
    for ep_data in episodes_data:
        episode_number = ep_data.get("episode_number", len(created_episodes) + 1)
        title = ep_data.get("title", f"第{episode_number}集")
        synopsis = ep_data.get("synopsis", "")

        # Generate script for this episode
        logger.info("Generating script for episode %d: %s", episode_number, title)
        try:
            script = await ai_writer.generate_episode_script(
                outline=outline,
                episode_number=episode_number,
                episode_title=title,
                episode_synopsis=synopsis,
            )
        except Exception as e:
            logger.error("Failed to generate script for episode %d: %s", episode_number, e)
            script = None

        episode = Episode(
            id=uuid.uuid4().hex[:36],
            project_id=project.id,
            episode_number=episode_number,
            title=title,
            synopsis=synopsis,
            full_script=script,
            status=(
                EpisodeStatus.SCRIPT_REVIEW.value
                if script
                else EpisodeStatus.SCRIPT_GENERATING.value
            ),
        )
        db.add(episode)
        created_episodes.append(episode)

    # Step 4: Advance project to IN_PRODUCTION
    project.status = ProjectStatus.IN_PRODUCTION.value
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project.id,
        status=project.status,
        episodes_count=len(created_episodes),
    )


@router.post("/parse-episode-scenes", response_model=StoryResponse)
async def parse_episode_scenes(
    req: ParseEpisodeScenesRequest, db: AsyncSession = Depends(get_db)
):
    """Parse scenes for a single episode.

    Requires episode in SCRIPT_REVIEW status.
    After parsing, advances episode to STORYBOARD.
    """
    episode = await db.get(Episode, req.episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    if episode.status != EpisodeStatus.SCRIPT_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Episode must be in SCRIPT_REVIEW status (current: {episode.status})",
        )

    if not episode.full_script:
        raise HTTPException(status_code=400, detail="No script to parse")

    script = episode.full_script

    # Parse scenes via AI
    scenes_data = await ai_writer.parse_scenes(script)

    # Clear existing scenes for this episode
    await db.execute(delete(Scene).where(Scene.episode_id == episode.id))

    # Bulk insert scenes
    for scene_data in scenes_data:
        scene = Scene(
            id=uuid.uuid4().hex[:36],
            project_id=episode.project_id,
            episode_id=episode.id,
            sequence_order=scene_data.get("sequence_order", 0),
            dialogue_text=scene_data.get("dialogue_text"),
            prompt_visual=scene_data.get("prompt_visual"),
            prompt_motion=scene_data.get("prompt_motion"),
            sfx_text=scene_data.get("sfx_text"),
            status=SceneStatus.PENDING.value,
        )
        db.add(scene)

    episode.status = EpisodeStatus.STORYBOARD.value
    await db.flush()
    await db.refresh(episode)

    return StoryResponse(
        project_id=episode.project_id,
        status=episode.status,
        scenes_count=len(scenes_data),
    )


# ──────────────────────────────────────────────────
# Legacy endpoints (kept for backward compatibility)
# ──────────────────────────────────────────────────


@router.post("/generate-script", response_model=StoryResponse)
async def generate_script(
    req: GenerateScriptRequest, db: AsyncSession = Depends(get_db)
):
    """Stage 2 (legacy): Generate full script from approved outline."""
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.OUTLINE_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in OUTLINE_REVIEW status (current: {project.status})",
        )

    if not project.world_outline:
        raise HTTPException(status_code=400, detail="No outline to expand")

    outline = project.world_outline
    script = await ai_writer.generate_script(outline)

    project.full_script = script
    project.status = ProjectStatus.SCRIPT_REVIEW.value
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
    """Stage 3 (legacy): Parse script into structured scene data."""
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.SCRIPT_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in SCRIPT_REVIEW status (current: {project.status})",
        )

    if not project.full_script:
        raise HTTPException(status_code=400, detail="No script to parse")

    script = project.full_script
    scenes_data = await ai_writer.parse_scenes(script)

    # Clear existing scenes for this project before inserting new ones
    await db.execute(delete(Scene).where(Scene.project_id == project.id))

    for scene_data in scenes_data:
        scene = Scene(
            id=uuid.uuid4().hex[:36],
            project_id=project.id,
            sequence_order=scene_data.get("sequence_order", 0),
            dialogue_text=scene_data.get("dialogue_text"),
            prompt_visual=scene_data.get("prompt_visual"),
            prompt_motion=scene_data.get("prompt_motion"),
            sfx_text=scene_data.get("sfx_text"),
            status=SceneStatus.PENDING.value,
        )
        db.add(scene)

    project.status = ProjectStatus.STORYBOARD.value
    await db.flush()
    await db.refresh(project)

    return StoryResponse(
        project_id=project.id,
        status=project.status,
        scenes_count=len(scenes_data),
    )
