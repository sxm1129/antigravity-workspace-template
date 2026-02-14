from __future__ import annotations
"""FFmpeg composition service — merges all scene videos into a final output.

CRITICAL SAFEGUARDS:
1. Silent track injection: If a video has no audio stream, inject anullsrc to prevent
   FFmpeg concat filter 'Stream specifier mismatch' crash.
2. Timestamp reset: Apply setpts=PTS-STARTPTS and aresample=async=1 to fix
   Seedance video timestamp discontinuities.
3. Uniform scaling: All clips scaled to 1920x1080.
"""

import json
import logging
import os
import subprocess

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def compose_final_video(project_id: str, scene_video_paths: list[str]) -> str:
    """Compose all scene videos into a final output video.

    Args:
        project_id: Project ID.
        scene_video_paths: Ordered list of relative paths to scene videos in media_volume.

    Returns:
        Relative path to the final composed video.
    """
    if not scene_video_paths:
        raise ValueError("No scene videos to compose")

    output_dir = os.path.join(settings.MEDIA_VOLUME, project_id)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "final_output.mp4")

    # Phase 1: Normalize all clips (add silence if needed, fix timestamps, scale)
    normalized_paths = []
    for i, rel_path in enumerate(scene_video_paths):
        full_path = os.path.join(settings.MEDIA_VOLUME, rel_path)
        if not os.path.exists(full_path):
            logger.warning("Scene video not found, skipping: %s", full_path)
            continue

        norm_path = os.path.join(output_dir, f"_norm_{i:04d}.mp4")
        _normalize_clip(full_path, norm_path)
        normalized_paths.append(norm_path)

    if not normalized_paths:
        raise RuntimeError("No valid video clips to compose after normalization")

    # Phase 2: Concat all normalized clips
    _concat_clips(normalized_paths, output_path)

    # Cleanup normalized intermediates
    for p in normalized_paths:
        try:
            os.remove(p)
        except OSError:
            pass

    rel_output = f"{project_id}/final_output.mp4"
    logger.info("Final video composed: %s", rel_output)
    return rel_output


def _normalize_clip(input_path: str, output_path: str) -> None:
    """Normalize a single video clip.

    - Checks for audio stream presence via ffprobe
    - Injects anullsrc if no audio (CRITICAL for concat stability)
    - Resets timestamps with setpts=PTS-STARTPTS
    - Resamples audio with aresample=async=1
    - Scales to 1920x1080
    """
    has_audio = _has_audio_stream(input_path)

    filter_complex_parts = []

    if has_audio:
        # Video with audio: normalize both
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS",
            "-af", "aresample=async=1",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "24000",
            "-r", "24",
            output_path,
        ]
    else:
        # Video WITHOUT audio: inject silent audio track (CRITICAL!)
        logger.info("No audio stream detected in %s, injecting anullsrc", input_path)
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setpts=PTS-STARTPTS",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-ar", "24000",
            "-r", "24",
            "-shortest",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.error("FFmpeg normalize failed: %s", result.stderr[-500:])
        raise RuntimeError(f"FFmpeg normalization failed for {input_path}")


def _has_audio_stream(filepath: str) -> bool:
    """Check if a video file has an audio stream using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "json",
                filepath,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        return len(streams) > 0
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return False


def _concat_clips(clip_paths: list[str], output_path: str) -> None:
    """Concatenate normalized clips using FFmpeg concat demuxer."""
    # Create concat file list
    concat_list_path = output_path + ".concat.txt"
    with open(concat_list_path, "w") as f:
        for path in clip_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    # Cleanup concat list
    try:
        os.remove(concat_list_path)
    except OSError:
        pass

    if result.returncode != 0:
        logger.error("FFmpeg concat failed: %s", result.stderr[-500:])
        raise RuntimeError("FFmpeg final concat failed")
