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
        self._media_volume = os.path.abspath(settings.MEDIA_VOLUME)
        # Verify remotion project exists
        pkg_json = os.path.join(self._remotion_dir, "package.json")
        if not os.path.exists(pkg_json):
            raise ImportError(
                f"Remotion project not found at {self._remotion_dir}. "
                f"Expected package.json at {pkg_json}"
            )
        # Auto-create symlink: remotion/public/media → media_volume
        self._ensure_media_symlink()

    def _ensure_media_symlink(self) -> None:
        """Ensure public/media symlink points to media_volume."""
        public_media = os.path.join(self._remotion_dir, "public", "media")
        if os.path.islink(public_media):
            if os.readlink(public_media) == self._media_volume:
                return  # Already correct
            os.remove(public_media)
        elif os.path.exists(public_media):
            logger.warning("public/media exists but is not a symlink; skipping")
            return
        os.symlink(self._media_volume, public_media)
        logger.info("Created symlink: %s → %s", public_media, self._media_volume)

    def _validate_assets(self, scenes: list[SceneData]) -> None:
        """Pre-flight check: verify all asset files exist on disk."""
        missing = []
        for s in scenes:
            video_abs = os.path.join(self._media_volume, s.video_path)
            if not os.path.isfile(video_abs):
                missing.append(f"scene {s.id}: video {s.video_path}")
            if s.audio_path:
                audio_abs = os.path.join(self._media_volume, s.audio_path)
                if not os.path.isfile(audio_abs):
                    missing.append(f"scene {s.id}: audio {s.audio_path}")
        if missing:
            detail = "\n  ".join(missing)
            raise FileNotFoundError(
                f"Asset pre-validation failed — {len(missing)} file(s) missing:\n  {detail}"
            )
        logger.info("Asset pre-validation passed: %d scenes, all files exist", len(scenes))

    def _stage_assets(self, project_id: str, scenes: list[SceneData]) -> str:
        """Hardlink scene assets into remotion/public/ for rendering.

        Returns the staging dir path. Caller MUST clean up via _cleanup_staged().
        Uses hardlinks (instant, zero disk overhead) with copy fallback.
        """
        stage_dir = os.path.join(self._remotion_dir, "public", project_id)
        os.makedirs(stage_dir, exist_ok=True)

        staged_files = set()
        for s in scenes:
            for rel_path in [s.video_path, s.audio_path]:
                if not rel_path:
                    continue
                src = os.path.join(self._media_volume, rel_path)
                dst = os.path.join(self._remotion_dir, "public", rel_path)
                if dst in staged_files or os.path.exists(dst):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    os.link(src, dst)  # hardlink — instant, no extra disk
                except OSError:
                    import shutil
                    shutil.copy2(src, dst)  # fallback for cross-device
                staged_files.add(dst)

        logger.info("Staged %d assets into public/%s", len(staged_files), project_id)
        return stage_dir

    def _cleanup_staged(self, project_id: str) -> None:
        """Remove staged assets from remotion/public/ after render."""
        stage_dir = os.path.join(self._remotion_dir, "public", project_id)
        if os.path.isdir(stage_dir):
            import shutil
            shutil.rmtree(stage_dir, ignore_errors=True)
            logger.info("Cleaned up staged assets in public/%s", project_id)

    def compose(
        self,
        project_id: str,
        scenes: list[SceneData],
        *,
        title: str = "",
        episode_title: str | None = None,
        bgm_path: str | None = None,
        style: str = "default",
        on_progress: Any | None = None,
    ) -> ComposeResult:
        """Render via `npx remotion render ComicDrama`.

        Args:
            on_progress: Optional callback ``(rendered: int, total: int) -> None``
                         called each time Remotion reports frame progress.
        """
        import re

        if not scenes:
            raise ValueError("No scenes to compose")

        # Pre-flight: verify all assets exist
        self._validate_assets(scenes)

        # Stage assets into remotion/public/ via hardlinks
        self._stage_assets(project_id, scenes)

        try:
            # Build input props (paths relative to public/)
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

            # Invoke Remotion CLI with streaming output for progress
            cmd = [
                "npx", "remotion", "render",
                "ComicDrama",
                "--props", os.path.abspath(props_path),
                "--output", os.path.abspath(output_path),
                "--codec", "h264",
                "--concurrency", "2",
                "--log=verbose",
            ]

            logger.info(
                "Remotion render: project=%s, scenes=%d, cmd=%s",
                project_id, len(scenes), " ".join(cmd),
            )

            # Remotion v4 writes progress via stdout using \r carriage returns.
            # We merge stdout+stderr and read character-by-character so we can
            # split on both \r and \n to capture progress lines.
            progress_patterns = [
                re.compile(r"(\d+)\s+out\s+of\s+(\d+)\s+frames"),  # "5 out of 144 frames"
                re.compile(r"Rendered?\s+(\d+)/(\d+)"),             # "Rendered 5/144"
                re.compile(r"\((\d+)/(\d+)\)"),                     # "(5/144)"
                re.compile(r"frame\s+(\d+)/(\d+)", re.IGNORECASE),  # "frame 5/144"
                re.compile(r"Stitching.*?(\d+)%"),                  # "Stitching ... 50%"
            ]
            output_lines: list[str] = []

            process = subprocess.Popen(
                cmd,
                cwd=self._remotion_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr into stdout
                text=True,
            )

            try:
                assert process.stdout is not None
                buf = ""
                for ch in iter(lambda: process.stdout.read(1), ""):
                    if ch in ("\r", "\n"):
                        line = buf.strip()
                        if line:
                            output_lines.append(line)
                            # Try each pattern in priority order
                            for i, pat in enumerate(progress_patterns):
                                m = pat.search(line)
                                if m and on_progress:
                                    if i == 4:  # Stitching percentage
                                        pct = int(m.group(1))
                                        on_progress(pct, 100)
                                    else:
                                        rendered, total = int(m.group(1)), int(m.group(2))
                                        on_progress(rendered, total)
                                    break
                        buf = ""
                    else:
                        buf += ch
                # Handle any remaining buffer
                if buf.strip():
                    output_lines.append(buf.strip())

                process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                raise RuntimeError("Remotion render timed out after 600s")

            if process.returncode != 0:
                error_tail = "\n".join(output_lines[-20:])
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
        finally:
            # Always clean up staged assets
            self._cleanup_staged(project_id)

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

            - Preview: `/media/{path}` — relative URL, served by FastAPI
            - CLI render: `http://localhost:9001/media/{path}` — absolute URL
              from the already-running FastAPI server. This is the most robust
              approach: Chromium in Remotion can fetch HTTP URLs reliably,
              avoiding filesystem/symlink/webpack bundler complexities.
            """
            if for_preview:
                return f"/media/{relative_path}"
            # CLI render: full HTTP URL from FastAPI's media endpoint
            return f"http://localhost:9001/media/{relative_path}"

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
                from app.services.tts_service import strip_speaker_prefix
                scene_dict["dialogue"] = strip_speaker_prefix(s.dialogue_text)
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
