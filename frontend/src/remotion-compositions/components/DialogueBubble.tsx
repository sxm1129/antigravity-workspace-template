import React from "react";
import { useCurrentFrame, interpolate, useVideoConfig, spring } from "remotion";

interface DialogueBubbleProps {
  text: string;
  bubbleStyle: "normal" | "think" | "shout" | "narration";
  position: { x: number; y: number };
  comicStyle: "default" | "manga_cn";
}

/**
 * Comic-style dialogue bubble with entrance animation.
 */
export const DialogueBubble: React.FC<DialogueBubbleProps> = ({
  text,
  bubbleStyle,
  position,
  comicStyle,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Pop-in entrance
  const scale = spring({
    frame,
    fps,
    config: { damping: 60, stiffness: 300 },
  });

  const opacity = interpolate(frame, [0, 5], [0, 1], {
    extrapolateRight: "clamp",
  });

  const bubbleConfig = getBubbleConfig(bubbleStyle, comicStyle);

  return (
    <div
      style={{
        position: "absolute",
        left: `${position.x * 100}%`,
        top: `${position.y * 100}%`,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        maxWidth: "45%",
        zIndex: 10,
      }}
    >
      {/* Bubble body */}
      <div
        style={{
          ...bubbleConfig.bodyStyle,
          padding: "16px 24px",
          fontSize: comicStyle === "manga_cn" ? 26 : 22,
          fontWeight: bubbleStyle === "shout" ? 800 : 500,
          fontFamily:
            comicStyle === "manga_cn"
              ? '"Noto Sans SC", "PingFang SC", sans-serif'
              : '"Comic Neue", "Comic Sans MS", cursive',
          lineHeight: 1.5,
          textAlign: "center",
          color: bubbleConfig.textColor,
          whiteSpace: "pre-wrap",
        }}
      >
        {text}
      </div>

      {/* Tail (pointer) — only for normal and shout */}
      {(bubbleStyle === "normal" || bubbleStyle === "shout") && (
        <div
          style={{
            position: "absolute",
            bottom: -14,
            left: "30%",
            width: 0,
            height: 0,
            borderLeft: "10px solid transparent",
            borderRight: "10px solid transparent",
            borderTop: `16px solid ${bubbleConfig.bgColor}`,
          }}
        />
      )}
    </div>
  );
};

interface BubbleConfig {
  bodyStyle: React.CSSProperties;
  textColor: string;
  bgColor: string;
}

function getBubbleConfig(
  bubbleStyle: string,
  comicStyle: string
): BubbleConfig {
  switch (bubbleStyle) {
    case "think":
      return {
        bodyStyle: {
          background: "rgba(255, 255, 255, 0.85)",
          borderRadius: "50%",
          border: "2px solid #333",
          boxShadow: "2px 2px 0 rgba(0,0,0,0.2)",
        },
        textColor: "#333",
        bgColor: "rgba(255, 255, 255, 0.85)",
      };

    case "shout":
      return {
        bodyStyle: {
          background: "#fff",
          borderRadius: 8,
          border: "3px solid #e53935",
          boxShadow: "4px 4px 0 rgba(229, 57, 53, 0.3)",
          // Jagged edges via clip-path would go here in production
        },
        textColor: "#c62828",
        bgColor: "#fff",
      };

    case "narration":
      return {
        bodyStyle: {
          background:
            comicStyle === "manga_cn"
              ? "rgba(26, 10, 46, 0.85)"
              : "rgba(30, 30, 60, 0.85)",
          borderRadius: 4,
          border: "1px solid rgba(255,255,255,0.2)",
          backdropFilter: "blur(8px)",
        },
        textColor: "rgba(255, 255, 255, 0.9)",
        bgColor: "rgba(30, 30, 60, 0.85)",
      };

    default: // "normal"
      return {
        bodyStyle: {
          background: "#fff",
          borderRadius: 20,
          border: "2px solid #333",
          boxShadow: "3px 3px 0 rgba(0,0,0,0.15)",
        },
        textColor: "#222",
        bgColor: "#fff",
      };
  }
}
