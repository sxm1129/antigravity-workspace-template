import React from "react";
import { useCurrentFrame, interpolate, useVideoConfig } from "remotion";

interface CreditsProps {
  title: string;
  style: "default" | "manga_cn";
}

/**
 * End credits — project title + powered-by text with scroll animation.
 */
export const Credits: React.FC<CreditsProps> = ({ title, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, fps * 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  const isManga = style === "manga_cn";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: "#0a0a1a",
        opacity,
        fontFamily: isManga
          ? '"Noto Sans SC", sans-serif'
          : '"Inter", sans-serif',
      }}
    >
      <p
        style={{
          fontSize: 20,
          color: "rgba(255, 255, 255, 0.5)",
          letterSpacing: "0.2em",
          textTransform: "uppercase",
          marginBottom: 16,
        }}
      >
        {isManga ? "制作完成" : "THE END"}
      </p>

      <h2
        style={{
          fontSize: 40,
          fontWeight: 700,
          color: "#ffffff",
          margin: 0,
          letterSpacing: isManga ? "0.1em" : "-0.01em",
        }}
      >
        {title}
      </h2>

      <div
        style={{
          width: 120,
          height: 2,
          background: isManga
            ? "linear-gradient(90deg, transparent, #e74c3c, transparent)"
            : "linear-gradient(90deg, transparent, #6366f1, transparent)",
          margin: "24px 0",
        }}
      />

      <p
        style={{
          fontSize: 14,
          color: "rgba(255, 255, 255, 0.3)",
          letterSpacing: "0.15em",
        }}
      >
        Powered by MotionWeaver
      </p>
    </div>
  );
};
