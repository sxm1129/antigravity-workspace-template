"use client";

/** Toast — floating notification banners with auto-dismiss. */

import { useToastStore, type Toast as ToastType } from "@/stores/useToastStore";

const TYPE_STYLES: Record<ToastType["type"], string> = {
  success: "background: linear-gradient(135deg, #10b981, #059669); color: #fff;",
  error: "background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff;",
  info: "background: linear-gradient(135deg, #3b82f6, #2563eb); color: #fff;",
  warning: "background: linear-gradient(135deg, #f59e0b, #d97706); color: #fff;",
};

const TYPE_ICONS: Record<ToastType["type"], string> = {
  success: "✓",
  error: "✕",
  info: "ℹ",
  warning: "⚠",
};

export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: "1rem",
        right: "1rem",
        zIndex: 9999,
        display: "flex",
        flexDirection: "column",
        gap: "0.5rem",
        maxWidth: "400px",
      }}
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          style={{
            ...parseStyle(TYPE_STYLES[toast.type]),
            padding: "0.75rem 1rem",
            borderRadius: "0.5rem",
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.875rem",
            fontWeight: 500,
            animation: "slideIn 0.3s ease",
          }}
        >
          <span style={{ fontSize: "1rem", flexShrink: 0 }}>
            {TYPE_ICONS[toast.type]}
          </span>
          <span style={{ flex: 1 }}>{toast.message}</span>
          <button
            onClick={() => removeToast(toast.id)}
            style={{
              background: "transparent",
              border: "none",
              color: "inherit",
              cursor: "pointer",
              fontSize: "1rem",
              lineHeight: 1,
              opacity: 0.7,
              padding: 0,
            }}
          >
            ×
          </button>
        </div>
      ))}
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

function parseStyle(css: string): React.CSSProperties {
  const result: Record<string, string> = {};
  for (const decl of css.split(";")) {
    const [key, value] = decl.split(":").map((s) => s.trim());
    if (key && value) {
      const camelKey = key.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      result[camelKey] = value;
    }
  }
  return result as React.CSSProperties;
}
