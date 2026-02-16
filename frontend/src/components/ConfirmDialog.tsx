"use client";

/**
 * ConfirmDialog — custom modal to replace native confirm() / alert().
 * Renders a centered overlay with smooth animations.
 */

import { useCallback, useEffect } from "react";
import { useConfirmStore } from "@/stores/useConfirmStore";

const VARIANT_COLORS = {
  danger: { accent: "#ef4444", bg: "rgba(239,68,68,0.12)", icon: "⚠" },
  info: { accent: "#7c3aed", bg: "rgba(124,58,237,0.12)", icon: "ℹ" },
  warning: { accent: "#f59e0b", bg: "rgba(245,158,11,0.12)", icon: "⚠" },
} as const;

export default function ConfirmDialog() {
  const { open, title, message, confirmText, cancelText, variant, onConfirm, onCancel, close } =
    useConfirmStore();

  const handleConfirm = useCallback(() => {
    onConfirm?.();
    close();
  }, [onConfirm, close]);

  const handleCancel = useCallback(() => {
    onCancel?.();
    close();
  }, [onCancel, close]);

  // ESC key to cancel
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") handleCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, handleCancel]);

  if (!open) return null;

  const colors = VARIANT_COLORS[variant];

  return (
    <>
      <style>{`
        @keyframes confirmOverlayIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes confirmDialogIn {
          from { opacity: 0; transform: translate(-50%, -50%) scale(0.92); }
          to { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        }
      `}</style>

      {/* Backdrop */}
      <div
        onClick={handleCancel}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0, 0, 0, 0.6)",
          backdropFilter: "blur(4px)",
          zIndex: 10000,
          animation: "confirmOverlayIn 0.2s ease",
        }}
      />

      {/* Dialog */}
      <div
        role="dialog"
        aria-modal="true"
        style={{
          position: "fixed",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 10001,
          width: "min(420px, calc(100vw - 2rem))",
          background: "linear-gradient(145deg, #1e1e2e, #181825)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "1rem",
          boxShadow: `0 20px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04), inset 0 1px 0 rgba(255,255,255,0.06)`,
          animation: "confirmDialogIn 0.25s cubic-bezier(0.16, 1, 0.3, 1)",
          overflow: "hidden",
        }}
      >
        {/* Top accent line */}
        <div
          style={{
            height: 3,
            background: `linear-gradient(90deg, transparent, ${colors.accent}, transparent)`,
          }}
        />

        <div style={{ padding: "1.5rem" }}>
          {/* Icon + Title */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
            <div
              style={{
                width: 40,
                height: 40,
                borderRadius: "0.625rem",
                background: colors.bg,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.25rem",
                flexShrink: 0,
              }}
            >
              {colors.icon}
            </div>
            <h3
              style={{
                margin: 0,
                fontSize: "1.05rem",
                fontWeight: 600,
                color: "#e4e4e7",
                letterSpacing: "-0.01em",
              }}
            >
              {title}
            </h3>
          </div>

          {/* Message */}
          <p
            style={{
              margin: "0 0 1.5rem",
              fontSize: "0.9rem",
              color: "#a1a1aa",
              lineHeight: 1.6,
            }}
          >
            {message}
          </p>

          {/* Actions */}
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "0.625rem",
            }}
          >
            {cancelText && (
              <button
                onClick={handleCancel}
                style={{
                  padding: "0.5rem 1.25rem",
                  background: "rgba(255, 255, 255, 0.06)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "0.5rem",
                  color: "#a1a1aa",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(255, 255, 255, 0.1)";
                  e.currentTarget.style.color = "#e4e4e7";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "rgba(255, 255, 255, 0.06)";
                  e.currentTarget.style.color = "#a1a1aa";
                }}
              >
                {cancelText}
              </button>
            )}
            <button
              onClick={handleConfirm}
              autoFocus
              style={{
                padding: "0.5rem 1.25rem",
                background: `linear-gradient(135deg, ${colors.accent}, ${colors.accent}dd)`,
                border: "none",
                borderRadius: "0.5rem",
                color: "#fff",
                fontSize: "0.875rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s ease",
                boxShadow: `0 2px 8px ${colors.accent}44`,
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-1px)";
                e.currentTarget.style.boxShadow = `0 4px 16px ${colors.accent}66`;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "none";
                e.currentTarget.style.boxShadow = `0 2px 8px ${colors.accent}44`;
              }}
            >
              {confirmText}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
