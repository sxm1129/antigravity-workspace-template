from __future__ import annotations
"""Direct sync pipeline for E2E testing — bypasses Celery.

DEVELOPMENT ONLY: Runs the full AI pipeline synchronously in a single request.
This avoids the need for Redis + Celery worker during development/testing.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.project import Project
from app.models.scene import Scene

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


class RunPipelineRequest(BaseModel):
    project_id: str
    skip_video: bool = True  # skip video gen by default (needs ARK_API_KEY)


class PipelineResult(BaseModel):
    project_id: str
    status: str
    outline_length: int = 0
    script_length: int = 0
    scenes_count: int = 0
    images_generated: int = 0
    audio_generated: int = 0
    videos_generated: int = 0
    final_video_path: str | None = None
    errors: list[str] = []


@router.post("/run-full-pipeline", response_model=PipelineResult)
async def run_full_pipeline(
    req: RunPipelineRequest, db: AsyncSession = Depends(get_db)
):
    """Run the entire AI pipeline synchronously for testing.

    Stages: Outline → Script → Parse Scenes → TTS + Images → (optional) Videos → Compose
    """
    result = PipelineResult(project_id=req.project_id, status="running")

    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ----- Stage 1: Generate Outline (if not done) -----
    if project.status == "IDEATION":
        from app.services.ai_writer import generate_outline

        logger.info("Stage 1: Generating outline for project %s", req.project_id)
        try:
            outline = await generate_outline(project.logline)
            project.world_outline = outline
            project.status = "OUTLINE_REVIEW"
            await db.flush()
            result.outline_length = len(outline)
        except Exception as e:
            result.errors.append(f"Outline failed: {e}")
            result.status = "failed_at_outline"
            return result
    else:
        result.outline_length = len(project.world_outline or "")

    # ----- Stage 2: Generate Script -----
    if project.status == "OUTLINE_REVIEW":
        from app.services.ai_writer import generate_script

        logger.info("Stage 2: Generating script for project %s", req.project_id)
        try:
            script = await generate_script(project.world_outline)
            project.full_script = script
            project.status = "SCRIPT_REVIEW"
            await db.flush()
            result.script_length = len(script)
        except Exception as e:
            result.errors.append(f"Script failed: {e}")
            result.status = "failed_at_script"
            return result
    else:
        result.script_length = len(project.full_script or "")

    # ----- Stage 3: Parse Scenes -----
    if project.status == "SCRIPT_REVIEW":
        from app.services.ai_writer import parse_scenes

        logger.info("Stage 3: Parsing scenes for project %s", req.project_id)
        try:
            scenes_data = await parse_scenes(project.full_script)
            result.scenes_count = len(scenes_data)

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
        except Exception as e:
            result.errors.append(f"Parse scenes failed: {e}")
            result.status = "failed_at_parse"
            return result

    # ----- Stage 4: Generate TTS + Images -----
    if project.status in ("STORYBOARDING", "WAITING_ASSET_APPROVAL"):
        scene_result = await db.execute(
            select(Scene)
            .where(Scene.project_id == req.project_id)
            .order_by(Scene.sequence_order)
        )
        scenes = scene_result.scalars().all()

        from app.services.tts_service import synthesize_speech
        from app.services.image_gen import generate_image

        for scene in scenes:
            # TTS
            if scene.dialogue_text and not scene.local_audio_path:
                try:
                    logger.info("Stage 4: TTS for scene %s", scene.id[:8])
                    audio_path = await synthesize_speech(
                        scene.dialogue_text, req.project_id, scene.id
                    )
                    scene.local_audio_path = audio_path
                    result.audio_generated += 1
                except Exception as e:
                    result.errors.append(f"TTS scene {scene.id[:8]}: {e}")

            # Image
            if scene.prompt_visual and not scene.local_image_path:
                try:
                    logger.info("Stage 4: Image for scene %s", scene.id[:8])
                    image_path = await generate_image(
                        scene.prompt_visual, req.project_id, scene.id,
                        scene.sfx_text, None
                    )
                    scene.local_image_path = image_path
                    scene.status = "WAITING_HUMAN_APPROVAL"
                    result.images_generated += 1
                except Exception as e:
                    result.errors.append(f"Image scene {scene.id[:8]}: {e}")

        project.status = "WAITING_ASSET_APPROVAL"
        await db.flush()

    # ----- Stage 5: Generate Videos (optional) -----
    if not req.skip_video:
        scene_result = await db.execute(
            select(Scene)
            .where(
                Scene.project_id == req.project_id,
                Scene.local_image_path.isnot(None),
            )
            .order_by(Scene.sequence_order)
        )
        scenes = scene_result.scalars().all()

        from app.services.video_gen import generate_video

        for scene in scenes:
            if not scene.local_video_path:
                try:
                    logger.info("Stage 5: Video for scene %s", scene.id[:8])
                    video_path = await generate_video(
                        scene.prompt_motion or "",
                        req.project_id,
                        scene.id,
                        scene.local_image_path,
                        scene.local_audio_path,
                    )
                    scene.local_video_path = video_path
                    scene.status = "READY"
                    result.videos_generated += 1
                except Exception as e:
                    result.errors.append(f"Video scene {scene.id[:8]}: {e}")

        await db.flush()

    # ----- Stage 6: Compose Final Video -----
    scene_result = await db.execute(
        select(Scene)
        .where(
            Scene.project_id == req.project_id,
            Scene.local_video_path.isnot(None),
        )
        .order_by(Scene.sequence_order)
    )
    ready_scenes = scene_result.scalars().all()

    if ready_scenes:
        from app.services.ffmpeg_service import compose_final_video

        video_paths = [s.local_video_path for s in ready_scenes if s.local_video_path]
        if video_paths:
            try:
                logger.info("Stage 6: Composing final video")
                final_path = compose_final_video(req.project_id, video_paths)
                project.status = "COMPLETED"
                result.final_video_path = final_path
            except Exception as e:
                result.errors.append(f"Compose failed: {e}")

        await db.flush()

    result.status = project.status
    return result
