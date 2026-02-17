from __future__ import annotations
"""Asset generation API endpoints — dispatches Celery tasks for TTS, image, and video.

Enforces the Human-in-the-Loop gate: images must be APPROVED before video generation.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.scene import Scene, SceneStatus
from app.models.character import Character
from app.models.project import Project, ProjectStatus
from app.models.episode import Episode, EpisodeStatus

router = APIRouter()


class GenerateAssetsRequest(BaseModel):
    project_id: str
    episode_id: str | None = None


class GenerateSceneImageRequest(BaseModel):
    scene_id: str


class ApproveSceneRequest(BaseModel):
    scene_id: str


class GenerateSceneVideoRequest(BaseModel):
    scene_id: str


class ComposeVideoRequest(BaseModel):
    project_id: str
    episode_id: str | None = None


@router.post("/generate-all-images")
async def generate_all_scene_images(
    req: GenerateAssetsRequest, db: AsyncSession = Depends(get_db)
):
    """Dispatch TTS + image generation tasks for ALL pending scenes in a project.

    Transitions project to PRODUCTION.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status not in (
        ProjectStatus.STORYBOARD.value,
        ProjectStatus.PRODUCTION.value,
        ProjectStatus.IN_PRODUCTION.value,
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Project must be in STORYBOARD or IN_PRODUCTION status (current: {project.status})",
        )

    # Validate episode if provided
    episode = None
    if req.episode_id:
        episode = await db.get(Episode, req.episode_id)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        if episode.project_id != req.project_id:
            raise HTTPException(status_code=400, detail="Episode does not belong to this project")

    # Get pending scenes (filtered by episode if provided)
    scene_query = select(Scene).where(
        Scene.project_id == req.project_id,
        Scene.status == SceneStatus.PENDING.value,
    )
    if req.episode_id:
        scene_query = scene_query.where(Scene.episode_id == req.episode_id)
    result = await db.execute(scene_query.order_by(Scene.sequence_order))
    scenes = result.scalars().all()

    if not scenes:
        raise HTTPException(status_code=400, detail="No pending scenes to generate")

    # Get character identity refs for this project
    char_result = await db.execute(
        select(Character).where(Character.project_id == req.project_id)
    )
    characters = char_result.scalars().all()
    all_identity_refs = []
    for char in characters:
        if char.nano_identity_refs:
            all_identity_refs.extend(char.nano_identity_refs)

    # Collect scene data before releasing DB
    scene_data_list = [
        {
            "scene_id": s.id,
            "project_id": req.project_id,
            "dialogue_text": s.dialogue_text,
            "prompt_visual": s.prompt_visual,
            "sfx_text": s.sfx_text,
        }
        for s in scenes
    ]

    # Update scenes to GENERATING
    for s in scenes:
        s.status = SceneStatus.GENERATING.value

    # Only set project status to PRODUCTION if it's currently STORYBOARD (legacy).
    # Don't downgrade IN_PRODUCTION to PRODUCTION.
    if project.status == ProjectStatus.STORYBOARD.value:
        project.status = ProjectStatus.PRODUCTION.value

    # Advance episode status from STORYBOARD -> PRODUCTION
    if episode and episode.status == EpisodeStatus.STORYBOARD.value:
        episode.status = EpisodeStatus.PRODUCTION.value

    await db.flush()

    # Dispatch Celery tasks (after DB is released by endpoint return)
    from app.tasks.asset_tasks import generate_scene_audio, generate_scene_image

    task_ids = []
    for sd in scene_data_list:
        # TTS task
        if sd["dialogue_text"]:
            audio_task = generate_scene_audio.delay(
                sd["scene_id"], sd["project_id"], sd["dialogue_text"]
            )
            task_ids.append({"scene_id": sd["scene_id"], "task": "audio", "task_id": audio_task.id})

        # Image task
        if sd["prompt_visual"]:
            img_task = generate_scene_image.delay(
                sd["scene_id"],
                sd["project_id"],
                sd["prompt_visual"],
                sd["sfx_text"],
                all_identity_refs if all_identity_refs else None,
            )
            task_ids.append({"scene_id": sd["scene_id"], "task": "image", "task_id": img_task.id})

    return {"dispatched": len(task_ids), "tasks": task_ids}


