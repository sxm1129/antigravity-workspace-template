from __future__ import annotations
"""Video generation service — multi-provider support.

Supports providers (in priority order from VIDEO_PROVIDERS env):
  seedance (Volcengine Ark), kling, vidu, wan (DashScope), gemini (Veo),
  sora (RunningHub), remotion, ffmpeg.

Each AI provider follows: POST create → poll status → download.
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
from app.services.providers import kling_video, vidu_video, wan_video, gemini_video, sora_video

logger = logging.getLogger(__name__)
settings = get_settings()

# Module-level httpx client for connection reuse (lazy init)
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """Return a module-level httpx.AsyncClient, creating it on first use."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=60.0)
    return _http_client


class VideoGenService(BaseGenService[str]):
    """Multi-provider video generation service.

    Routes to providers based on VIDEO_PROVIDERS priority list.
    Inherits retry, fallback, timeout, and cost tracking from BaseGenService.
    """

    service_name = "video_gen"

    def __init__(self) -> None:
        super().__init__(GenServiceConfig(
            max_retries=1,
            retry_delay=5.0,
            timeout=660.0,  # AI video tasks can take 10+ min
            fallback_enabled=True,
        ))

    def _get_provider_chain(self) -> list[str]:
        """Parse VIDEO_PROVIDERS into ordered list."""
        return [p.strip() for p in settings.VIDEO_PROVIDERS.split(",") if p.strip()]

    async def _generate(self, **kwargs: Any) -> str:
        """Try primary provider from VIDEO_PROVIDERS chain."""
        if settings.USE_MOCK_API:
            return _mock_video(kwargs["project_id"], kwargs["scene_id"])

        providers = self._get_provider_chain()
        if not providers:
            raise RuntimeError("No video providers configured")

        primary = providers[0]
        return await self._dispatch_provider(primary, **kwargs)

    async def _fallback(self, **kwargs: Any) -> str:
        """Try remaining providers in VIDEO_PROVIDERS chain."""
        providers = self._get_provider_chain()
        scene_id = kwargs.get("scene_id", "unknown")

        # Skip the first provider (already tried in _generate)
        for provider in providers[1:]:
            logger.info(
                "video_gen fallback: trying %s for scene=%s",
                provider, scene_id[:8],
            )
            try:
                return await self._dispatch_provider(provider, **kwargs)
            except Exception as exc:
                logger.warning("%s fallback failed: %s", provider, exc)

        raise RuntimeError("All video providers exhausted")

    async def _dispatch_provider(self, provider: str, **kwargs: Any) -> str:
        """Route to the correct provider implementation."""
        prompt_motion = kwargs.get("prompt_motion", "")
        project_id = kwargs["project_id"]
        scene_id = kwargs["scene_id"]
        local_image_path = kwargs["local_image_path"]
        local_audio_path = kwargs.get("local_audio_path")

        if provider == "seedance":
            return await _generate_video_core(
                prompt_motion=prompt_motion,
                project_id=project_id,
                scene_id=scene_id,
                local_image_path=local_image_path,
                local_audio_path=local_audio_path,
            )

        elif provider == "kling":
            if not settings.KLING_API_KEY:
                raise RuntimeError("KLING_API_KEY not configured")
            image_b64 = _read_image_as_base64(local_image_path)
            result = await kling_video.generate_video(
                prompt=prompt_motion,
                model=settings.KLING_VIDEO_MODEL,
                api_key=settings.KLING_API_KEY,
                base_url=settings.KLING_API_BASE or None,
                image_base64=[image_b64] if image_b64 else None,
                http_client=_get_http_client(),
            )
            return await _download_video(result["video_url"], project_id, scene_id)

        elif provider == "vidu":
            if not settings.VIDU_API_KEY:
                raise RuntimeError("VIDU_API_KEY not configured")
            image_b64 = _read_image_as_base64(local_image_path)
            result = await vidu_video.generate_video(
                prompt=prompt_motion,
                model=settings.VIDU_VIDEO_MODEL,
                api_key=settings.VIDU_API_KEY,
                base_url=settings.VIDU_API_BASE or None,
                image_base64=[image_b64] if image_b64 else None,
                http_client=_get_http_client(),
            )
            return await _download_video(result["video_url"], project_id, scene_id)

        elif provider == "wan":
            if not settings.DASHSCOPE_API_KEY:
                raise RuntimeError("DASHSCOPE_API_KEY not configured")
            return await _dashscope_image_to_video(
                prompt_motion, project_id, scene_id,
                local_image_path, local_audio_path,
            )

        elif provider == "gemini":
            api_key = settings.GEMINI_VIDEO_API_KEY or settings.GEMINI_API_KEY
            if not api_key:
                raise RuntimeError("GEMINI_VIDEO_API_KEY not configured")
            image_b64 = _read_image_as_base64(local_image_path)
            result = await gemini_video.generate_video(
                prompt=prompt_motion,
                model=settings.GEMINI_VIDEO_MODEL,
                api_key=api_key,
                image_base64=[image_b64] if image_b64 else None,
                http_client=_get_http_client(),
            )
            if "video_url" in result:
                return await _download_video(result["video_url"], project_id, scene_id)
            elif "video_data" in result:
                return _save_video_data(
                    result["video_data"], project_id, scene_id,
                    result.get("mime_type", "video/mp4"),
                )
            raise RuntimeError("Gemini Veo: no video in result")

        elif provider == "sora":
            if not settings.SORA_API_KEY or not settings.SORA_API_BASE:
                raise RuntimeError("SORA_API_KEY/SORA_API_BASE not configured")
            image_b64 = _read_image_as_base64(local_image_path)
            result = await sora_video.generate_video(
                prompt=prompt_motion,
                model=settings.SORA_VIDEO_MODEL,
                api_key=settings.SORA_API_KEY,
                base_url=settings.SORA_API_BASE,
                image_base64=[image_b64] if image_b64 else None,
                http_client=_get_http_client(),
            )
            return await _download_video(result["video_url"], project_id, scene_id)

        elif provider == "remotion":
            return _remotion_image_to_video(
                project_id, scene_id, local_image_path,
                local_audio_path, prompt_motion,
            )

        elif provider == "ffmpeg":
            return _ffmpeg_image_to_video(
                project_id, scene_id, local_image_path, local_audio_path,
            )

        else:
            raise RuntimeError(f"Unknown video provider: {provider}")

    def _estimate_cost(self, **kwargs: Any) -> float:
        """Rough cost estimate per video generation call."""
        return 0.10


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


