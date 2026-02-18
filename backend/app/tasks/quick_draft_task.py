from __future__ import annotations
"""Quick Draft Celery task — runs the full AI pipeline in one shot.

Bypasses human review, uses fast/low-quality settings, and pushes
progress updates via Redis Pub/Sub.
"""

import json
import logging
import os

from celery import shared_task

from app.config import get_settings
from app.models.project import ProjectMode, ProjectStatus
from app.models.scene import SceneStatus
from app.tasks import run_async

logger = logging.getLogger(__name__)
settings = get_settings()

STEPS = [
    ("outline", "生成大纲"),
    ("script", "撰写剧本"),
    ("parse_scenes", "解析分镜"),
    ("tts", "合成语音"),
    ("image_gen", "绘制画面"),
    ("video_gen", "生成动画"),
    ("compose", "合成成片"),
]


@shared_task(bind=True, time_limit=1800, max_retries=0)
def run_quick_draft(self, project_id: str, logline: str, style: str = "default"):
    """Run the full comic drama pipeline in a single Celery task.

    Progress is pushed via Redis Pub/Sub for real-time frontend updates.
    """
    from app.services.pubsub import publish_project_update

    try:
        _publish_progress(project_id, "outline", 1, len(STEPS), "正在生成故事大纲...")

        # Step 1: Generate outline
        from app.services.ai_writer import generate_outline
        outline = run_async(generate_outline(logline, style=style))
        run_async(_update_project_fields(project_id, world_outline=outline,
                                          status=ProjectStatus.OUTLINE_REVIEW.value))

        # Step 2: Generate script
        _publish_progress(project_id, "script", 2, len(STEPS), "正在撰写完整剧本...")
        from app.services.ai_writer import generate_script
        script = run_async(generate_script(outline))
        run_async(_update_project_fields(project_id, full_script=script,
                                          status=ProjectStatus.SCRIPT_REVIEW.value))

        # Step 3: Parse scenes
        _publish_progress(project_id, "parse_scenes", 3, len(STEPS), "正在解析分镜...")
        from app.services.ai_writer import parse_scenes
        scenes_data = run_async(parse_scenes(script))
        scene_ids = run_async(_create_scenes(project_id, scenes_data))
        run_async(_update_project_fields(project_id, status=ProjectStatus.STORYBOARD.value))
        total_scenes = len(scene_ids)

        # Step 4: TTS for all scenes
        _publish_progress(project_id, "tts", 4, len(STEPS),
                          f"正在为 {total_scenes} 个场景合成语音...")
        run_async(_update_project_fields(project_id, status=ProjectStatus.PRODUCTION.value))
        for i, (sid, dialogue) in enumerate(scene_ids):
            if dialogue:
                _publish_progress(project_id, "tts", 4, len(STEPS),
                                  f"语音合成 {i+1}/{total_scenes}...")
                try:
                    from app.services.tts_service import synthesize_speech
                    audio_path, audio_duration = run_async(synthesize_speech(dialogue, project_id, sid))
                    run_async(_update_scene_field(sid, "local_audio_path", audio_path))
                    run_async(_update_scene_field(sid, "audio_duration", audio_duration))
                except Exception as e:
                    logger.warning("TTS failed for scene %s: %s", sid, e)

        # Step 5: Image generation
        _publish_progress(project_id, "image_gen", 5, len(STEPS),
                          f"正在为 {total_scenes} 个场景绘制画面...")
        for i, (sid, _) in enumerate(scene_ids):
            _publish_progress(project_id, "image_gen", 5, len(STEPS),
                              f"图片生成 {i+1}/{total_scenes}...")
            try:
                prompt_visual = run_async(_get_scene_field(sid, "prompt_visual"))
                sfx_text = run_async(_get_scene_field(sid, "sfx_text"))
                if prompt_visual:
                    from app.services.image_gen import generate_image
                    img_path = run_async(generate_image(prompt_visual, project_id, sid, sfx_text))
                    run_async(_update_scene_field(sid, "local_image_path", img_path))
                    run_async(_update_scene_field(sid, "status", SceneStatus.APPROVED.value))
            except Exception as e:
                logger.warning("Image gen failed for scene %s: %s", sid, e)

        # Step 6: Video generation (use FFmpeg fallback for speed in draft mode)
        _publish_progress(project_id, "video_gen", 6, len(STEPS),
                          f"正在为 {total_scenes} 个场景生成动画...")
        for i, (sid, _) in enumerate(scene_ids):
            _publish_progress(project_id, "video_gen", 6, len(STEPS),
                              f"视频生成 {i+1}/{total_scenes}...")
            try:
                img_path = run_async(_get_scene_field(sid, "local_image_path"))
                audio_path = run_async(_get_scene_field(sid, "local_audio_path"))
                motion_prompt = run_async(_get_scene_field(sid, "prompt_motion")) or ""
                if img_path:
                    from app.services.video_gen import generate_video
                    vid_path = run_async(generate_video(
                        motion_prompt, project_id, sid, img_path, audio_path
                    ))
                    run_async(_update_scene_field(sid, "local_video_path", vid_path))
                    run_async(_update_scene_field(sid, "status", SceneStatus.READY.value))
            except Exception as e:
                logger.warning("Video gen failed for scene %s: %s", sid, e)

        # Step 7: Compose final video
        _publish_progress(project_id, "compose", 7, len(STEPS), "正在合成最终视频...")
        video_paths = run_async(_get_ready_scene_videos(project_id))
        if video_paths:
            from app.services.ffmpeg_service import compose_final_video
            run_async(_update_project_fields(project_id, status=ProjectStatus.COMPOSING.value))
            output_path = compose_final_video(project_id, video_paths)
            run_async(_update_project_fields(
                project_id,
                status=ProjectStatus.COMPLETED.value,
                final_video_path=output_path,
            ))
            _publish_progress(project_id, "done", len(STEPS), len(STEPS), "预览完成!")
            publish_project_update(project_id, ProjectStatus.COMPLETED.value)
            return {"project_id": project_id, "status": "completed"}
        else:
            # No videos were generated — stay in PRODUCTION, don't claim COMPLETED
            logger.warning("Quick draft: no videos generated for project %s, staying in PRODUCTION", project_id)
            _publish_progress(project_id, "partial_done", len(STEPS), len(STEPS),
                              "素材生成完成，但视频生成失败。请在看板中手动重试。")
            publish_project_update(project_id, ProjectStatus.PRODUCTION.value)
            return {"project_id": project_id, "status": "partial"}

    except Exception as exc:
        logger.error("Quick draft failed for project %s: %s", project_id, exc, exc_info=True)
        _publish_progress(project_id, "error", 0, len(STEPS), f"生成失败: {str(exc)[:200]}")
        raise


