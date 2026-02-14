from __future__ import annotations
"""TTS service — integrates with IndexTTS for speech synthesis.

Uses the IndexTTS API at configured endpoint. Returns audio as WAV bytes
and saves to local media_volume.
"""

import base64
import logging
import os
import uuid

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def synthesize_speech(
    text: str,
    project_id: str,
    scene_id: str,
    voice: str | None = None,
) -> str:
    """Synthesize speech from text and save WAV to media_volume.

    Args:
        text: The dialogue text to synthesize.
        project_id: Project ID for directory organization.
        scene_id: Scene ID for file naming.
        voice: Voice index (defaults to settings.INDEX_TTS_VOICE).

    Returns:
        Relative path to the generated audio file in media_volume.
    """
    if settings.USE_MOCK_API:
        return await _mock_tts(project_id, scene_id)

    voice = voice or settings.INDEX_TTS_VOICE
    api_url = f"{settings.INDEX_TTS_URL}/api/v1/tts"

    form_data = {
        "input_text": text,
        "index": voice,
        "beam_size": "1",
        "sample_rate": "24000",
        "use_cache": "true",
    }

    # Dynamic timeout: base 60s + 10s per 50 chars, max 600s
    timeout = min(60.0 + len(text) // 50 * 10.0, 600.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(api_url, data=form_data)
        response.raise_for_status()

    result = response.json()
    if not result.get("success"):
        error_msg = result.get("error", "Unknown TTS error")
        raise RuntimeError(f"IndexTTS failed: {error_msg}")

    # Decode Base64 WAV audio
    audio_bytes = base64.b64decode(result["audio_base64"])

    # Save to media_volume
    rel_path = _save_audio(audio_bytes, project_id, scene_id)
    logger.info("TTS audio saved: %s (%d bytes)", rel_path, len(audio_bytes))
    return rel_path


def _save_audio(audio_bytes: bytes, project_id: str, scene_id: str) -> str:
    """Save audio bytes to media_volume and return relative path."""
    dir_path = os.path.join(settings.MEDIA_VOLUME, project_id, "audio")
    os.makedirs(dir_path, exist_ok=True)

    filename = f"{scene_id}.wav"
    filepath = os.path.join(dir_path, filename)
    with open(filepath, "wb") as f:
        f.write(audio_bytes)

    return f"{project_id}/audio/{filename}"


async def _mock_tts(project_id: str, scene_id: str) -> str:
    """Generate a silent WAV file for mock TTS.

    Creates a minimal valid WAV header with 1 second of silence.
    """
    import struct

    sample_rate = 24000
    num_channels = 1
    bits_per_sample = 16
    duration_sec = 2
    num_samples = sample_rate * duration_sec

    # WAV header
    data_size = num_samples * num_channels * (bits_per_sample // 8)
    file_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        file_size,
        b"WAVE",
        b"fmt ",
        16,  # PCM chunk size
        1,   # PCM format
        num_channels,
        sample_rate,
        sample_rate * num_channels * (bits_per_sample // 8),
        num_channels * (bits_per_sample // 8),
        bits_per_sample,
        b"data",
        data_size,
    )

    audio_bytes = header + b"\x00" * data_size
    return _save_audio(audio_bytes, project_id, scene_id)
