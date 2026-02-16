import React from "react";
import { OffthreadVideo, Audio, useCurrentFrame } from "remotion";
import type { SceneProps } from "../types";
import { DialogueBubble } from "./DialogueBubble";

interface SceneClipProps {
  scene: SceneProps;
  style: "default" | "manga_cn";
}

/**
 * Single scene — video clip + optional audio + dialogue bubble overlay.
 * Uses OffthreadVideo for better @remotion/player compatibility.
 * Falls back to a gradient placeholder when videoSrc is missing.
 */
export const SceneClip: React.FC<SceneClipProps> = ({ scene, style }) => {
  const frame = useCurrentFrame();

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
        background: "#000",
      }}
    >
      {/* Scene video or fallback placeholder */}
      {scene.videoSrc ? (
        <OffthreadVideo
          src={scene.videoSrc}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #1a1a2e, #16213e)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "rgba(255,255,255,0.3)",
            fontSize: 18,
          }}
        >
          场景 {scene.id.slice(0, 8)}
        </div>
      )}

      {/* TTS narration audio */}
      {scene.audioSrc && <Audio src={scene.audioSrc} />}

      {/* Dialogue bubble */}
      {scene.dialogue && (
        <DialogueBubble
          text={scene.dialogue}
          bubbleStyle={scene.bubbleStyle || "normal"}
          position={scene.bubblePosition || { x: 0.5, y: 0.8 }}
          comicStyle={style}
        />
      )}

      {/* SFX text overlay */}
      {scene.sfx && (
        <div
          style={{
            position: "absolute",
            top: "10%",
            right: "5%",
            fontSize: 48,
            fontWeight: 900,
            fontStyle: "italic",
            color: "#ffeb3b",
            textShadow:
              "3px 3px 0 #e65100, -1px -1px 0 #e65100, 1px -1px 0 #e65100, -1px 1px 0 #e65100",
            transform: `rotate(-15deg) scale(${1 + Math.sin(frame * 0.3) * 0.05})`,
            fontFamily: '"Impact", "Arial Black", sans-serif',
            letterSpacing: "0.05em",
          }}
        >
          {scene.sfx}
        </div>
      )}
    </div>
  );
};
