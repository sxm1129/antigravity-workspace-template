from __future__ import annotations
"""Video generation service — uses Volcengine Ark Seedance (I2V).

Async task pattern:
1. POST /contents/generations/tasks → create task
2. GET  /contents/generations/tasks/{id} → poll status
3. Download result video when task completes

Model: doubao-seedance-1-0-lite-i2v-250428

Refactored to extend BaseGenService for unified retry, fallback, and metrics.
"""

import asyncio
import base64
import logging
import os
from typing import Any

import httpx

from app.config import get_settings
from app.services.base_gen_service import BaseGenService, GenServiceConfig

logger = logging.getLogger(__name__)
settings = get_settings()


class VideoGenService(BaseGenService[str]):
    """Video generation service wrapping Volcengine Seedance I2V API.

    Inherits retry, fallback, timeout, and cost tracking from BaseGenService.
    """

    service_name = "video_gen"

    def __init__(self) -> None:
        super().__init__(GenServiceConfig(
            max_retries=1,
            retry_delay=5.0,
            timeout=660.0,  # Seedance tasks can take 10+ min
            fallback_enabled=True,
        ))

    async def _generate(self, **kwargs: Any) -> str:
        """Delegate to core Seedance video generation."""
        return await _generate_video_core(
            prompt_motion=kwargs["prompt_motion"],
            project_id=kwargs["project_id"],
            scene_id=kwargs["scene_id"],
            local_image_path=kwargs["local_image_path"],
            local_audio_path=kwargs.get("local_audio_path"),
        )

    async def _fallback(self, **kwargs: Any) -> str:
        """Fallback to FFmpeg image-to-video with Ken Burns effect."""
        logger.info("video_gen: using FFmpeg fallback for scene=%s", kwargs["scene_id"][:8])
        return _ffmpeg_image_to_video(
            kwargs["project_id"],
            kwargs["scene_id"],
            kwargs["local_image_path"],
            kwargs.get("local_audio_path"),
        )

    def _estimate_cost(self, **kwargs: Any) -> float:
        """Rough cost estimate per video generation call."""
        return 0.10  # ~$0.10 per Seedance I2V call


# Module-level singleton for metrics aggregation
_video_service = VideoGenService()


def get_video_service() -> VideoGenService:
    """Return the singleton VideoGenService for metrics access."""
    return _video_service


async def generate_video(
    prompt_motion: str,
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Public API — delegates to VideoGenService for retry/fallback/metrics.

    Backward-compatible with existing callers.
    """
    result = await _video_service.execute(
        prompt_motion=prompt_motion,
        project_id=project_id,
        scene_id=scene_id,
        local_image_path=local_image_path,
        local_audio_path=local_audio_path,
    )
    return result.data


async def _generate_video_core(
    prompt_motion: str,
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Core video generation via Volcengine Seedance I2V.

    Args:
        prompt_motion: Motion description prompt.
        project_id: Project ID for directory organization.
        scene_id: Scene ID for file naming.
        local_image_path: Relative path to the base image in media_volume.
        local_audio_path: Relative path to the audio in media_volume (optional).

    Returns:
        Relative path to the generated video in media_volume.
    """
    if settings.USE_MOCK_API:
        return _mock_video(project_id, scene_id)

    # Fallback to FFmpeg I2V if no ARK_API_KEY
    if not settings.ARK_API_KEY:
        logger.warning("No ARK_API_KEY set, using FFmpeg image-to-video fallback")
        return _ffmpeg_image_to_video(project_id, scene_id, local_image_path, local_audio_path)

    # Read local image as Base64 for URL embedding
    image_full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    with open(image_full_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    image_data_url = f"data:image/png;base64,{image_b64}"

    # Build Seedance task creation payload
    # Format: text prompt with generation params + reference image
    prompt_text = (
        f"{prompt_motion}  "
        f"--resolution 720p  --duration 5 --camerafixed false --watermark true"
    )

    payload = {
        "model": settings.ARK_VIDEO_MODEL,
        "content": [
            {
                "type": "text",
                "text": prompt_text,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data_url,
                },
            },
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.ARK_API_KEY}",
    }

    task_url = f"{settings.ARK_ENDPOINT}/contents/generations/tasks"

    logger.info("Creating Seedance task for scene=%s", scene_id[:8])

    # Step 1: Create task
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(task_url, headers=headers, json=payload)
        response.raise_for_status()

    task_data = response.json()
    task_id = task_data.get("id") or task_data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Seedance API returned no task ID: {task_data}")

    logger.info("Seedance task created: %s", task_id)

    # Step 2: Poll for completion
    poll_url = f"{task_url}/{task_id}"
    video_url = await _poll_task(poll_url, headers, timeout_seconds=600)

    # Step 3: Download video
    rel_path = await _download_video(video_url, project_id, scene_id)
    logger.info("Video saved: %s", rel_path)
    return rel_path


async def _poll_task(
    poll_url: str,
    headers: dict,
    timeout_seconds: int = 600,
    interval_seconds: int = 10,
) -> str:
    """Poll Volcengine task status until completion.

    Returns the video URL when task succeeds.
    Raises RuntimeError on timeout or failure.
    """
    elapsed = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout_seconds:
            await asyncio.sleep(interval_seconds)
            elapsed += interval_seconds

            response = await client.get(poll_url, headers=headers)
            response.raise_for_status()

            data = response.json()
            status = data.get("status", "").lower()

            logger.info("Seedance task poll: status=%s elapsed=%ds", status, elapsed)

            if status in ("succeeded", "completed", "success"):
                # Extract video URL from result
                output = data.get("output", {})
                video_url = (
                    output.get("video_url")
                    or output.get("url")
                    or data.get("video_url")
                )
                if not video_url:
                    # Try content array format
                    content = output.get("content", [])
                    for item in content:
                        if item.get("type") == "video_url":
                            video_url = item.get("video_url", {}).get("url")
                            break

                if not video_url:
                    raise RuntimeError(f"Task succeeded but no video URL found: {data}")

                return video_url

            elif status in ("failed", "error", "cancelled"):
                error_msg = data.get("error", {}).get("message", "Unknown error")
                raise RuntimeError(f"Seedance task failed: {error_msg}")

    raise RuntimeError(f"Seedance task timed out after {timeout_seconds}s")


async def _download_video(url: str, project_id: str, scene_id: str) -> str:
    """Download video from URL, stream to disk."""
    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "videos")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.mp4"
    filepath = os.path.join(dir_path, filename)

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(filepath, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)

    return f"{project_id}/videos/{filename}"


