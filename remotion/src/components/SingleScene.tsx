import React from "react";
import {
  Img,
  Audio,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import type { SingleSceneProps } from "../types";

/**
 * Motion presets for cinematic image-to-video rendering.
 *
 * Each preset defines how the image moves/scales over the duration:
 *   zoom-in   — slow zoom into center with spring easing
 *   zoom-out  — start zoomed, ease out to full
 *   pan-left  — gentle drift from right to left
 *   pan-right — gentle drift from left to right
 *   drift     — diagonal movement with subtle rotation
 */

interface MotionValues {
  scale: number;
  translateX: number;
  translateY: number;
  rotate: number;
}

function useMotion(
  preset: SingleSceneProps["motionPreset"],
  frame: number,
  fps: number,
  durationInFrames: number,
): MotionValues {
  const progress = frame / durationInFrames;

  // Spring-based easing for smooth organic movement
  const springVal = spring({
    frame,
    fps,
    config: { damping: 100, stiffness: 10, mass: 1 },
    durationInFrames,
  });

  switch (preset) {
    case "zoom-in":
      return {
        scale: interpolate(springVal, [0, 1], [1.0, 1.12]),
        translateX: interpolate(springVal, [0, 1], [0, -1]),
        translateY: interpolate(springVal, [0, 1], [0, -0.5]),
        rotate: 0,
      };

    case "zoom-out":
      return {
        scale: interpolate(springVal, [0, 1], [1.15, 1.0]),
        translateX: interpolate(springVal, [0, 1], [-1, 0]),
        translateY: interpolate(springVal, [0, 1], [-0.5, 0]),
        rotate: 0,
      };

    case "pan-left":
      return {
        scale: 1.08,
        translateX: interpolate(progress, [0, 1], [3, -3]),
        translateY: interpolate(progress, [0, 1], [0, -0.3]),
        rotate: 0,
      };

    case "pan-right":
      return {
        scale: 1.08,
        translateX: interpolate(progress, [0, 1], [-3, 3]),
        translateY: interpolate(progress, [0, 1], [-0.3, 0]),
        rotate: 0,
      };

    case "drift":
      return {
        scale: interpolate(springVal, [0, 1], [1.05, 1.1]),
        translateX: interpolate(progress, [0, 1], [-1.5, 1.5]),
        translateY: interpolate(progress, [0, 1], [1, -1]),
        rotate: interpolate(progress, [0, 1], [-0.3, 0.3]),
      };

    default:
      return {
        scale: interpolate(springVal, [0, 1], [1.0, 1.08]),
        translateX: 0,
        translateY: 0,
        rotate: 0,
      };
  }
}

/**
 * SingleScene — renders a still image as a cinematic video clip.
 *
 * Features:
 *  - Smooth Ken Burns motion via spring physics
 *  - Dark vignette overlay for depth
 *  - Fade in/out at edges
 *  - Optional audio track
 */
export const SingleScene: React.FC<SingleSceneProps> = ({
  imageSrc,
  audioSrc,
  motionPreset = "zoom-in",
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const motion = useMotion(motionPreset, frame, fps, durationInFrames);

  // Fade in (first 12 frames = 0.5s) and fade out (last 12 frames)
  const fadeFrames = Math.min(12, Math.floor(durationInFrames * 0.08));
  const opacity = interpolate(
    frame,
    [0, fadeFrames, durationInFrames - fadeFrames, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <div
      style={{
        width,
        height,
        position: "relative",
        overflow: "hidden",
        background: "#000",
      }}
    >
      {/* Image layer with motion */}
      <div
        style={{
          width: "100%",
          height: "100%",
          opacity,
          transform: `scale(${motion.scale}) translate(${motion.translateX}%, ${motion.translateY}%) rotate(${motion.rotate}deg)`,
          willChange: "transform, opacity",
        }}
      >
        <Img
          src={imageSrc}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
          }}
        />
      </div>

      {/* Vignette overlay — dark edges for cinematic depth */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Subtle film grain texture via noise */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: 0.03,
          background: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          pointerEvents: "none",
          mixBlendMode: "overlay",
        }}
      />

      {/* Audio track */}
      {audioSrc && (
        <Audio
          src={audioSrc}
          endAt={durationInFrames}
          volume={(f) =>
            f > durationInFrames - 8
              ? Math.max(0, (durationInFrames - f) / 8)
              : 1
          }
        />
      )}
    </div>
  );
};