def _read_image_as_base64(local_image_path: str) -> str | None:
    """Read a local image from media_volume and return as data URL base64."""
    if not local_image_path:
        logger.warning("_read_image_as_base64: empty image path")
        return None
    image_full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    if not os.path.exists(image_full_path):
        logger.warning("_read_image_as_base64: file not found: %s", image_full_path)
        return None
    with open(image_full_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/png;base64,{image_b64}"


def _save_video_data(
    video_b64: str,
    project_id: str,
    scene_id: str,
    mime_type: str = "video/mp4",
) -> str:
    """Save base64-encoded video data to disk."""
    import base64 as b64_mod

    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "videos")
    os.makedirs(dir_path, exist_ok=True)

    ext = "mp4" if "mp4" in mime_type else "webm"
    filename = f"{scene_id}.{ext}"
    filepath = os.path.join(dir_path, filename)

    video_bytes = b64_mod.b64decode(video_b64)
    with open(filepath, "wb") as f:
        f.write(video_bytes)

    logger.info("Saved video data: %s (%d bytes)", filepath, len(video_bytes))
    return f"{project_id}/videos/{filename}"


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
    # When no ARK_API_KEY, raise immediately so BaseGenService routes to _fallback()
    # which iterates through remaining providers in VIDEO_PROVIDERS chain.
    if not settings.ARK_API_KEY:
        raise RuntimeError("ARK_API_KEY not configured — delegating to fallback chain")

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
    client = _get_http_client()
    response = await client.post(task_url, headers=headers, json=payload, timeout=120.0)
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
    client = _get_http_client()
    while elapsed < timeout_seconds:
        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds

        response = await client.get(poll_url, headers=headers, timeout=30.0)
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

    client = _get_http_client()
    async with client.stream("GET", url, timeout=120.0) as response:
        response.raise_for_status()
        with open(filepath, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=8192):
                f.write(chunk)

    return f"{project_id}/videos/{filename}"


# ── DashScope wanx2.1-i2v (Image to Video) ──

