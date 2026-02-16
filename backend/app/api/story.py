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

import asyncio
import json
import uuid
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.project import Project, ProjectStatus
from app.models.episode import Episode, EpisodeStatus
from app.models.scene import Scene, SceneStatus
from app.services import ai_writer
from app.services.outline_pipeline import OutlinePipeline

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Deadlock retry helper ──────────────────────────

_MAX_DEADLOCK_RETRIES = 3
_DEADLOCK_BACKOFF_BASE = 0.3  # seconds


async def _flush_with_retry(
    db: AsyncSession, *, max_retries: int = _MAX_DEADLOCK_RETRIES
) -> None:
    """Flush the session, retrying on MySQL deadlock (error 1213).

    Uses exponential back-off: 0.3s, 0.6s, 1.2s.
    """
    for attempt in range(1, max_retries + 1):
        try:
            await db.flush()
            return
        except OperationalError as exc:
            # MySQL deadlock error code = 1213
            if exc.orig and getattr(exc.orig, "args", (None,))[0] == 1213:
                if attempt == max_retries:
                    logger.error("Deadlock persists after %d retries, raising", max_retries)
                    raise
                wait = _DEADLOCK_BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Deadlock detected (attempt %d/%d), retrying in %.1fs",
                    attempt, max_retries, wait,
                )
                await asyncio.sleep(wait)
            else:
                raise


class GenerateOutlineRequest(BaseModel):
    project_id: str


class GenerateScriptRequest(BaseModel):
    project_id: str


class ParseScenesRequest(BaseModel):
    project_id: str


class ExtractAndGenerateRequest(BaseModel):
    """Request for the new episode-based flow."""
    project_id: str


class RegenerateOutlineRequest(BaseModel):
    """Request to regenerate outline with optional custom prompt."""
    project_id: str
    custom_prompt: str | None = None


class ParseEpisodeScenesRequest(BaseModel):
    """Request to parse scenes for a single episode."""
    episode_id: str


class StoryResponse(BaseModel):
    project_id: str
    status: str
    content: str | None = None
    scenes_count: int | None = None
    episodes_count: int | None = None


class ContinuePipelineRequest(BaseModel):
    """Request to continue the pipeline from a specific step with modified data."""
    project_id: str
    start_from: int  # Step index to resume from (0-3)
    intent_result: dict[str, Any] | None = None
    world_result: dict[str, Any] | None = None
    plot_result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# SSE Pipeline endpoints
# ---------------------------------------------------------------------------

async def _pipeline_event_stream(
    project_id: str,
    logline: str,
    style: str,
    *,
    start_from: int = 0,
    prior_intent: dict | None = None,
    prior_world: dict | None = None,
    prior_plot: dict | None = None,
):
    """Async generator that yields SSE events from the outline pipeline."""
    from app.database import async_session_factory

    pipeline = OutlinePipeline()

    try:
        async for event in pipeline.run(
            logline, style,
            start_from=start_from,
            prior_intent=prior_intent,
            prior_world=prior_world,
            prior_plot=prior_plot,
        ):
            # Yield as SSE format
            event_data = event.model_dump(exclude_none=True)
            yield f"event: {event.event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            # On pipeline_complete, save the outline to DB
            if event.event_type == "pipeline_complete" and event.outline:
                async with async_session_factory() as db:
                    project = await db.get(Project, project_id)
                    if project:
                        project.world_outline = event.outline
                        project.status = ProjectStatus.OUTLINE_REVIEW.value
                        await db.commit()
    except Exception as e:
        logger.exception("SSE stream error for project %s", project_id)
        from app.services.agents.base import PipelineEvent
        error_event = PipelineEvent(event_type="error", error=f"Stream error: {e}")
        event_data = error_event.model_dump(exclude_none=True)
        yield f"event: error\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"


@router.post("/generate-outline-stream")
async def generate_outline_stream(
    req: GenerateOutlineRequest, db: AsyncSession = Depends(get_db)
):
    """Generate world outline using multi-agent pipeline with SSE progress.

    Returns a text/event-stream with step_start, step_complete, and
    pipeline_complete events for real-time progress display.
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

    logline = project.logline
    style = project.style_preset or "default"

    return StreamingResponse(
        _pipeline_event_stream(project.id, logline, style),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/continue-pipeline")
async def continue_pipeline(
    req: ContinuePipelineRequest, db: AsyncSession = Depends(get_db)
):
    """Continue the pipeline from a specific step after user edits.

    Allows users to modify intermediate results (e.g. characters)
    and resume the pipeline from that point.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.logline:
        raise HTTPException(status_code=400, detail="Project logline is empty")

    if not (0 <= req.start_from <= 3):
        raise HTTPException(
            status_code=400,
            detail=f"start_from must be 0-3 (got: {req.start_from})",
        )

    # Validate that required prior results are provided when resuming
    if req.start_from >= 1 and not req.intent_result:
        raise HTTPException(
            status_code=400,
            detail="intent_result is required when start_from >= 1",
        )
    if req.start_from >= 2 and not req.world_result:
        raise HTTPException(
            status_code=400,
            detail="world_result is required when start_from >= 2",
        )
    if req.start_from >= 3 and not req.plot_result:
        raise HTTPException(
            status_code=400,
            detail="plot_result is required when start_from >= 3",
        )

    logline = project.logline
    style = project.style_preset or "default"

    return StreamingResponse(
        _pipeline_event_stream(
            project.id, logline, style,
            start_from=req.start_from,
            prior_intent=req.intent_result,
            prior_world=req.world_result,
            prior_plot=req.plot_result,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


@router.post("/regenerate-outline", response_model=StoryResponse)
async def regenerate_outline(
    req: RegenerateOutlineRequest, db: AsyncSession = Depends(get_db)
):
    """Regenerate world outline for a project in OUTLINE_REVIEW status.

    Allows users to regenerate the outline if unsatisfied, optionally
    with a custom system prompt they have edited.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.OUTLINE_REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in OUTLINE_REVIEW status (current: {project.status})",
        )

    if not project.logline:
        raise HTTPException(status_code=400, detail="Project logline is empty")

    logline = project.logline
    style = project.style_preset or "default"

    outline = await ai_writer.generate_outline(
        logline, style=style, custom_prompt=req.custom_prompt
    )

    project.world_outline = outline
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

        # Incremental save — commit each episode so prior work isn't lost
        # if a later LLM call fails
        await _flush_with_retry(db)
        logger.info("Episode %d saved to DB (%s)", episode_number, episode.status)

    # Step 4: Advance project to IN_PRODUCTION
    project.status = ProjectStatus.IN_PRODUCTION.value
    await _flush_with_retry(db)
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
    await _flush_with_retry(db)
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
