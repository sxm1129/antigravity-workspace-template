from __future__ import annotations
"""Celery tasks for asset generation (TTS, image, video).

Each task:
1. Reads data from DB
2. Releases DB connection
3. Calls external API
4. Opens new connection to write results
5. Publishes status update via Redis Pub/Sub
"""

import logging

from celery import shared_task

from app.config import get_settings
from app.models.scene import SceneStatus
from app.tasks import run_async

logger = logging.getLogger(__name__)
settings = get_settings()


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def generate_scene_audio(self, scene_id: str, project_id: str, dialogue_text: str):
    """Generate TTS audio for a scene's dialogue."""
    try:
        from app.services.tts_service import synthesize_speech

        rel_path = run_async(
            synthesize_speech(dialogue_text, project_id, scene_id)
        )

        # Update scene in DB
        run_async(_update_scene_path(scene_id, "local_audio_path", rel_path))
        logger.info("Audio generated for scene %s: %s", scene_id, rel_path)

        # Broadcast via Redis Pub/Sub
        _publish_scene_update(project_id, scene_id, "audio_done")

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
    """Generate an image for a scene."""
    try:
        from app.services.image_gen import generate_image

        rel_path = run_async(
            generate_image(prompt_visual, project_id, scene_id, sfx_text, identity_refs)
        )

        # Update scene in DB and set status to REVIEW
        run_async(_update_scene_path(scene_id, "local_image_path", rel_path))
        run_async(_update_scene_status(scene_id, SceneStatus.REVIEW.value))
        logger.info("Image generated for scene %s: %s", scene_id, rel_path)

        # Broadcast via Redis Pub/Sub
        _publish_scene_update(project_id, scene_id, SceneStatus.REVIEW.value)

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
    """Generate a video for a scene.

    Includes Redis mutex lock to prevent duplicate expensive requests.
    Lock is released on both success and failure.
    """
    import redis
    from app.services.pubsub import _get_sync_pool

    lock_key = f"seedance_lock:{scene_id}"
    redis_client = redis.Redis(connection_pool=_get_sync_pool())

    # Anti-duplicate: SETNX mutex
    if not redis_client.set(lock_key, "1", ex=600, nx=True):
        logger.warning("Duplicate video request blocked for scene %s", scene_id)
        return {"scene_id": scene_id, "status": "duplicate_blocked"}

    succeeded = False
    try:
        from app.services.video_gen import generate_video

        run_async(_update_scene_status(scene_id, SceneStatus.VIDEO_GEN.value))

        # Broadcast status change
        _publish_scene_update(project_id, scene_id, SceneStatus.VIDEO_GEN.value)

        rel_path = run_async(
            generate_video(prompt_motion, project_id, scene_id, local_image_path, local_audio_path)
        )

        run_async(_update_scene_path(scene_id, "local_video_path", rel_path))
        run_async(_update_scene_status(scene_id, SceneStatus.READY.value))
        logger.info("Video generated for scene %s: %s", scene_id, rel_path)

        # Broadcast final status
        _publish_scene_update(project_id, scene_id, SceneStatus.READY.value)
        succeeded = True

        return {"scene_id": scene_id, "video_path": rel_path}

    except Exception as exc:
        logger.error("Video generation failed for scene %s: %s", scene_id, exc)
        raise self.retry(exc=exc)
    finally:
        # Always release lock — on success or before retry
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


def _publish_scene_update(project_id: str, scene_id: str, status: str) -> None:
    """Publish scene status update via Redis Pub/Sub (sync, for Celery workers)."""
    try:
        from app.services.pubsub import publish_scene_update
        publish_scene_update(project_id, scene_id, status)
    except Exception:
        # Best-effort, never fail the task
        pass
