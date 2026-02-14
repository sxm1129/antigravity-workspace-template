from __future__ import annotations
"""Video generation service — uses Volcengine Ark Seedance (I2V).

Async task pattern:
1. POST /contents/generations/tasks → create task
2. GET  /contents/generations/tasks/{id} → poll status
3. Download result video when task completes

Model: doubao-seedance-1-0-lite-i2v-250428
"""

import asyncio
import base64
import logging
import os

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def generate_video(
    prompt_motion: str,
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Generate a video for a scene using Volcengine Seedance I2V.

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
