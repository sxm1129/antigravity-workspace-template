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
def generate_scene_audio(self, scene_id: str, project_id: str, dialogue_text: str, voice: str | None = None):
    """Generate TTS audio for a scene's dialogue."""
    try:
        from app.services.tts_service import synthesize_speech

        rel_path, audio_duration = run_async(
            synthesize_speech(dialogue_text, project_id, scene_id, voice=voice)
        )

        # Update scene in DB with path and duration
        run_async(_update_scene_fields(scene_id, local_audio_path=rel_path, audio_duration=audio_duration))
        logger.info("Audio generated for scene %s: %s (%.2fs)", scene_id, rel_path, audio_duration)

        # Broadcast via Redis Pub/Sub
        _publish_scene_update(project_id, scene_id, "audio_done")

        return {"scene_id": scene_id, "audio_path": rel_path, "audio_duration": audio_duration}

    except Exception as exc:
        logger.error("Audio generation failed for scene %s: %s", scene_id, exc)
        if self.request.retries >= self.max_retries:
            _mark_scene_error(scene_id, project_id, f"TTS failed: {exc}")
            return {"scene_id": scene_id, "status": "error"}
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

        # Update scene in DB: path + status in one call
        run_async(_update_scene_fields(
            scene_id, local_image_path=rel_path, status=SceneStatus.REVIEW.value,
        ))
        logger.info("Image generated for scene %s: %s", scene_id, rel_path)

        # Broadcast via Redis Pub/Sub
        _publish_scene_update(project_id, scene_id, SceneStatus.REVIEW.value)

        return {"scene_id": scene_id, "image_path": rel_path}

    except Exception as exc:
        logger.error("Image generation failed for scene %s: %s", scene_id, exc)
        if self.request.retries >= self.max_retries:
            _mark_scene_error(scene_id, project_id, f"Image gen failed: {exc}")
            return {"scene_id": scene_id, "status": "error"}
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
    if not redis_client.set(lock_key, "1", ex=900, nx=True):
        logger.warning("Duplicate video request blocked for scene %s", scene_id)
        return {"scene_id": scene_id, "status": "duplicate_blocked"}

    try:
        from app.services.video_gen import generate_video

        run_async(_update_scene_status(scene_id, SceneStatus.VIDEO_GEN.value))

        # Broadcast status change
        _publish_scene_update(project_id, scene_id, SceneStatus.VIDEO_GEN.value)

        rel_path = run_async(
            generate_video(prompt_motion, project_id, scene_id, local_image_path, local_audio_path)
        )

        # Probe video duration from the generated file
        video_dur = _probe_video_duration(project_id, rel_path)

        run_async(_update_scene_fields(scene_id, local_video_path=rel_path, video_duration=video_dur))
        run_async(_update_scene_status(scene_id, SceneStatus.READY.value))
        logger.info("Video generated for scene %s: %s (%.1fs)", scene_id, rel_path, video_dur)

        # Broadcast final status
        _publish_scene_update(project_id, scene_id, SceneStatus.READY.value)

        redis_client.delete(lock_key)  # Release lock on success
        return {"scene_id": scene_id, "video_path": rel_path}

    except Exception as exc:
        logger.error("Video generation failed for scene %s: %s", scene_id, exc)
        if self.request.retries >= self.max_retries:
            _mark_scene_error(scene_id, project_id, f"Video gen failed: {exc}")
            redis_client.delete(lock_key)  # Release lock on final failure
            return {"scene_id": scene_id, "status": "error"}
        # Keep lock held during retry to prevent duplicates
        raise self.retry(exc=exc)


async def _update_scene_fields(scene_id: str, **kwargs) -> None:
    """Update multiple fields on a scene record."""
    from sqlalchemy import update

    from app.database import async_session_factory
    from app.models.scene import Scene

    async with async_session_factory() as session:
        await session.execute(
            update(Scene).where(Scene.id == scene_id).values(**kwargs)
        )
        await session.commit()





async def _update_scene_status(scene_id: str, status: str) -> None:
    """Update scene status."""
    await _update_scene_fields(scene_id, status=status)


def _probe_video_duration(project_id: str, rel_path: str) -> float:
    """Probe video file duration using ffprobe."""
    import subprocess

    full_path = f"{settings.MEDIA_VOLUME}/{rel_path}"
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                full_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return 5.0


def _publish_scene_update(project_id: str, scene_id: str, status: str) -> None:
    """Publish scene status update via Redis Pub/Sub (sync, for Celery workers)."""
    try:
        from app.services.pubsub import publish_scene_update
        publish_scene_update(project_id, scene_id, status)
    except Exception:
        # Best-effort, never fail the task
        pass


def _mark_scene_error(scene_id: str, project_id: str, error_msg: str) -> None:
    """Mark a scene as ERROR with an error message — called on final task failure."""
    try:
        truncated = str(error_msg)[:500]
        run_async(_update_scene_fields(
            scene_id,
            status=SceneStatus.ERROR.value,
            error_message=truncated,
        ))
        _publish_scene_update(project_id, scene_id, SceneStatus.ERROR.value)
        logger.warning("Scene %s marked as ERROR: %s", scene_id, truncated[:100])
    except Exception as err:
        logger.error("Failed to mark scene %s as ERROR: %s", scene_id, err)