def _mock_video(project_id: str, scene_id: str) -> str:
    """Generate a mock video file (5-second color bars via FFmpeg or fallback)."""
    import subprocess

    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "videos")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.mp4"
    filepath = os.path.join(dir_path, filename)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i",
                "color=c=0x23233C:size=1920x1080:duration=5:rate=24",
                "-f", "lavfi", "-i",
                "anullsrc=r=24000:cl=mono",
                "-t", "5",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-shortest",
                filepath,
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        with open(filepath, "wb") as f:
            f.write(b"\x00" * 1024)
        logger.warning("FFmpeg not available, wrote placeholder MP4")

    return f"{project_id}/videos/{filename}"


def _ffmpeg_image_to_video(
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Create a video from an image using FFmpeg with Ken Burns zoom effect.

    Generates a 5-second 720p video with a slow zoom-in effect from the image.
    Optionally overlays audio if available.
    """
    import subprocess

    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "videos")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.mp4"
    filepath = os.path.join(dir_path, filename)

    image_full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    if not os.path.exists(image_full_path):
        logger.error("Image not found for video gen: %s", image_full_path)
        return _mock_video(project_id, scene_id)

    # Ken Burns zoom: slowly zoom from 100% to 110% over 5 seconds
    zoom_filter = (
        "scale=8000:-1,"
        "zoompan=z='min(zoom+0.002,1.1)':d=120:x='iw/2-(iw/zoom/2)'"
        ":y='ih/2-(ih/zoom/2)':s=1280x720:fps=24,"
        "setpts=PTS-STARTPTS"
    )

    # Build base command
    if local_audio_path:
        audio_full = os.path.join(settings.MEDIA_VOLUME, local_audio_path)
        if os.path.exists(audio_full):
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", image_full_path,
                "-i", audio_full,
                "-vf", zoom_filter,
                "-t", "5",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p", "-shortest",
                filepath,
            ]
        else:
            local_audio_path = None

    if not local_audio_path:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_full_path,
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-vf", zoom_filter,
            "-t", "5",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-shortest",
            filepath,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error("FFmpeg I2V failed: %s", result.stderr[-500:])
            return _mock_video(project_id, scene_id)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("FFmpeg I2V error, falling back to mock")
        return _mock_video(project_id, scene_id)

    logger.info("FFmpeg I2V video created: %s", filepath)
    return f"{project_id}/videos/{filename}"
