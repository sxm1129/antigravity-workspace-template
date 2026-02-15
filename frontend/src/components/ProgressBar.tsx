"use client";

/** ProgressBar — animated progress indicator with gradient fill. */

interface ProgressBarProps {
  percent: number; // 0-100
  height?: number;
}

export default function ProgressBar({ percent, height = 8 }: ProgressBarProps) {
  const clampedPct = Math.min(100, Math.max(0, percent));
  return (
    <div
      style={{
        width: "100%",
        height: `${height}px`,
        background: "rgba(255,255,255,0.1)",
        borderRadius: `${height / 2}px`,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${clampedPct}%`,
          height: "100%",
          background: "linear-gradient(90deg, #6366f1, #a78bfa, #c084fc)",
          borderRadius: `${height / 2}px`,
          transition: "width 0.5s ease",
        }}
      />
    </div>
  );
}
