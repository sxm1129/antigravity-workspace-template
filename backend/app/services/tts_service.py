from __future__ import annotations
"""TTS service — integrates with IndexTTS for speech synthesis.

Uses the IndexTTS API at configured endpoint. Returns audio as WAV bytes
and saves to local media_volume.
"""

import base64
import logging
import os
import re
import uuid

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Regex to strip speaker / stage-direction prefixes from dialogue text.
# Handles patterns like:
#   "齐齐: ..."           → simple name + colon
#   "(旁白) 齐大山：..."   → parenthetical tag + name + colon
#   "（独白）齐齐：..."    → full-width parens + name + colon
#   "(旁白)：..."          → tag only + colon
#   "旁白：..."            → bare tag + colon
_SPEAKER_PREFIX_RE = re.compile(
    r"^\s*"
    r"(?:[（(][^)）]{1,10}[)）]\s*)?"   # optional parenthetical tag like (旁白)
    r"[\u4e00-\u9fff\w]{1,10}"          # name (Chinese chars / letters / digits)
    r"\s*[：:]\s*"                       # colon (full-width or half-width)
)

# Module-level httpx client for connection reuse (lazy init)
_http_client: httpx.AsyncClient | None = None


def strip_speaker_prefix(text: str) -> str:
    """Strip character name / stage-direction prefix from dialogue text for TTS.

    Examples:
        '齐齐: 你好啊' → '你好啊'
        '(旁白) 齐大山：我曾为了...' → '我曾为了...'
        '（独白）齐齐：好美的海...' → '好美的海...'
        '旁白：从前有一个...' → '从前有一个...'
        '普通句子' → '普通句子'  (no change)
    """
    return _SPEAKER_PREFIX_RE.sub("", text).strip()


def _get_http_client(timeout: float = 60.0) -> httpx.AsyncClient:
    """Return a module-level httpx.AsyncClient, creating it on first use."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=timeout)
    return _http_client


async def synthesize_speech(
    text: str,
    project_id: str,
    scene_id: str,
    voice: str | None = None,
) -> tuple[str, float]:
    """Synthesize speech from text and save WAV to media_volume.

    Args:
        text: The dialogue text to synthesize.
        project_id: Project ID for directory organization.
        scene_id: Scene ID for file naming.
        voice: Voice index (defaults to settings.INDEX_TTS_VOICE).

    Returns:
        Tuple of (relative_path, duration_seconds).
    """
    if settings.USE_MOCK_API:
        rel_path = await _mock_tts(project_id, scene_id)
        return rel_path, 2.0

    # Strip character name prefix (e.g., "齐齐: " → "")
    text = strip_speaker_prefix(text)
    if not text:
        logger.warning("Empty text after stripping speaker prefix for scene %s", scene_id)
        rel_path = await _mock_tts(project_id, scene_id)
        return rel_path, 0.5

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

    client = _get_http_client()
    response = await client.post(api_url, data=form_data, timeout=timeout)
    response.raise_for_status()

    result = response.json()
    if not result.get("success"):
        error_msg = result.get("error", "Unknown TTS error")
        raise RuntimeError(f"IndexTTS failed: {error_msg}")

    # Decode Base64 WAV audio
    audio_bytes = base64.b64decode(result["audio_base64"])

    # Save to media_volume
    rel_path = _save_audio(audio_bytes, project_id, scene_id)
    duration = _wav_duration(audio_bytes)
    logger.info("TTS audio saved: %s (%d bytes, %.2fs)", rel_path, len(audio_bytes), duration)
    return rel_path, duration


def _wav_duration(audio_bytes: bytes) -> float:
    """Calculate duration of WAV audio from raw bytes.

    Reads the WAV header to extract sample rate, channels, and bits per sample,
    then computes duration from data size.
    """
    import struct

    if len(audio_bytes) < 44:
        return 5.0  # fallback

    try:
        # WAV header: bytes 24-28 = sample_rate, 34-36 = bits_per_sample
        # bytes 22-24 = num_channels, bytes 40-44 = data_size
        num_channels = struct.unpack_from("<H", audio_bytes, 22)[0]
        sample_rate = struct.unpack_from("<I", audio_bytes, 24)[0]
        bits_per_sample = struct.unpack_from("<H", audio_bytes, 34)[0]
        data_size = struct.unpack_from("<I", audio_bytes, 40)[0]

        if sample_rate == 0 or num_channels == 0 or bits_per_sample == 0:
            return 5.0

        bytes_per_sample = bits_per_sample // 8
        num_samples = data_size // (num_channels * bytes_per_sample)
        return num_samples / sample_rate
    except (struct.error, ZeroDivisionError):
        return 5.0


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
