"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { useProjectStore } from "@/stores/useProjectStore";
import { useToastStore } from "@/stores/useToastStore";
import { episodeApi, assetApi, projectApi, type Episode, type Scene } from "@/lib/api";
import { connectProjectWS, type WSMessage } from "@/lib/ws";
import SceneCard from "@/components/SceneCard";
import { useCeleryGuard } from "@/components/CeleryGuard";

type PageParams = { id: string; episodeId: string };

export default function EpisodeKanbanPage(props: { params: Promise<PageParams> }) {
  const resolvedParams = use(props.params);
  const { id: projectId, episodeId } = resolvedParams;
  const router = useRouter();
  const { currentProject, fetchProject, loading, error, setError } = useProjectStore();
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [episodeScenes, setEpisodeScenes] = useState<Scene[]>([]);
  const [loadingEpisode, setLoadingEpisode] = useState(true);

  // Dismiss errors
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(timer);
  }, [error, setError]);

  // Fetch project if not loaded
  useEffect(() => {
    if (!currentProject || currentProject.id !== projectId) {
      fetchProject(projectId);
    }
  }, [projectId, currentProject, fetchProject]);

  // Fetch episode + scenes
  useEffect(() => {
    let mounted = true;
    async function load() {
      setLoadingEpisode(true);
      try {
        const ep = await episodeApi.get(episodeId);
        const scenes = await episodeApi.listScenes(episodeId);
        if (mounted) {
          setEpisode(ep);
          setEpisodeScenes(scenes);
        }
      } catch (e) {
        if (mounted) setError((e as Error).message);
      } finally {
        if (mounted) setLoadingEpisode(false);
      }
    }
    load();
    return () => { mounted = false; };
  }, [episodeId, setError]);

  if ((loading && !currentProject) || loadingEpisode) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "calc(100vh - 56px)" }}>
        <div className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  if (!currentProject || !episode) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--text-muted)" }}>
        <p>剧集未找到</p>
        <button className="btn-secondary" style={{ marginTop: 16 }} onClick={() => router.push(`/project/${projectId}`)}>
          返回项目
        </button>
      </div>
    );
  }

  return (
    <div style={{ height: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      {/* Episode Header */}
      <div
        style={{
          padding: "16px 24px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button
            onClick={() => router.push(`/project/${projectId}`)}
            style={{
              background: "none", border: "none",
              color: "var(--text-muted)", cursor: "pointer",
              fontSize: 14, padding: "4px 8px",
            }}
          >
            ← 返回项目
          </button>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
              {currentProject.title} — 第{episode.episode_number}集：{episode.title}
            </h2>
            {episode.synopsis && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2, maxWidth: 600 }}>
                {episode.synopsis.length > 80 ? episode.synopsis.slice(0, 80) + "..." : episode.synopsis}
              </p>
            )}
          </div>
        </div>

        {/* Episode status badge */}
        <div style={{
          fontSize: 12, fontWeight: 600,
          padding: "4px 12px", borderRadius: 100,
          background: "var(--accent-primary)", color: "#fff",
        }}>
          {episode.status}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: "10px 24px",
          background: "rgba(255,92,92,0.1)",
          borderBottom: "1px solid rgba(255,92,92,0.2)",
          color: "var(--accent-danger)", fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto" }}>
        <EpisodeKanbanContent
          project={currentProject}
          episode={episode}
          scenes={episodeScenes}
          onScenesUpdate={(scenes) => setEpisodeScenes(scenes)}
          onEpisodeUpdate={(ep) => setEpisode(ep)}
        />
      </div>
    </div>
  );
}

/* ── Inline Episode Kanban Content ── */

const EPISODE_PHASE_ACTIONS: Record<string, { label: string; description: string }> = {
  STORYBOARD: {
    label: "生成全部素材",
    description: "AI 将为每个镜头生成语音、图片素材。",
  },
  PRODUCTION: {
    label: "素材生成完毕",
    description: "审核通过的镜头将自动触发视频生成。全部完成后可合成最终视频。",
  },
  COMPOSING: {
    label: "合成最终视频",
    description: "所有镜头视频就绪, 合成完整漫剧视频。",
  },
  COMPLETED: {
    label: "已完成",
    description: "本集漫剧已生成完毕。",
  },
};

