"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { systemApi } from "@/lib/api";
import { useToastStore } from "@/stores/useToastStore";

const AUTO_START_DELAY = 5; // seconds

/**
 * useCeleryGuard — pre-flight check for Celery worker availability.
 *
 * Usage:
 *   const { ensureWorker, guardDialog } = useCeleryGuard();
 *   const handleAction = async () => {
 *     if (!(await ensureWorker())) return;
 *     // ... proceed with task dispatch
 *   };
 *   return <>{guardDialog}{...rest}</>;
 */
export function useCeleryGuard() {
  const addToast = useToastStore((s) => s.addToast);
  const [showDialog, setShowDialog] = useState(false);
  const [countdown, setCountdown] = useState(AUTO_START_DELAY);
  const [starting, setStarting] = useState(false);
  const resolveRef = useRef<((ok: boolean) => void) | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const doStart = useCallback(async () => {
    setStarting(true);
    try {
      const result = await systemApi.celeryStart();
      if (result.status === "started" || result.status === "already_running") {
        addToast("success", `✅ ${result.message}`);
        // Wait a moment for worker to fully initialize
        if (result.status === "started") {
          await new Promise((r) => setTimeout(r, 3000));
        }
        setShowDialog(false);
        resolveRef.current?.(true);
      } else {
        addToast("error", `启动失败: ${result.message}`);
        setShowDialog(false);
        resolveRef.current?.(false);
      }
    } catch (err) {
      addToast("error", `Worker 启动异常: ${(err as Error).message}`);
      setShowDialog(false);
      resolveRef.current?.(false);
    } finally {
      setStarting(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [addToast]);

  const startCountdown = useCallback(() => {
    setCountdown(AUTO_START_DELAY);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          timerRef.current = null;
          doStart();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [doStart]);

  const ensureWorker = useCallback(async (): Promise<boolean> => {
    try {
      const isOnline = await systemApi.celeryPing();
      if (isOnline) return true;
    } catch {
      // If status check fails, assume offline
    }

    // Worker offline — show dialog with countdown
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setShowDialog(true);
      startCountdown();
    });
  }, [startCountdown]);

  const handleManualStart = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    doStart();
  };

  const handleCancel = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setShowDialog(false);
    resolveRef.current?.(false);
  };

  const guardDialog = showDialog ? (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backdropFilter: "blur(4px)",
      }}
      onClick={handleCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--bg-secondary, #1a1a2e)",
          border: "1px solid var(--border, #333)",
          borderRadius: 16,
          padding: "32px 36px",
          maxWidth: 440,
          width: "90%",
          boxShadow: "0 24px 48px rgba(0,0,0,0.4)",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <span style={{ fontSize: 28 }}>⚙️</span>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary, #fff)" }}>
            任务处理引擎未启动
          </h3>
        </div>

        {/* Body */}
        <p style={{ fontSize: 13, color: "var(--text-secondary, #aaa)", lineHeight: 1.6, marginBottom: 20 }}>
          检测到 <strong>Celery Worker</strong> 未运行，素材生成任务需要 Worker 来执行。
          {!starting && countdown > 0 && (
            <span style={{ display: "block", marginTop: 8, color: "var(--accent-primary, #7c3aed)" }}>
              将在 <strong>{countdown}</strong> 秒后自动启动...
            </span>
          )}
          {starting && (
            <span style={{ display: "block", marginTop: 8, color: "var(--accent-primary, #7c3aed)" }}>
              正在启动 Worker...
            </span>
          )}
        </p>

        {/* Progress bar */}
        {!starting && countdown > 0 && (
          <div style={{
            height: 4, borderRadius: 2,
            background: "rgba(124,58,237,0.15)",
            marginBottom: 20,
            overflow: "hidden",
          }}>
            <div
              style={{
                height: "100%", borderRadius: 2,
                background: "var(--accent-primary, #7c3aed)",
                width: `${((AUTO_START_DELAY - countdown) / AUTO_START_DELAY) * 100}%`,
                transition: "width 1s linear",
              }}
            />
          </div>
        )}

        {starting && (
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
            <div className="spinner" style={{ width: 24, height: 24 }} />
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            onClick={handleCancel}
            disabled={starting}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 13,
              border: "1px solid var(--border, #333)",
              background: "transparent",
              color: "var(--text-secondary, #aaa)",
              cursor: starting ? "not-allowed" : "pointer",
              opacity: starting ? 0.5 : 1,
            }}
          >
            取消
          </button>
          <button
            onClick={handleManualStart}
            disabled={starting}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 13,
              border: "none",
              background: "linear-gradient(135deg, #7c3aed, #6d28d9)",
              color: "#fff", fontWeight: 600,
              cursor: starting ? "not-allowed" : "pointer",
              opacity: starting ? 0.7 : 1,
            }}
          >
            {starting ? "启动中..." : "立即启动"}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { ensureWorker, guardDialog };
}