async def _dashscope_image_to_video(
    prompt_motion: str,
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Generate video from image using Alibaba DashScope wanx I2V.

    Async task pattern:
    1. POST /services/aigc/image2video/video-synthesis  →  task_id
    2. GET  /tasks/{task_id}  →  poll until COMPLETED
    3. Download result video
    """
    image_full_path = os.path.join(settings.MEDIA_VOLUME, local_image_path)
    with open(image_full_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    image_data_url = f"data:image/png;base64,{image_b64}"

    # Build request payload — i2v uses `image_url`, kf2v uses `first_frame_url`
    payload = {
        "model": settings.DASHSCOPE_VIDEO_MODEL,
        "input": {
            "image_url": image_data_url,
            "prompt": prompt_motion or "缓慢推进，柔和的光线变化，电影质感画面",
        },
        "parameters": {
            "resolution": "720P",
            "prompt_extend": True,
        },
    }

    headers = {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }

    endpoint = settings.DASHSCOPE_ENDPOINT
    create_url = f"{endpoint}/services/aigc/image2video/video-synthesis"

    logger.info(
        "DashScope I2V: creating task for scene=%s model=%s",
        scene_id[:8], settings.DASHSCOPE_VIDEO_MODEL,
    )

    client = _get_http_client()

    # Step 1: Create async task
    resp = await client.post(create_url, json=payload, headers=headers, timeout=60.0)
    resp.raise_for_status()
    result = resp.json()

    task_id = result.get("output", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"DashScope: no task_id in response: {result}")

    logger.info("DashScope I2V: task created task_id=%s", task_id)

    # Step 2: Poll for completion
    poll_url = f"{endpoint}/tasks/{task_id}"
    poll_headers = {"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"}

    timeout_seconds = 300
    interval_seconds = 8
    elapsed = 0

    while elapsed < timeout_seconds:
        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds

        poll_resp = await client.get(poll_url, headers=poll_headers, timeout=30.0)
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()

        task_status = poll_data.get("output", {}).get("task_status", "UNKNOWN")
        logger.debug("DashScope I2V: poll task_id=%s status=%s elapsed=%ds", task_id, task_status, elapsed)

        if task_status == "SUCCEEDED":
            video_url = poll_data.get("output", {}).get("video_url")
            if not video_url:
                raise RuntimeError(f"DashScope: SUCCEEDED but no video_url: {poll_data}")
            logger.info("DashScope I2V: task succeeded, downloading video")
            return await _download_video(video_url, project_id, scene_id)

        if task_status in ("FAILED", "CANCELLED"):
            error_msg = poll_data.get("output", {}).get("message", "Unknown error")
            raise RuntimeError(f"DashScope task {task_status}: {error_msg}")

    raise RuntimeError(f"DashScope I2V: timeout after {timeout_seconds}s for task={task_id}")

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


# ── Motion preset selection ──

_MOTION_KEYWORDS: dict[str, list[str]] = {
    "zoom-in": ["靠近", "特写", "聚焦", "放大", "close", "zoom in", "focus"],
    "zoom-out": ["远景", "全景", "缩小", "拉远", "wide", "zoom out", "pull back"],
    "pan-left": ["向左", "左移", "pan left", "左"],
    "pan-right": ["向右", "右移", "pan right", "右"],
    "drift": ["缓慢", "漂移", "dreamy", "drift", "float", "慢"],
}

_MOTION_PRESETS = ["zoom-in", "zoom-out", "pan-left", "pan-right", "drift"]


def _select_motion_preset(prompt_motion: str, scene_id: str) -> str:
    """Select a motion preset based on prompt_motion keywords or fallback to pseudo-random."""
    prompt_lower = prompt_motion.lower()
    for preset, keywords in _MOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return preset
    # Deterministic pseudo-random based on scene_id hash
    idx = hash(scene_id) % len(_MOTION_PRESETS)
    return _MOTION_PRESETS[idx]


def _remotion_image_to_video(
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
    prompt_motion: str = "",
) -> str:
    """Render a single image to video using Remotion SingleSceneRender composition.

    Produces higher quality output than FFmpeg Ken Burns with:
    - Spring-based Ken Burns with easing
    - Cinematic vignette overlay
    - Film grain texture
    - Smooth fade in/out

    Falls back to FFmpeg if Remotion is not available.
    """
    import json
    import subprocess

    # Resolve paths
    remotion_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", settings.REMOTION_PROJECT_PATH)
    )
    media_volume = os.path.abspath(settings.MEDIA_VOLUME)

    image_full_path = os.path.join(media_volume, local_image_path)
    if not os.path.exists(image_full_path):
        raise FileNotFoundError(f"Image not found: {image_full_path}")

    # Determine duration from audio, default 5s
    duration = 5.0
    audio_src = None
    if local_audio_path:
        audio_full = os.path.join(media_volume, local_audio_path)
        if os.path.exists(audio_full):
            duration = max(_probe_audio_duration(audio_full) + 0.5, 3.0)
            # Audio path relative to Remotion public/media symlink
            audio_src = f"http://localhost:9001/media/{local_audio_path}"

    fps = 24
    duration_frames = int(duration * fps)
    motion_preset = _select_motion_preset(prompt_motion, scene_id)

    # Build props
    props = {
        "imageSrc": f"http://localhost:9001/media/{local_image_path}",
        "durationInFrames": duration_frames,
        "motionPreset": motion_preset,
    }
    if audio_src:
        props["audioSrc"] = audio_src

    # Write props and set output path
    output_dir = os.path.join(media_volume, project_id, "videos")
    os.makedirs(output_dir, exist_ok=True)

    props_path = os.path.join(output_dir, f"{scene_id}_props.json")
    output_path = os.path.join(output_dir, f"{scene_id}.mp4")

    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)

    # Render via Remotion CLI
    cmd = [
        "npx", "remotion", "render",
        "SingleSceneRender",
        "--props", os.path.abspath(props_path),
        "--output", os.path.abspath(output_path),
        "--codec", "h264",
        "--concurrency", "2",
    ]

    logger.info(
        "Remotion I2V: scene=%s preset=%s duration=%.1fs frames=%d",
        scene_id[:8], motion_preset, duration, duration_frames,
    )

    try:
        result = subprocess.run(
            cmd,
            cwd=remotion_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            logger.error("Remotion I2V failed (rc=%d): %s", result.returncode, result.stderr[-500:])
            raise RuntimeError(f"Remotion render failed: {result.stderr[-200:]}")

        logger.info("Remotion I2V success: scene=%s → %s", scene_id[:8], output_path)

    finally:
        # Clean up props file
        try:
            os.remove(props_path)
        except OSError:
            pass

    return f"{project_id}/videos/{scene_id}.mp4"


def _ffmpeg_image_to_video(
    project_id: str,
    scene_id: str,
    local_image_path: str,
    local_audio_path: str | None = None,
) -> str:
    """Create a video from an image using FFmpeg with Ken Burns zoom effect.

    Duration is driven by audio length (+ 0.5s padding). Falls back to 5s if no audio.
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

    # Determine duration from audio, default 5s
    duration = 5.0
    audio_full = None
    if local_audio_path:
        audio_full = os.path.join(settings.MEDIA_VOLUME, local_audio_path)
        if os.path.exists(audio_full):
            duration = max(_probe_audio_duration(audio_full) + 0.5, 3.0)
        else:
            audio_full = None

    # zoompan d parameter = duration * fps (24)
    zoom_frames = int(duration * 24)
    zoom_filter = (
        f"scale=2560:-1,"
        f"zoompan=z='min(zoom+0.002,1.1)':d={zoom_frames}:x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)':s=1280x720:fps=24,"
        f"setpts=PTS-STARTPTS"
    )

    t_str = f"{duration:.1f}"

    if audio_full:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_full_path,
            "-i", audio_full,
            "-vf", zoom_filter,
            "-t", t_str,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-shortest",
            filepath,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_full_path,
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-vf", zoom_filter,
            "-t", t_str,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p", "-shortest",
            filepath,
        ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error("FFmpeg I2V failed: %s", result.stderr[-500:])
            return _mock_video(project_id, scene_id)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("FFmpeg I2V error, falling back to mock")
        return _mock_video(project_id, scene_id)

    logger.info("FFmpeg I2V video created: %s (%.1fs)", filepath, duration)
    return f"{project_id}/videos/{filename}"


def _probe_audio_duration(audio_path: str) -> float:
    """Probe audio file duration using ffprobe. Returns seconds."""
    import subprocess

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass

    logger.warning("ffprobe failed for %s, defaulting to 5s", audio_path)
    return 5.0
