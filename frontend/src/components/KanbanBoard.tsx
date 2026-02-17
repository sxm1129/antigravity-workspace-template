"use client";

import { type Project, type Episode, episodeApi, mediaUrl } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import { useToastStore } from "@/stores/useToastStore";
import { connectProjectWS, type WSMessage } from "@/lib/ws";
import { useCeleryGuard } from "@/components/CeleryGuard";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";

const PHASE_ACTIONS: Record<string, { label: string; description: string }> = {
  STORYBOARD: {
    label: "生成全部画面",
    description: "审核通过的镜头将自动触发视频生成。全部完成后可合成最终视频。",
  },
  PRODUCTION: {
    label: "进入生产",
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

const STATUS_STYLES: Record<string, { label: string; color: string; bg: string }> = {
  DRAFT:          { label: "草稿",   color: "#94a3b8", bg: "rgba(148,163,184,0.12)" },
  OUTLINE_REVIEW: { label: "大纲审核", color: "#60a5fa", bg: "rgba(96,165,250,0.12)" },
  SCRIPT_REVIEW:  { label: "剧本审核", color: "#818cf8", bg: "rgba(129,140,248,0.12)" },
  STORYBOARD:     { label: "分镜",   color: "#a78bfa", bg: "rgba(167,139,250,0.12)" },
  PRODUCTION:     { label: "制作中", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  COMPOSING:      { label: "合成中", color: "#8b5cf6", bg: "rgba(139,92,246,0.12)" },
  COMPLETED:      { label: "已完成", color: "#10b981", bg: "rgba(16,185,129,0.12)" },
};

export default function KanbanBoard({ project }: { project: Project }) {
  const {
    composeFinal,
    refreshCurrentProject,
    loading,
  } = useProjectStore();
  const addToast = useToastStore((s) => s.addToast);
  const { ensureWorker, guardDialog } = useCeleryGuard();
  const router = useRouter();

  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loadingEpisodes, setLoadingEpisodes] = useState(true);

  // Fetch episodes
  useEffect(() => {
    setLoadingEpisodes(true);
    episodeApi.list(project.id).then((eps) => {
      setEpisodes(eps.sort((a, b) => a.episode_number - b.episode_number));
      setLoadingEpisodes(false);
    }).catch(() => setLoadingEpisodes(false));
  }, [project.id]);

  // WebSocket for real-time updates
  useEffect(() => {
    const conn = connectProjectWS(project.id, (msg: WSMessage) => {
      if (msg.type === "project_update") {
        refreshCurrentProject();
        // Refresh episode list too
        episodeApi.list(project.id).then((eps) => {
          setEpisodes(eps.sort((a, b) => a.episode_number - b.episode_number));
        });
      }
    });
    return () => conn.close();
  }, [project.id, refreshCurrentProject]);

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

  const handlePhaseAction = async () => {
    if (!await ensureWorker()) return;
    try {
      await composeFinal(project.id);
      addToast("success", "合成任务已提交");
    } catch {
      addToast("error", "操作失败");
    }
  };

  const totalScenes = episodes.reduce((sum, ep) => sum + (ep.scenes_count || 0), 0);
  const completedEpisodes = episodes.filter((ep) => ep.status === "COMPLETED").length;

  const finalVideoUrl = project.final_video_path
    ? mediaUrl(project.final_video_path)
    : null;

  return (
    <div style={{ padding: "24px" }}>
      {guardDialog}

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
              <span>剧集: {episodes.length}</span>
              <span>|</span>
              <span>总镜头: {totalScenes}</span>
              <span>|</span>
              <span>已完成: {completedEpisodes}/{episodes.length}</span>
            </div>
          </div>
          {project.status === "PRODUCTION" && (
            <button
              className="btn-primary"
              onClick={handlePhaseAction}
              disabled={loading}
              style={{ flexShrink: 0, marginLeft: 24, background: "linear-gradient(135deg, #f59e0b, #d97706)" }}
            >
              {loading ? <span className="spinner" /> : null}
              🎞 合成最终视频
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
          <h3 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 8 }}>
            正在合成最终视频...
          </h3>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
            正在拼接镜头片段，添加转场效果
          </p>
          <div style={{
            width: "100%", maxWidth: 400, height: 4, borderRadius: 2,
            background: "rgba(255,255,255,0.08)", margin: "0 auto 14px", overflow: "hidden",
          }}>
            <div style={{
              width: "100%", height: "100%",
              background: "linear-gradient(90deg, #6366f1, #8b5cf6, #6366f1)",
              borderRadius: 2, animation: "composeProgress 2s ease-in-out infinite",
            }} />
          </div>
          <div style={{ display: "flex", justifyContent: "center", gap: 24, fontSize: 12, color: "var(--text-muted)" }}>
            <span>已用时: <b style={{ color: "var(--text-secondary)" }}>
              {Math.floor(composeElapsed / 60)}:{String(composeElapsed % 60).padStart(2, "0")}
            </b></span>
          </div>
          <style>{`@keyframes composeProgress { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }`}</style>
        </div>
      )}

      {/* Final Video Section */}
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
                      padding: "10px 20px", fontSize: 13, fontWeight: 600, color: "#fff",
                      background: "linear-gradient(135deg, var(--accent-primary), #6045d6)",
                      borderRadius: "var(--radius-sm)", textDecoration: "none",
                      display: "inline-flex", alignItems: "center", gap: 6,
                    }}
                  >
                    ▶ 在线预览
                  </a>
                  <a
                    href={finalVideoUrl}
                    download
                    style={{
                      padding: "10px 20px", fontSize: 13, fontWeight: 600, color: "var(--text-primary)",
                      background: "rgba(255,255,255,0.08)", border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)", textDecoration: "none",
                      display: "inline-flex", alignItems: "center", gap: 6,
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

      {/* Episode Cards Grid */}
      {loadingEpisodes ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
          <div className="spinner" style={{ width: 28, height: 28 }} />
        </div>
      ) : episodes.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {episodes.map((ep) => {
            const st = STATUS_STYLES[ep.status] || STATUS_STYLES.DRAFT;
            return (
              <div
                key={ep.id}
                onClick={() => router.push(`/project/${project.id}/episode/${ep.id}`)}
                className="glass-panel"
                style={{
                  padding: "20px 22px",
                  cursor: "pointer",
                  transition: "all 0.2s ease",
                  borderLeft: `3px solid ${st.color}`,
                  position: "relative",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
                  (e.currentTarget as HTMLElement).style.boxShadow = "0 8px 24px rgba(0,0,0,0.3)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.transform = "translateY(0)";
                  (e.currentTarget as HTMLElement).style.boxShadow = "";
                }}
              >
                {/* Header */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 600, letterSpacing: 1,
                    color: "var(--text-muted)", textTransform: "uppercase",
                  }}>
                    第 {ep.episode_number} 集
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 600, padding: "3px 10px",
                    borderRadius: 20, color: st.color, background: st.bg,
                  }}>
                    {st.label}
                  </span>
                </div>

                {/* Title */}
                <h4 style={{
                  fontSize: 15, fontWeight: 600, color: "var(--text-primary)",
                  marginBottom: 8, lineHeight: 1.4,
                }}>
                  {ep.title}
                </h4>

                {/* Synopsis */}
                {ep.synopsis && (
                  <p style={{
                    fontSize: 12, color: "var(--text-muted)",
                    lineHeight: 1.5, marginBottom: 12,
                    overflow: "hidden", textOverflow: "ellipsis",
                    display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                  }}>
                    {ep.synopsis}
                  </p>
                )}

                {/* Footer stats */}
                <div style={{
                  display: "flex", alignItems: "center", gap: 14,
                  fontSize: 12, color: "var(--text-muted)",
                  borderTop: "1px solid rgba(255,255,255,0.06)",
                  paddingTop: 10, marginTop: 4,
                }}>
                  <span>🎬 {ep.scenes_count ?? 0} 镜头</span>
                  {ep.final_video_path && (
                    <span style={{ color: "#10b981" }}>✅ 已合成</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: 80, color: "var(--text-muted)" }}>
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>🎬</div>
          <p style={{ fontSize: 14 }}>暂无剧集, 请先在编剧模式完成剧本</p>
        </div>
      )}
    </div>
  );
}