@router.post("/regenerate-image")
async def regenerate_scene_image(
    req: GenerateSceneImageRequest, db: AsyncSession = Depends(get_db)
):
    """Regenerate image for a single scene (redraw button)."""
    scene = await db.get(Scene, req.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if not scene.prompt_visual:
        raise HTTPException(status_code=400, detail="Scene has no visual prompt")

    # Get identity refs
    char_result = await db.execute(
        select(Character).where(Character.project_id == scene.project_id)
    )
    characters = char_result.scalars().all()
    identity_refs = []
    for char in characters:
        if char.nano_identity_refs:
            identity_refs.extend(char.nano_identity_refs)

    scene_data = {
        "scene_id": scene.id,
        "project_id": scene.project_id,
        "prompt_visual": scene.prompt_visual,
        "sfx_text": scene.sfx_text,
    }

    scene.status = SceneStatus.GENERATING.value
    await db.flush()

    from app.tasks.asset_tasks import generate_scene_image

    task = generate_scene_image.delay(
        scene_data["scene_id"],
        scene_data["project_id"],
        scene_data["prompt_visual"],
        scene_data["sfx_text"],
        identity_refs if identity_refs else None,
    )

    return {"scene_id": scene.id, "task_id": task.id}


@router.post("/approve-scene")
async def approve_scene_and_generate_video(
    req: ApproveSceneRequest, db: AsyncSession = Depends(get_db)
):
    """Human approves a scene's image and triggers video generation.

    This is the CRITICAL Human-in-the-Loop gate.
    Only after explicit approval does the expensive video generation start.
    """
    scene = await db.get(Scene, req.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if scene.status != SceneStatus.REVIEW.value:
        raise HTTPException(
            status_code=400,
            detail=f"Scene must be in REVIEW status (current: {scene.status})",
        )

    if not scene.local_image_path:
        raise HTTPException(status_code=400, detail="Scene has no generated image")

    scene_data = {
        "scene_id": scene.id,
        "project_id": scene.project_id,
        "prompt_motion": scene.prompt_motion or "",
        "local_image_path": scene.local_image_path,
        "local_audio_path": scene.local_audio_path,
    }

    # BUG-7 FIX: Warn (but don't block) if audio not yet generated
    audio_warning = None
    if scene.dialogue_text and not scene.local_audio_path:
        audio_warning = (
            "Audio not yet generated for this scene. "
            "Video will be created without dialogue audio."
        )

    scene.status = SceneStatus.APPROVED.value
    await db.flush()

    from app.tasks.asset_tasks import generate_scene_video

    task = generate_scene_video.delay(
        scene_data["scene_id"],
        scene_data["project_id"],
        scene_data["prompt_motion"],
        scene_data["local_image_path"],
        scene_data["local_audio_path"],
    )

    result = {"scene_id": scene.id, "task_id": task.id, "status": "video_generation_started"}
    if audio_warning:
        result["warning"] = audio_warning

    return result


@router.post("/compose-final")
async def compose_final_video(
    req: ComposeVideoRequest, db: AsyncSession = Depends(get_db)
):
    """Trigger final video composition when all scenes are READY.

    Transitions project to COMPOSING.
    """
    project = await db.get(Project, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate episode if provided
    episode = None
    if req.episode_id:
        episode = await db.get(Episode, req.episode_id)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")

    # Check all scenes are READY (filtered by episode if provided)
    scene_query = select(Scene).where(Scene.project_id == req.project_id)
    if req.episode_id:
        scene_query = scene_query.where(Scene.episode_id == req.episode_id)
    result = await db.execute(scene_query)
    scenes = result.scalars().all()

    if not scenes:
        raise HTTPException(status_code=400, detail="No scenes found")

    not_ready = [s for s in scenes if s.status != SceneStatus.READY.value]
    if not_ready:
        raise HTTPException(
            status_code=400,
            detail=f"{len(not_ready)} scenes are not READY yet",
        )

    # Only set project status to COMPOSING if it's currently PRODUCTION (legacy).
    if project.status == ProjectStatus.PRODUCTION.value:
        project.status = ProjectStatus.COMPOSING.value

    # Advance episode status from PRODUCTION -> COMPOSING
    if episode and episode.status == EpisodeStatus.PRODUCTION.value:
        episode.status = EpisodeStatus.COMPOSING.value

    await db.flush()

    from app.tasks.compose_task import compose_project_video

    task = compose_project_video.delay(req.project_id, episode_id=req.episode_id)

    return {"project_id": req.project_id, "task_id": task.id, "status": "composition_started"}


class BatchApproveRequest(BaseModel):
    scene_ids: list[str]


@router.post("/batch-approve")
async def batch_approve(req: BatchApproveRequest, db: AsyncSession = Depends(get_db)):
    """Approve multiple scenes at once and trigger video generation for each.

    Only scenes in REVIEW status with an existing image will be approved.
    """
    # Batch-fetch all requested scenes in one query
    result = await db.execute(
        select(Scene).where(Scene.id.in_(req.scene_ids))
    )
    all_scenes = {s.id: s for s in result.scalars().all()}

    # First pass: approve eligible scenes and collect dispatch data
    approved_dispatch: list[dict] = []
    for scene_id in req.scene_ids:
        scene = all_scenes.get(scene_id)
        if not scene or scene.status != SceneStatus.REVIEW.value:
            continue
        if not scene.local_image_path:
            continue

        scene.status = SceneStatus.APPROVED.value
        approved_dispatch.append({
            "scene_id": scene.id,
            "project_id": scene.project_id,
            "prompt_motion": scene.prompt_motion or "",
            "local_image_path": scene.local_image_path or "",
            "local_audio_path": scene.local_audio_path,
        })

    await db.flush()

    # Dispatch video generation for approved scenes
    from app.tasks.asset_tasks import generate_scene_video

    tasks = []
    for sd in approved_dispatch:
        task = generate_scene_video.delay(
            sd["scene_id"],
            sd["project_id"],
            sd["prompt_motion"],
            sd["local_image_path"],
            sd["local_audio_path"],
        )
        tasks.append({"scene_id": sd["scene_id"], "task_id": task.id})

    return {"approved": len(approved_dispatch), "video_tasks": tasks}

