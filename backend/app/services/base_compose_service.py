from __future__ import annotations
"""Abstract base for video composition services (Strategy Pattern).

Two implementations:
- FFmpegComposeService  — fast concat, no effects
- RemotionComposeService — React-based, full post-production

Selected via settings.COMPOSE_PROVIDER.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SceneData:
    """Value object carrying everything the composer needs per scene."""

    id: str
    video_path: str          # relative path in media_volume
    audio_path: str | None = None
    dialogue_text: str | None = None
    sfx_text: str | None = None
    prompt_motion: str | None = None
    sequence_order: int = 0
    duration_seconds: float = 5.0

    # Remotion-specific (ignored by FFmpeg)
    transition: str | None = "fade"        # fade | dissolve | wipe | slide
    bubble_style: str | None = "normal"    # normal | think | shout | narration
    bubble_position: dict[str, float] | None = None  # {x, y} as 0-1 ratios


@dataclass
class ComposeResult:
    """Standardized composition result."""

    output_path: str
    provider: str
    duration_seconds: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseComposeService(ABC):
    """Abstract compose service — strategy interface."""

    provider_name: str = "unknown"

    @abstractmethod
    def compose(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
        on_progress: Callable[[int, int], None] | None = None,
    ) -> ComposeResult:
        """Compose scene clips into a final video.

        Args:
            project_id: Project ID for output directory.
            scenes: Ordered scene data list.
            title: Project title (for title card).
            episode_title: Episode title (optional).
            bgm_path: Background music path (optional).
            style: Style preset name.

        Returns:
            ComposeResult with the output video path.
        """

    def supports_preview(self) -> bool:
        """Whether this provider supports real-time browser preview."""
        return False

    def get_preview_props(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
    ) -> dict | None:
        """Generate preview props for @remotion/player (Remotion only)."""
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_compose_service: BaseComposeService | None = None


def get_compose_service() -> BaseComposeService:
    """Return the compose service singleton based on settings.COMPOSE_PROVIDER."""
    global _compose_service
    if _compose_service is not None:
        return _compose_service

    from app.config import get_settings
    settings = get_settings()
    provider = getattr(settings, "COMPOSE_PROVIDER", "ffmpeg").lower()

    if provider == "remotion":
        try:
            from app.services.remotion_service import RemotionComposeService
            _compose_service = RemotionComposeService()
            logger.info("Compose provider: remotion")
        except ImportError:
            logger.warning(
                "Remotion service not available, falling back to ffmpeg"
            )
            from app.services.ffmpeg_compose import FFmpegComposeService
            _compose_service = FFmpegComposeService()
    else:
        from app.services.ffmpeg_compose import FFmpegComposeService
        _compose_service = FFmpegComposeService()
        logger.info("Compose provider: ffmpeg")

    return _compose_service


def reset_compose_service() -> None:
    """Reset singleton (for testing / hot-reload)."""
    global _compose_service
    _compose_service = None
