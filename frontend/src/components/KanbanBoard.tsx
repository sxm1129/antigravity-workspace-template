"use client";

import { type Project, assetApi, mediaUrl } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import { useToastStore } from "@/stores/useToastStore";
import SceneCard from "@/components/SceneCard";
import { useEffect, useState, useRef } from "react";
import { connectProjectWS, type WSMessage } from "@/lib/ws";

const PHASE_ACTIONS: Record<string, { label: string; description: string }> = {
  STORYBOARD: {
    label: "生成全部素材",
    description: "AI 将为每个镜头生成语音、图片素材。",
  },
  PRODUCTION: {
    label: "已审核的镜头 → 生成视频",
    description: "审核通过的镜头将自动触发视频生成。全部完成后可合成最终视频。",
  },
  COMPOSING: {
    label: "合成最终视频",
    description: "所有镜头视频就绪, 合成完整漫剧视频。",
  },
  COMPLETED: {
    label: "已完成",
    description: "漫剧已生成完毕, 可下载最终视频。",
  },
};

export default function KanbanBoard({ project }: { project: Project }) {
  const {
    scenes,
    generateAllImages,
    composeFinal,
    updateSceneLocally,
    refreshCurrentProject,
    loading,
  } = useProjectStore();
  const addToast = useToastStore((s) => s.addToast);

  // WebSocket for real-time updates
  useEffect(() => {
    const conn = connectProjectWS(project.id, (msg: WSMessage) => {
      if (msg.type === "scene_update" && msg.scene_id && msg.status) {
        updateSceneLocally(msg.scene_id, { status: msg.status });
        if (["REVIEW", "READY", "audio_done"].includes(msg.status)) {
          refreshCurrentProject();
        }
      }
      if (msg.type === "project_update") {
        refreshCurrentProject();
      }
    });
    return () => conn.close();
  }, [project.id, updateSceneLocally, refreshCurrentProject]);

  const phase = PHASE_ACTIONS[project.status];
  const isComposing = project.status === "COMPOSING";

  // Elapsed timer for composing
  const [composeElapsed, setComposeElapsed] = useState(0);
  const composeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (isComposing) {
      setComposeElapsed(0);
      composeTimerRef.current = setInterval(() => {
        setComposeElapsed((t) => t + 1);
      }, 1000);
    } else {
      if (composeTimerRef.current) {
        clearInterval(composeTimerRef.current);
        composeTimerRef.current = null;
      }
    }
    return () => {
      if (composeTimerRef.current) clearInterval(composeTimerRef.current);
    };
  }, [isComposing]);

  // Auto-refresh when composing
  useEffect(() => {
    if (!isComposing) return;
    const interval = setInterval(() => {
      refreshCurrentProject();
    }, 3000);
    return () => clearInterval(interval);
  }, [isComposing, refreshCurrentProject]);

  const handlePhaseAction = async () => {
    if (project.status === "STORYBOARD") {
      await generateAllImages(project.id);
    } else if (project.status === "COMPOSING") {
      await composeFinal(project.id);
    }
  };

  const approvedCount = scenes.filter((s) =>
    ["APPROVED", "VIDEO_GEN", "READY"].includes(s.status)
  ).length;

  const readyCount = scenes.filter((s) => s.status === "READY").length;
  const reviewCount = scenes.filter((s) => s.status === "REVIEW").length;

  const handleBatchApprove = async () => {
    const reviewSceneIds = scenes
      .filter((s) => s.status === "REVIEW")
      .map((s) => s.id);
    if (reviewSceneIds.length === 0) {
      addToast("info", "没有待审核的场景");
      return;
    }
    try {
      const result = await assetApi.batchApprove(reviewSceneIds);
      addToast("success", `已批量审核 ${result.approved} 个场景`);
      refreshCurrentProject();
    } catch (err: unknown) {
      addToast("error", err instanceof Error ? err.message : "批量审核失败");
    }
  };

  const finalVideoUrl = project.final_video_path
    ? mediaUrl(project.final_video_path)
    : null;

  return (
    <div style={{ padding: "24px" }}>
      {/* Phase Header */}
      {phase && (
        <div
          className="glass-panel"
          style={{
            padding: "20px 24px",
            marginBottom: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {phase.description}
            </p>
            <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 12, color: "var(--text-muted)" }}>
              <span>总镜头: {scenes.length}</span>
              <span>|</span>
              <span>已审核: {approvedCount}</span>
              <span>|</span>
              <span>就绪: {readyCount}</span>
            </div>
          </div>
          {project.status !== "COMPLETED" && project.status !== "PRODUCTION" && project.status !== "COMPOSING" && (
            <button
              className="btn-primary"
              onClick={handlePhaseAction}
              disabled={loading}
              style={{ flexShrink: 0, marginLeft: 24 }}
            >
              {loading ? <span className="spinner" /> : null}
              {phase.label}
            </button>
          )}
          {project.status === "PRODUCTION" && reviewCount > 0 && (
            <button
              className="btn-primary"
              onClick={handleBatchApprove}
              disabled={loading}
              style={{ flexShrink: 0, marginLeft: 12, background: "linear-gradient(135deg, #10b981, #059669)" }}
            >
              全部审核 ({reviewCount})
            </button>
          )}
        </div>
      )}

      {/* Compose Progress Overlay */}
      {isComposing && (
        <div
          className="glass-panel fade-in"
          style={{
            padding: "28px 32px",
            marginBottom: 24,
            background: "linear-gradient(135deg, rgba(99,102,241,0.12), rgba(139,92,246,0.12))",
            border: "1px solid rgba(139,92,246,0.35)",
            borderRadius: "var(--radius-lg)",
            textAlign: "center",
          }}
        >
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            width: 56,
            height: 56,
            borderRadius: "50%",
            background: "rgba(99,102,241,0.15)",
            marginBottom: 16,
            animation: "pulse 2s infinite",
          }}>
            <span style={{ fontSize: 28 }}>🎬</span>
          </div>
          <h3 style={{
            fontSize: 18,
            fontWeight: 700,
            color: "var(--text-primary)",
            marginBottom: 8,
          }}>
            正在合成最终视频...
          </h3>
          <p style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            marginBottom: 16,
          }}>
            正在拼接 {scenes.length} 个镜头片段，添加转场效果
          </p>

          {/* Progress bar animation */}
          <div style={{
            width: "100%",
            maxWidth: 400,
            height: 4,
            borderRadius: 2,
            background: "rgba(255,255,255,0.08)",
            margin: "0 auto 14px",
            overflow: "hidden",
          }}>
            <div style={{
              width: "100%",
              height: "100%",
              background: "linear-gradient(90deg, #6366f1, #8b5cf6, #6366f1)",
              borderRadius: 2,
              animation: "composeProgress 2s ease-in-out infinite",
            }} />
          </div>

          <div style={{
            display: "flex",
            justifyContent: "center",
            gap: 24,
            fontSize: 12,
            color: "var(--text-muted)",
          }}>
            <span>已用时: <b style={{ color: "var(--text-secondary)" }}>
              {Math.floor(composeElapsed / 60)}:{String(composeElapsed % 60).padStart(2, "0")}
            </b></span>
            <span>镜头数: <b style={{ color: "var(--text-secondary)" }}>{scenes.length}</b></span>
          </div>

          <style>{`
            @keyframes composeProgress {
              0% { transform: translateX(-100%); }
              100% { transform: translateX(100%); }
            }
          `}</style>
        </div>
      )}

      {/* Final Video Section — show for COMPLETED projects */}
      {project.status === "COMPLETED" && (
        <div
          className="glass-panel"
          style={{
            padding: "20px 24px",
            marginBottom: 24,
            background: "linear-gradient(135deg, rgba(99,102,241,0.1), rgba(139,92,246,0.1))",
            border: "1px solid rgba(139,92,246,0.3)",
            borderRadius: "var(--radius-lg)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
                🎬 最终视频
              </h3>
              <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
                {finalVideoUrl
                  ? "漫剧视频已合成完毕，点击下载或在线预览。"
                  : "最终视频尚未合成。请点击「合成最终视频」以生成。"}
              </p>
            </div>
            <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
              {finalVideoUrl ? (
                <>
                  <a
                    href={finalVideoUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: "10px 20px",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#fff",
                      background: "linear-gradient(135deg, var(--accent-primary), #6045d6)",
                      borderRadius: "var(--radius-sm)",
                      textDecoration: "none",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    ▶ 在线预览
                  </a>
                  <a
                    href={finalVideoUrl}
                    download
                    style={{
                      padding: "10px 20px",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      background: "rgba(255,255,255,0.08)",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      textDecoration: "none",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    ⬇ 下载视频
                  </a>
                </>
              ) : (
                <button
                  className="btn-primary"
                  onClick={() => composeFinal(project.id)}
                  disabled={loading}
                  style={{ flexShrink: 0 }}
                >
                  {loading ? <span className="spinner" /> : null}
                  🎞 合成最终视频
                </button>
              )}
            </div>
          </div>
          {/* Preview player if video exists */}
          {finalVideoUrl && (
            <div style={{ marginTop: 16, borderRadius: "var(--radius-md)", overflow: "hidden" }}>
              <video
                src={finalVideoUrl}
                controls
                style={{ width: "100%", maxHeight: 400, background: "#000" }}
              />
            </div>
          )}
        </div>
      )}

      {/* Scene Grid — simple grid without dnd-kit to avoid render crash */}
      {scenes.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: 16,
          }}
        >
          {scenes.map((scene, i) => (
            <SceneCard key={scene.id} scene={scene} index={i} />
          ))}
        </div>
      ) : (
        <div
          style={{
            textAlign: "center",
            padding: 80,
            color: "var(--text-muted)",
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>🎬</div>
          <p style={{ fontSize: 14 }}>暂无分镜, 请先在编剧模式完成剧本解析</p>
        </div>
      )}
    </div>
  );
}
