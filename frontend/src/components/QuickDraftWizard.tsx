"use client";

/** QuickDraftWizard — full-screen dialog for one-click pipeline execution. */

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { quickDraftApi, type DraftProgress } from "@/lib/api";
import { useToastStore } from "@/stores/useToastStore";
import ProgressBar from "@/components/ProgressBar";

interface QuickDraftWizardProps {
  open: boolean;
  onClose: () => void;
}

const STEP_LABELS: Record<string, string> = {
  outline: "生成大纲",
  script: "撰写剧本",
  parse_scenes: "解析分镜",
  tts: "合成语音",
  image_gen: "绘制画面",
  video_gen: "生成动画",
  compose: "合成成片",
  done: "完成",
  error: "出错",
};

export default function QuickDraftWizard({ open, onClose }: QuickDraftWizardProps) {
  const router = useRouter();
  const addToast = useToastStore((s) => s.addToast);
  const [title, setTitle] = useState("");
  const [logline, setLogline] = useState("");
  const [running, setRunning] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [progress, setProgress] = useState<DraftProgress | null>(null);

  // Poll for progress when running
  useEffect(() => {
    if (!running || !projectId) return;
    const interval = setInterval(async () => {
      try {
        const res = await quickDraftApi.progress(projectId);
        setProgress(res.progress);
        if (res.status === "COMPLETED" || res.progress?.step === "done") {
          setRunning(false);
          addToast("success", "一键预览完成!");
          clearInterval(interval);
          router.push(`/project/${projectId}`);
        }
        if (res.progress?.step === "error") {
          setRunning(false);
          addToast("error", res.progress.desc || "生成失败");
          clearInterval(interval);
        }
      } catch {
        // ignore poll errors
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [running, projectId, addToast, router]);

  const handleStart = useCallback(async () => {
    if (!title.trim() || !logline.trim()) {
      addToast("warning", "请填写标题和灵感");
      return;
    }
    setRunning(true);
    try {
      const res = await quickDraftApi.start({ title: title.trim(), logline: logline.trim() });
      setProjectId(res.project_id);
      addToast("info", "开始生成预览...");
    } catch (err: unknown) {
      setRunning(false);
      addToast("error", err instanceof Error ? err.message : "启动失败");
    }
  }, [title, logline, addToast]);

  if (!open) return null;

  const pct = progress ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(8px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: "linear-gradient(135deg, #1e1e2f, #2a2a40)",
          borderRadius: "1rem",
          padding: "2rem",
          width: "min(90vw, 520px)",
          color: "#fff",
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1.5rem" }}>
          <h2 style={{ margin: 0, fontSize: "1.25rem" }}>一键预览</h2>
          {!running && (
            <button
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                color: "#888",
                fontSize: "1.5rem",
                cursor: "pointer",
              }}
            >
              ×
            </button>
          )}
        </div>

        {!running ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <input
              placeholder="项目标题"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                border: "1px solid #444",
                background: "#2a2a40",
                color: "#fff",
                fontSize: "0.9rem",
              }}
            />
            <textarea
              placeholder="一句话灵感 (logline)..."
              value={logline}
              onChange={(e) => setLogline(e.target.value)}
              rows={3}
              style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                border: "1px solid #444",
                background: "#2a2a40",
                color: "#fff",
                fontSize: "0.9rem",
                resize: "vertical",
              }}
            />
            <button
              onClick={handleStart}
              style={{
                padding: "0.75rem 1.5rem",
                borderRadius: "0.5rem",
                border: "none",
                background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
                color: "#fff",
                fontWeight: 600,
                fontSize: "1rem",
                cursor: "pointer",
              }}
            >
              开始生成
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <ProgressBar percent={pct} />
            <p style={{ fontSize: "0.875rem", color: "#a78bfa", margin: 0, textAlign: "center" }}>
              {progress ? `${STEP_LABELS[progress.step] || progress.step} (${progress.current}/${progress.total})` : "正在启动..."}
            </p>
            <p style={{ fontSize: "0.8rem", color: "#888", margin: 0, textAlign: "center" }}>
              {progress?.desc || "请稍候..."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