def _publish_progress(project_id: str, step: str, current: int, total: int, desc: str):
    """Publish draft progress via Redis Pub/Sub + update DB."""
    try:
        from app.services.pubsub import _publish_sync
        _publish_sync(project_id, {
            "type": "draft_progress",
            "step": step,
            "current": current,
            "total": total,
            "desc": desc,
        })
        # Also persist to DB for polling fallback
        progress_json = json.dumps({"step": step, "current": current, "total": total, "desc": desc})
        run_async(_update_project_fields(project_id, draft_progress=progress_json))
    except Exception:
        pass


async def _update_project_fields(project_id: str, **fields):
    """Update multiple fields on a project."""
    from sqlalchemy import update
    from app.database import async_session_factory
    from app.models.project import Project

    async with async_session_factory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(**fields)
        )
        await session.commit()


async def _create_scenes(project_id: str, scenes_data: list[dict]) -> list[tuple[str, str]]:
    """Create scene records from parsed scene data. Returns [(scene_id, dialogue_text)]."""
    import uuid
    from app.database import async_session_factory
    from app.models.scene import Scene

    result = []
    async with async_session_factory() as session:
        for sd in scenes_data:
            scene = Scene(
                id=uuid.uuid4().hex[:36],
                project_id=project_id,
                sequence_order=sd.get("sequence_order", 0),
                dialogue_text=sd.get("dialogue_text"),
                prompt_visual=sd.get("prompt_visual"),
                prompt_motion=sd.get("prompt_motion"),
                sfx_text=sd.get("sfx_text"),
                status=SceneStatus.PENDING.value,
            )
            session.add(scene)
            result.append((scene.id, sd.get("dialogue_text", "")))
        await session.commit()
    return result


async def _update_scene_field(scene_id: str, field: str, value):
    """Update a single field on a scene."""
    from sqlalchemy import update
    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        await session.execute(
            update(Scene).where(Scene.id == scene_id).values(**{field: value})
        )
        await session.commit()


async def _get_scene_field(scene_id: str, field: str):
    """Get a single field from a scene."""
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        result = await session.execute(
            select(getattr(Scene, field)).where(Scene.id == scene_id)
        )
        return result.scalar()


async def _get_ready_scene_videos(project_id: str) -> list[str]:
    """Get video paths for all READY scenes in order."""
    from sqlalchemy import select
    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        result = await session.execute(
            select(Scene.local_video_path)
            .where(Scene.project_id == project_id, Scene.local_video_path.isnot(None))
            .order_by(Scene.sequence_order)
        )
        return [r[0] for r in result.fetchall()]
