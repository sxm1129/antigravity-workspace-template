"""Unified LLM client with multi-key round-robin, retry + exponential backoff,
timeout handling, and structured error messages.

All LLM calls across the codebase should go through `llm_call()`.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Key pool — build once from config
# ---------------------------------------------------------------------------

def _build_key_pool() -> list[str]:
    """Parse OPENROUTER_API_KEYS (comma-separated) with OPENROUTER_API_KEY as fallback."""
    keys: list[str] = []
    if settings.OPENROUTER_API_KEYS:
        keys = [k.strip() for k in settings.OPENROUTER_API_KEYS.split(",") if k.strip()]
    if not keys and settings.OPENROUTER_API_KEY:
        keys = [settings.OPENROUTER_API_KEY]
    if not keys:
        logger.warning("No OpenRouter API keys configured — LLM calls will fail")
    return keys


_KEY_POOL: list[str] = _build_key_pool()
_key_cycle = itertools.cycle(_KEY_POOL) if _KEY_POOL else None

# Track per-key failure counts for smart rotation
_key_failures: dict[str, int] = {k: 0 for k in _KEY_POOL}

OPENROUTER_URL = f"{settings.OPENROUTER_BASE_URL}/chat/completions"

# ---------------------------------------------------------------------------
# Shared HTTP client (lazy init)
# ---------------------------------------------------------------------------

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=float(settings.LLM_TIMEOUT))
    return _http_client


def _next_key() -> str:
    """Pick the next API key via round-robin, skipping keys with high failure counts."""
    if not _key_cycle:
        raise RuntimeError("No OpenRouter API keys configured")

    # Try up to len(pool) times to find a key with < 3 consecutive failures
    for _ in range(len(_KEY_POOL)):
        key = next(_key_cycle)
        if _key_failures.get(key, 0) < 3:
            return key

    # All keys have high failures — reset and return the next one anyway
    for k in _key_failures:
        _key_failures[k] = 0
    return next(_key_cycle)


def _mask_key(key: str) -> str:
    """Mask an API key for safe logging: show first 8 and last 4 chars."""
    if len(key) <= 16:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


# ---------------------------------------------------------------------------
# Retriable status codes
# ---------------------------------------------------------------------------

_RETRIABLE_STATUS = {408, 429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------

async def llm_call(
    system_prompt: str,
    user_prompt: str,
    *,
    json_mode: bool = False,
    model: str | None = None,
    max_tokens: int = 8192,
    temperature: float = 0.8,
    caller: str = "unknown",
) -> str:
    """Unified LLM call with multi-key rotation and retry + exponential backoff.

    Args:
        system_prompt: System message.
        user_prompt: User message.
        json_mode: If True, request JSON-format output.
        model: Override the default STORY_MODEL.
        max_tokens: Max tokens in response.
        temperature: Sampling temperature.
        caller: Identifier for logging (e.g. agent name).

    Returns:
        The content string from the LLM response.

    Raises:
        LLMError: If all retries are exhausted across all keys.
    """
    model = model or settings.STORY_MODEL
    max_retries = settings.LLM_MAX_RETRIES
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        key = _next_key()
        masked = _mask_key(key)

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://motionweaver.app",
            "X-Title": "MotionWeaver",
        }

        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        logger.info(
            "[%s] LLM call attempt %d/%d model=%s key=%s json=%s",
            caller, attempt, max_retries, model, masked, json_mode,
        )

        try:
            client = _get_client()
            response = await client.post(OPENROUTER_URL, headers=headers, json=body)

            if response.status_code == 401:
                # Auth failure — mark this key as bad and rotate immediately
                _key_failures[key] = _key_failures.get(key, 0) + 1
                logger.warning(
                    "[%s] 401 Unauthorized for key=%s (failures=%d), rotating...",
                    caller, masked, _key_failures[key],
                )
                last_error = LLMError(
                    f"API key {masked} unauthorized",
                    status_code=401,
                    retriable=True,
                )
                continue  # try next key immediately, no backoff

            if response.status_code in _RETRIABLE_STATUS:
                backoff = min(2 ** attempt, 30)
                logger.warning(
                    "[%s] HTTP %d (retriable), backing off %ds...",
                    caller, response.status_code, backoff,
                )
                last_error = LLMError(
                    f"HTTP {response.status_code}",
                    status_code=response.status_code,
                    retriable=True,
                )
                await asyncio.sleep(backoff)
                continue

            response.raise_for_status()

            # Success — reset failure count for this key
            _key_failures[key] = 0
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("[%s] LLM response OK, length=%d", caller, len(content))
            return content

        except httpx.TimeoutException:
            backoff = min(2 ** attempt, 30)
            logger.warning(
                "[%s] Timeout after %ds on attempt %d, backing off %ds...",
                caller, settings.LLM_TIMEOUT, attempt, backoff,
            )
            last_error = LLMError(
                f"LLM call timed out after {settings.LLM_TIMEOUT}s",
                status_code=408,
                retriable=True,
            )
            await asyncio.sleep(backoff)
            continue

        except httpx.HTTPStatusError as e:
            # Non-retriable HTTP error
            logger.error("[%s] HTTP error %d: %s", caller, e.response.status_code, e)
            raise LLMError(
                f"LLM HTTP error: {e.response.status_code}",
                status_code=e.response.status_code,
                retriable=False,
            ) from e

    # All retries exhausted
    raise last_error or LLMError("All LLM retry attempts exhausted", retriable=False)


# ---------------------------------------------------------------------------
# Health check — for /api/system/check-llm
# ---------------------------------------------------------------------------

async def check_llm_health() -> dict[str, Any]:
    """Quick health check: send a tiny prompt to verify keys are valid.

    Returns dict with status, working_keys, failed_keys, latency_ms.
    """
    results: dict[str, Any] = {
        "total_keys": len(_KEY_POOL),
        "working_keys": [],
        "failed_keys": [],
    }

    for key in _KEY_POOL:
        masked = _mask_key(key)
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.STORY_MODEL,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1,
        }
        try:
            client = _get_client()
            resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
            if resp.status_code == 200:
                results["working_keys"].append(masked)
            else:
                results["failed_keys"].append({"key": masked, "status": resp.status_code})
        except Exception as e:
            results["failed_keys"].append({"key": masked, "error": str(e)})

    results["status"] = "ok" if results["working_keys"] else "all_keys_failed"
    return results


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Structured LLM error with status code and retriable flag."""

    def __init__(self, message: str, status_code: int = 0, retriable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable
