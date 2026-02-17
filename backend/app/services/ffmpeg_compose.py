from __future__ import annotations
"""FFmpeg compose service — wraps existing ffmpeg_service.py as a Strategy.

This is the 'fast path': pure concat with normalized clips, no effects.
"""

import logging

from app.services.base_compose_service import (
    BaseComposeService,
    ComposeResult,
    SceneData,
)
from app.services.ffmpeg_service import compose_final_video

logger = logging.getLogger(__name__)


class FFmpegComposeService(BaseComposeService):
    """FFmpeg-based video composition (concat demuxer)."""

    provider_name = "ffmpeg"

    def compose(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
        on_progress=None,
    ) -> ComposeResult:
        """Delegate to existing compose_final_video (normalize + concat)."""
        video_paths = [s.video_path for s in scenes if s.video_path]
        if not video_paths:
            raise ValueError("No scene videos to compose")

        if on_progress:
            on_progress(0, len(video_paths))

        output_path = compose_final_video(project_id, video_paths)

        if on_progress:
            on_progress(len(video_paths), len(video_paths))

        return ComposeResult(
            output_path=output_path,
            provider=self.provider_name,
            duration_seconds=sum(s.duration_seconds for s in scenes),
        )
