from __future__ import annotations
"""Remotion compose service — React-based video composition via subprocess.

Generates input_props.json from SceneData, then invokes `npx remotion render`
to produce the final video. Supports @remotion/player preview via get_preview_props().
"""

import json
import logging
import os
import subprocess
from typing import Any

from app.config import get_settings
from app.services.base_compose_service import (
    BaseComposeService,
    ComposeResult,
    SceneData,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class RemotionComposeService(BaseComposeService):
    """Remotion-based video composition (subprocess CLI)."""

    provider_name = "remotion"

    def __init__(self) -> None:
        self._remotion_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", settings.REMOTION_PROJECT_PATH)
        )
        # Verify remotion project exists
        pkg_json = os.path.join(self._remotion_dir, "package.json")
        if not os.path.exists(pkg_json):
            raise ImportError(
                f"Remotion project not found at {self._remotion_dir}. "
                f"Expected package.json at {pkg_json}"
            )

    def compose(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
    ) -> ComposeResult:
        """Render via `npx remotion render ComicDrama`."""
        if not scenes:
            raise ValueError("No scenes to compose")

        # Build input props (local paths for CLI render)
        props = self._build_props(
            project_id, scenes,
            title=title, episode_title=episode_title,
            bgm_path=bgm_path, style=style,
            for_preview=False,
        )

        # Write props to file
        output_dir = os.path.join(settings.MEDIA_VOLUME, project_id)
        os.makedirs(output_dir, exist_ok=True)
        props_path = os.path.join(output_dir, "input_props.json")
        output_path = os.path.join(output_dir, "final_output.mp4")

        with open(props_path, "w", encoding="utf-8") as f:
            json.dump(props, f, ensure_ascii=False, indent=2)

        # Invoke Remotion CLI
        cmd = [
            "npx", "remotion", "render",
            "ComicDrama",
            "--props", os.path.abspath(props_path),
            "--output", os.path.abspath(output_path),
            "--codec", "h264",
            "--concurrency", "2",  # limit parallel frame renders
        ]

        logger.info(
            "Remotion render: project=%s, scenes=%d, cmd=%s",
            project_id, len(scenes), " ".join(cmd),
        )

        result = subprocess.run(
            cmd,
            cwd=self._remotion_dir,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max
        )

        if result.returncode != 0:
            error_tail = result.stderr[-1000:] if result.stderr else "no stderr"
            logger.error("Remotion render failed: %s", error_tail)
            raise RuntimeError(f"Remotion render failed: {error_tail}")

        rel_output = f"{project_id}/final_output.mp4"
        logger.info("Remotion render complete: %s", rel_output)

        return ComposeResult(
            output_path=rel_output,
            provider=self.provider_name,
            duration_seconds=sum(s.duration_seconds for s in scenes),
            metadata={"props_path": props_path},
        )

    def supports_preview(self) -> bool:
        return True

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
        """Generate InputProps JSON for @remotion/player frontend preview."""
        return self._build_props(
            project_id, scenes,
            title=title, episode_title=episode_title,
            bgm_path=bgm_path, style=style,
            for_preview=True,
        )

    def _build_props(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
        for_preview: bool = False,
    ) -> dict[str, Any]:
        """Build ComicDramaProps dict from SceneData list.

        Args:
            for_preview: If True, return browser-accessible /media/ URLs.
                         If False, return absolute local paths (for CLI render).
        """
        fps = 24

        def _resolve_path(relative_path: str) -> str:
            """Resolve asset path based on context (browser vs local).

            Both CLI render and browser preview use Remotion's built-in
            dev server which serves static files from its `public/` directory.
            We have a symlink: remotion/public/media → backend/media_volume,
            so `/media/{relative_path}` is accessible by Remotion's Chromium.
            """
            if for_preview:
                return f"/media/{relative_path}"
            # CLI render also runs via Remotion's bundler → same dev server
            return f"/media/{relative_path}"

        scene_props = []
        for s in scenes:
            scene_dict: dict[str, Any] = {
                "id": s.id,
                "videoSrc": _resolve_path(s.video_path),
                "durationInFrames": int(s.duration_seconds * fps),
                "transition": s.transition or "fade",
            }

            if s.audio_path:
                scene_dict["audioSrc"] = _resolve_path(s.audio_path)

            if s.dialogue_text:
                scene_dict["dialogue"] = s.dialogue_text
                scene_dict["bubbleStyle"] = s.bubble_style or "normal"
                if s.bubble_position:
                    scene_dict["bubblePosition"] = s.bubble_position

            if s.sfx_text:
                scene_dict["sfx"] = s.sfx_text

            scene_props.append(scene_dict)

        props: dict[str, Any] = {
            "title": title,
            "fps": fps,
            "width": 1920,
            "height": 1080,
            "scenes": scene_props,
            "style": style if style in ("default", "manga_cn") else "default",
        }

        if episode_title:
            props["episode"] = {"title": episode_title, "number": 1}

        if bgm_path:
            props["bgmSrc"] = _resolve_path(bgm_path)
            props["bgmVolume"] = 0.3

        return props
