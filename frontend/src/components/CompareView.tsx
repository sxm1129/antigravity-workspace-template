"use client";

/** CompareView — side-by-side or overlay comparison for assets. */

import { useState, useRef, useCallback } from "react";
import { mediaUrl } from "@/lib/api";

interface CompareViewProps {
  leftPath: string | null;
  rightPath: string | null;
  leftLabel?: string;
  rightLabel?: string;
  type?: "image" | "video";
}

export default function CompareView({
  leftPath,
  rightPath,
  leftLabel = "旧版",
  rightLabel = "新版",
  type = "image",
}: CompareViewProps) {
  const [splitPos, setSplitPos] = useState(50); // percent
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    setSplitPos(Math.max(5, Math.min(95, pct)));
  }, []);

  const leftUrl = mediaUrl(leftPath);
  const rightUrl = mediaUrl(rightPath);

  if (!leftUrl || !rightUrl) {
    return (
      <div style={{ color: "#888", textAlign: "center", padding: "2rem" }}>
        需要两个版本才能对比
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onMouseMove={handleMouseMove}
      onMouseUp={() => (dragging.current = false)}
      onMouseLeave={() => (dragging.current = false)}
      style={{
        position: "relative",
        width: "100%",
        aspectRatio: "16 / 9",
        overflow: "hidden",
        borderRadius: "0.75rem",
        cursor: "col-resize",
        userSelect: "none",
      }}
    >
      {/* Right (full) */}
      {type === "image" ? (
        <img src={rightUrl} alt={rightLabel} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      ) : (
        <video src={rightUrl} autoPlay loop muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      )}

      {/* Left (clipped) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          width: `${splitPos}%`,
          overflow: "hidden",
        }}
      >
        {type === "image" ? (
          <img src={leftUrl} alt={leftLabel} style={{ width: `${10000 / splitPos}%`, maxWidth: "none", height: "100%", objectFit: "cover" }} />
        ) : (
          <video src={leftUrl} autoPlay loop muted style={{ width: `${10000 / splitPos}%`, maxWidth: "none", height: "100%", objectFit: "cover" }} />
        )}
      </div>

      {/* Divider */}
      <div
        onMouseDown={() => (dragging.current = true)}
        style={{
          position: "absolute",
          top: 0,
          bottom: 0,
          left: `${splitPos}%`,
          width: "3px",
          background: "#fff",
          cursor: "col-resize",
          boxShadow: "0 0 8px rgba(0,0,0,0.5)",
          zIndex: 2,
        }}
      />

      {/* Labels */}
      <div style={{ position: "absolute", top: "0.5rem", left: "0.5rem", background: "rgba(0,0,0,0.6)", color: "#fff", padding: "0.25rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.75rem", zIndex: 3 }}>
        {leftLabel}
      </div>
      <div style={{ position: "absolute", top: "0.5rem", right: "0.5rem", background: "rgba(0,0,0,0.6)", color: "#fff", padding: "0.25rem 0.5rem", borderRadius: "0.25rem", fontSize: "0.75rem", zIndex: 3 }}>
        {rightLabel}
      </div>
    </div>
  );
}
