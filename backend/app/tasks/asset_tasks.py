from __future__ import annotations
"""Celery tasks for asset generation (TTS, image, video).

Each task:
1. Reads data from DB
2. Releases DB connection
3. Calls external API
4. Opens new connection to write results
"""

import asyncio
import logging

from celery import shared_task

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _run_async(coro):
    """Helper to run async code in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_scene_audio(self, scene_id: str, project_id: str, dialogue_text: str):
    """Generate TTS audio for a scene's dialogue."""
    try:
        from app.services.tts_service import synthesize_speech

        rel_path = _run_async(
            synthesize_speech(dialogue_text, project_id, scene_id)
        )

        # Update scene in DB
        _run_async(_update_scene_path(scene_id, "local_audio_path", rel_path))
        logger.info("Audio generated for scene %s: %s", scene_id, rel_path)
        return {"scene_id": scene_id, "audio_path": rel_path}

    except Exception as exc:
        logger.error("Audio generation failed for scene %s: %s", scene_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def generate_scene_image(
    self,
    scene_id: str,
    project_id: str,
    prompt_visual: str,
    sfx_text: str | None = None,
    identity_refs: list[str] | None = None,
):
    """Generate an image for a scene using Nano Banana Pro."""
    try:
        from app.services.image_gen import generate_image

        rel_path = _run_async(
            generate_image(prompt_visual, project_id, scene_id, sfx_text, identity_refs)
        )

        # Update scene in DB and set status to WAITING_HUMAN_APPROVAL
        _run_async(_update_scene_path(scene_id, "local_image_path", rel_path))
        _run_async(_update_scene_status(scene_id, "WAITING_HUMAN_APPROVAL"))
        logger.info("Image generated for scene %s: %s", scene_id, rel_path)
        return {"scene_id": scene_id, "image_path": rel_path}

    except Exception as exc:
        logger.error("Image generation failed for scene %s: %s", scene_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, default_retry_delay=120)
def generate_scene_video(
    self,
    scene_id: str,
    project_id: str,
    prompt_motion: str,
    local_image_path: str,
    local_audio_path: str | None = None,
):
    """Generate a video for a scene using Seedance 2.0.

    Includes Redis mutex lock to prevent duplicate expensive requests.
    """
    import redis

    lock_key = f"seedance_lock:{scene_id}"
    redis_client = redis.Redis.from_url(settings.REDIS_URL)

    # Anti-duplicate: SETNX mutex
    if not redis_client.set(lock_key, "1", ex=600, nx=True):
        logger.warning("Duplicate video request blocked for scene %s", scene_id)
        return {"scene_id": scene_id, "status": "duplicate_blocked"}

    try:
        from app.services.video_gen import generate_video

        _run_async(_update_scene_status(scene_id, "VIDEO_GENERATING"))

        rel_path = _run_async(
            generate_video(prompt_motion, project_id, scene_id, local_image_path, local_audio_path)
        )

        _run_async(_update_scene_path(scene_id, "local_video_path", rel_path))
        _run_async(_update_scene_status(scene_id, "READY"))
        logger.info("Video generated for scene %s: %s", scene_id, rel_path)
        return {"scene_id": scene_id, "video_path": rel_path}

    except Exception as exc:
        logger.error("Video generation failed for scene %s: %s", scene_id, exc)
        raise self.retry(exc=exc)
    finally:
        redis_client.delete(lock_key)


async def _update_scene_path(scene_id: str, field: str, value: str) -> None:
    """Update a single field on a scene record."""
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        await session.execute(
            update(Scene).where(Scene.id == scene_id).values(**{field: value})
        )
        await session.commit()


async def _update_scene_status(scene_id: str, status: str) -> None:
    """Update scene status."""
    await _update_scene_path(scene_id, "status", status)