function EpisodeKanbanContent({
  project, episode, scenes, onScenesUpdate, onEpisodeUpdate,
}: {
  project: { id: string; title: string; status: string; tts_voice?: string | null };
  episode: Episode;
  scenes: Scene[];
  onScenesUpdate: (scenes: Scene[]) => void;
  onEpisodeUpdate: (episode: Episode) => void;
}) {
  const { generateAllImages, composeFinal, updateSceneLocally, loading } = useProjectStore();
  const addToast = useToastStore((s) => s.addToast);
  const { ensureWorker, guardDialog } = useCeleryGuard();
  const [composeProgress, setComposeProgress] = useState<{
    rendered: number; total: number; percent: number;
  } | null>(null);
  const [ttsVoices, setTtsVoices] = useState<{ id: string; label: string; lang: string }[]>([]);
  const [selectedVoice, setSelectedVoice] = useState<string>(project.tts_voice || "en_female_midnight");

  // Fetch TTS voices on mount
  useEffect(() => {
    assetApi.getTtsVoices().then(setTtsVoices).catch(() => {});
  }, []);

  const handleVoiceChange = async (voiceId: string) => {
    setSelectedVoice(voiceId);
    try {
      await projectApi.update(project.id, { tts_voice: voiceId } as Partial<any>);
    } catch {
      // silent
    }
  };

  const phase = EPISODE_PHASE_ACTIONS[episode.status];

  // ── WebSocket for real-time scene updates ──
  useEffect(() => {
    const conn = connectProjectWS(project.id, (msg: WSMessage) => {
      if (msg.type === "scene_update" && msg.scene_id && msg.status) {
        // Update the scene locally in our episode-scoped list
        onScenesUpdate(
          scenes.map((s) => s.id === msg.scene_id ? { ...s, status: msg.status! } : s)
        );
        updateSceneLocally(msg.scene_id, { status: msg.status });
        // Re-fetch scenes on significant status changes
        if (["REVIEW", "READY", "audio_done"].includes(msg.status)) {
          episodeApi.listScenes(episode.id).then(onScenesUpdate);
          episodeApi.get(episode.id).then(onEpisodeUpdate);
        }
      }
      if (msg.type === "compose_progress" && msg.rendered != null && msg.total != null) {
        setComposeProgress({
          rendered: msg.rendered,
          total: msg.total,
          percent: msg.percent ?? 0,
        });
      }
      if (msg.type === "project_update") {
        setComposeProgress(null); // Reset progress on status change
        episodeApi.get(episode.id).then(onEpisodeUpdate);
        episodeApi.listScenes(episode.id).then(onScenesUpdate);
      }
    });
    return () => conn.close();
  }, [project.id, episode.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePhaseAction = async () => {
    // Pre-flight: ensure Celery worker is running
    if (!(await ensureWorker())) return;

    if (episode.status === "STORYBOARD") {
      await generateAllImages(project.id, episode.id);
    } else if (episode.status === "PRODUCTION" || episode.status === "COMPOSING") {
      await composeFinal(project.id, episode.id);
    }
    // Refresh episode metadata + scenes after action
    const [updatedEp, updatedScenes] = await Promise.all([
      episodeApi.get(episode.id),
      episodeApi.listScenes(episode.id),
    ]);
    onEpisodeUpdate(updatedEp);
    onScenesUpdate(updatedScenes);
  };

  const reviewCount = scenes.filter((s) => s.status === "REVIEW").length;
  const approvedCount = scenes.filter((s) =>
    ["APPROVED", "VIDEO_GEN", "READY"].includes(s.status)
  ).length;
  const readyCount = scenes.filter((s) => s.status === "READY").length;

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
      const [updatedEp, updatedScenes] = await Promise.all([
        episodeApi.get(episode.id),
        episodeApi.listScenes(episode.id),
      ]);
      onEpisodeUpdate(updatedEp);
      onScenesUpdate(updatedScenes);
    } catch (err: unknown) {
      addToast("error", err instanceof Error ? err.message : "批量审核失败");
    }
  };

  return (
    <div style={{ padding: "24px" }}>
      {guardDialog}
      {/* Phase Action Header */}
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
          <div style={{ display: "flex", gap: 10, flexShrink: 0, marginLeft: 24 }}>
            {episode.status === "STORYBOARD" && (
              <>
                <select
                  value={selectedVoice}
                  onChange={(e) => handleVoiceChange(e.target.value)}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 8,
                    border: "1px solid var(--border)",
                    background: "var(--bg-elevated)",
                    color: "var(--text-primary)",
                    fontSize: 13,
                    cursor: "pointer",
                    minWidth: 200,
                  }}
                >
                  {ttsVoices.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.label}
                    </option>
                  ))}
                </select>
                <button
                  className="btn-primary"
                  onClick={handlePhaseAction}
                  disabled={loading}
                >
                  {loading ? <span className="spinner" /> : null}
                  {phase.label}
                </button>
              </>
            )}
            {episode.status === "PRODUCTION" && reviewCount > 0 && (
              <button
                className="btn-primary"
                onClick={handleBatchApprove}
                disabled={loading}
                style={{ background: "linear-gradient(135deg, #10b981, #059669)" }}
              >
                全部审核 ({reviewCount})
              </button>
            )}
            {episode.status === "PRODUCTION" && readyCount > 0 && readyCount === scenes.length && (
              <button
                className="btn-primary"
                onClick={handlePhaseAction}
                disabled={loading}
                style={{ background: "linear-gradient(135deg, #f59e0b, #d97706)" }}
              >
                {loading ? <span className="spinner" /> : null}
                🎞 合成最终视频
              </button>
            )}
            {episode.status === "PRODUCTION" && readyCount < scenes.length && readyCount >= 0 && reviewCount === 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 12, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                  视频就绪: {readyCount}/{scenes.length}
                </span>
                {(() => {
                  const stuckIds = scenes
                    .filter((s) =>
                      ["APPROVED", "VIDEO_GEN"].includes(s.status) && !s.local_video_path
                    )
                    .map((s) => s.id);
                  return stuckIds.length > 0 ? (
                    <button
                      className="btn-secondary"
                      onClick={async () => {
                        if (!(await ensureWorker())) return;
                        try {
                          await assetApi.retryVideoGen(stuckIds);
                          addToast("success", `已重新触发 ${stuckIds.length} 个场景的视频生成`);
                          const updatedScenes = await episodeApi.listScenes(episode.id);
                          onScenesUpdate(updatedScenes);
                        } catch (err: unknown) {
                          addToast("error", err instanceof Error ? err.message : "重试失败");
                        }
                      }}
                      disabled={loading}
                      style={{ fontSize: 12, padding: "6px 14px" }}
                    >
                      🔄 重新生成视频 ({stuckIds.length})
                    </button>
                  ) : null;
                })()}
              </div>
            )}
            {episode.status === "COMPOSING" && (
              <div style={{
                display: "flex", alignItems: "center", gap: 12,
                minWidth: 280,
              }}>
                <div style={{
                  flex: 1, height: 24, borderRadius: 12,
                  background: "rgba(255,255,255,0.08)",
                  overflow: "hidden", position: "relative",
                }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${composeProgress?.percent ?? 0}%`,
                      background: "linear-gradient(90deg, #f59e0b, #ef4444, #8b5cf6)",
                      borderRadius: 12,
                      transition: "width 0.6s ease-out",
                      position: "relative",
                    }}
                  >
                    <div style={{
                      position: "absolute", inset: 0, borderRadius: 12,
                      background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent)",
                      animation: "shimmer 1.5s infinite",
                    }} />
                  </div>
                </div>
                <span style={{
                  fontSize: 12, fontWeight: 600, color: "var(--text-secondary)",
                  whiteSpace: "nowrap", minWidth: 80, textAlign: "right",
                }}>
                  {composeProgress
                    ? `${composeProgress.percent}% (${composeProgress.rendered}/${composeProgress.total})`
                    : "准备中..."}
                </span>
                <button
                  className="btn-secondary"
                  onClick={async () => {
                    try {
                      const updated = await episodeApi.resetStatus(episode.id);
                      onEpisodeUpdate(updated);
                      addToast("success", "已重置为 PRODUCTION 状态");
                    } catch (err: unknown) {
                      addToast("error", err instanceof Error ? err.message : "重置失败");
                    }
                  }}
                  style={{
                    fontSize: 11, padding: "4px 10px",
                    color: "#ef4444", borderColor: "#ef4444",
                  }}
                >
                  ⏹ 重置
                </button>
                <style>{`@keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }`}</style>
              </div>
            )}
            {episode.status === "COMPLETED" && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {episode.final_video_path && (
                  <a
                    href={`/media/${episode.final_video_path}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-primary"
                    style={{
                      textDecoration: "none", fontSize: 13,
                      background: "linear-gradient(135deg, #10b981, #059669)",
                    }}
                  >
                    🎬 播放最终视频
                  </a>
                )}
                <button
                  className="btn-secondary"
                  onClick={async () => {
                    if (!(await ensureWorker())) return;
                    await composeFinal(project.id, episode.id);
                    const updatedEp = await episodeApi.get(episode.id);
                    onEpisodeUpdate(updatedEp);
                    addToast("success", "已重新触发合成");
                  }}
                  disabled={loading}
                  style={{ fontSize: 12, padding: "6px 14px" }}
                >
                  🔄 重新合成
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Episode Script Preview */}
      {episode.full_script && (
        <details style={{ marginBottom: 24 }}>
          <summary style={{
            cursor: "pointer", fontSize: 14, fontWeight: 600,
            color: "var(--text-primary)", padding: "8px 0",
          }}>
            📜 查看本集剧本
          </summary>
          <div
            className="glass-panel"
            style={{
              maxHeight: 300, overflow: "auto",
              fontSize: 12, lineHeight: 1.7, color: "var(--text-secondary)",
              whiteSpace: "pre-wrap", padding: 16, marginTop: 8,
            }}
          >
            {episode.full_script}
          </div>
        </details>
      )}

      {/* Scenes Grid */}
      {scenes.length === 0 ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--text-muted)" }}>
          <p style={{ fontSize: 48, marginBottom: 16 }}>🎬</p>
          <p>本集暂未生成分镜</p>
        </div>
      ) : (
        <div>
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginBottom: 16,
          }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
              分镜 ({scenes.length})
            </h3>
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
            gap: 16,
          }}>
            {scenes.map((scene, index) => (
              <SceneCard key={scene.id} scene={scene} index={index} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
