import React from "react";
import {
  useCurrentFrame,
  interpolate,
  spring,
  useVideoConfig,
} from "remotion";

interface TitleCardProps {
  title: string;
  episode?: { title: string; number: number };
  style: "default" | "manga_cn";
}

/**
 * Title card — animated project name + episode title.
 */
export const TitleCard: React.FC<TitleCardProps> = ({
  title,
  episode,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Spring-based title entrance
  const titleScale = spring({
    frame,
    fps,
    config: { damping: 80, stiffness: 200, mass: 0.5 },
  });

  // Fade in for subtitle
  const subtitleOpacity = interpolate(frame, [fps * 0.8, fps * 1.5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Glow pulse
  const glowIntensity = interpolate(
    Math.sin(frame * 0.1),
    [-1, 1],
    [0.3, 0.8]
  );

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
        background: isManga
          ? "radial-gradient(ellipse at center, #1a0a2e 0%, #0a0a1a 70%)"
          : "radial-gradient(ellipse at center, #0d1b2a 0%, #0a0a1a 70%)",
        fontFamily: isManga
          ? '"Noto Serif SC", "STSong", serif'
          : '"Inter", "SF Pro", sans-serif',
      }}
    >
      {/* Decorative line */}
      <div
        style={{
          width: interpolate(frame, [0, fps], [0, 200], {
            extrapolateRight: "clamp",
          }),
          height: 2,
          background: isManga
            ? "linear-gradient(90deg, transparent, #e74c3c, transparent)"
            : "linear-gradient(90deg, transparent, #6366f1, transparent)",
          marginBottom: 24,
        }}
      />

      {/* Main title */}
      <h1
        style={{
          fontSize: isManga ? 72 : 64,
          fontWeight: 800,
          color: "#ffffff",
          textAlign: "center",
          transform: `scale(${titleScale})`,
          letterSpacing: isManga ? "0.15em" : "-0.02em",
          textShadow: isManga
            ? `0 0 ${glowIntensity * 40}px rgba(231, 76, 60, ${glowIntensity})`
            : `0 0 ${glowIntensity * 30}px rgba(99, 102, 241, ${glowIntensity})`,
          margin: 0,
          padding: "0 80px",
          lineHeight: 1.3,
        }}
      >
        {title}
      </h1>

      {/* Episode subtitle */}
      {episode && (
        <p
          style={{
            fontSize: 28,
            color: "rgba(255, 255, 255, 0.7)",
            opacity: subtitleOpacity,
            marginTop: 16,
            fontWeight: 400,
            letterSpacing: "0.1em",
          }}
        >
          {isManga ? `第${episode.number}集` : `Episode ${episode.number}`}
          {" — "}
          {episode.title}
        </p>
      )}

      {/* Decorative line */}
      <div
        style={{
          width: interpolate(frame, [0, fps], [0, 200], {
            extrapolateRight: "clamp",
          }),
          height: 2,
          background: isManga
            ? "linear-gradient(90deg, transparent, #e74c3c, transparent)"
            : "linear-gradient(90deg, transparent, #6366f1, transparent)",
          marginTop: 24,
        }}
      />
    </div>
  );
};
