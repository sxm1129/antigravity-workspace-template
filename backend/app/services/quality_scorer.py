from __future__ import annotations
"""VLM Quality Scorer — evaluates generated assets using a Vision LLM."""

import json
import logging
from dataclasses import dataclass, field

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class QualityScore:
    """Image quality assessment result."""
    overall: float = 0.0
    composition: float = 0.0
    prompt_adherence: float = 0.0
    character_consistency: float = 0.0
    technical_quality: float = 0.0
    reasons: list[str] = field(default_factory=list)


async def score_image(
    image_path: str,
    original_prompt: str,
    character_refs: list[str] | None = None,
) -> QualityScore:
    """Score a generated image using a VLM.

    Returns a QualityScore with 0-1 normalized scores.
    Falls back to a default neutral score if scoring fails.
    """
    import base64

    try:
        # Read image and encode
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        scoring_prompt = (
            "You are an expert comic art director evaluating a generated image.\n\n"
            f"Original prompt: {original_prompt}\n\n"
            "Score the image on these dimensions (0-10 each):\n"
            "1. composition: Layout, framing, visual balance\n"
            "2. prompt_adherence: How well it matches the requested scene\n"
            "3. character_consistency: Character appearance quality\n"
            "4. technical_quality: Clarity, no artifacts, proper anatomy\n\n"
            'Respond in JSON only: {"composition": N, "prompt_adherence": N, '
            '"character_consistency": N, "technical_quality": N, "reasons": ["..."]}'
        )

        content: list[dict] = [
            {"type": "text", "text": scoring_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ]

        # Use key rotation pool from llm_client
        from app.services.llm_client import _next_key, _get_client
        api_key = _next_key()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
            "max_tokens": 300,
        }

        client = _get_client()
        resp = await client.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()

        data = resp.json()
        raw_text = data["choices"][0]["message"]["content"]
        scores = json.loads(raw_text)

        overall = (
            scores.get("composition", 5) * 0.20
            + scores.get("prompt_adherence", 5) * 0.35
            + scores.get("character_consistency", 5) * 0.25
            + scores.get("technical_quality", 5) * 0.20
        ) / 10.0

        return QualityScore(
            overall=round(overall, 3),
            composition=scores.get("composition", 5) / 10.0,
            prompt_adherence=scores.get("prompt_adherence", 5) / 10.0,
            character_consistency=scores.get("character_consistency", 5) / 10.0,
            technical_quality=scores.get("technical_quality", 5) / 10.0,
            reasons=scores.get("reasons", []),
        )

    except Exception as e:
        logger.warning("Image scoring failed, returning neutral score: %s", e)
        return QualityScore(overall=0.5, reasons=["scoring_unavailable"])


def check_audio_quality(audio_path: str, dialogue_text: str) -> tuple[bool, str]:
    """Check TTS audio duration for reasonableness.

    Returns (is_ok, reason).
    """
    import subprocess

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(result.stdout.strip())
    except Exception:
        return True, "could not determine duration"

    if not dialogue_text:
        return True, "no dialogue to compare"

    expected = len(dialogue_text) / 4.0  # ~4 chars/sec for Chinese
    if duration > expected * 3:
        return False, f"audio too long: {duration:.1f}s vs expected ~{expected:.1f}s"
    if duration < expected * 0.2:
        return False, f"audio too short: {duration:.1f}s vs expected ~{expected:.1f}s"

    return True, "ok"
