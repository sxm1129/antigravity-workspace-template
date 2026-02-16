"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { useProjectStore } from "@/stores/useProjectStore";
import { episodeApi, type Episode, type Scene } from "@/lib/api";
import KanbanBoard from "@/components/KanbanBoard";

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

      {/* Content: Reuse KanbanBoard with filtered scenes */}
      <div style={{ flex: 1, overflow: "auto" }}>
        <EpisodeKanbanContent
          project={currentProject}
          episode={episode}
          scenes={episodeScenes}
          onScenesUpdate={(scenes) => setEpisodeScenes(scenes)}
        />
      </div>
    </div>
  );
}

/* ── Inline Episode Kanban Content ── */
function EpisodeKanbanContent({
  project, episode, scenes, onScenesUpdate,
}: {
  project: { id: string; title: string; status: string };
  episode: Episode;
  scenes: Scene[];
  onScenesUpdate: (scenes: Scene[]) => void;
}) {
  const { generateAllImages, approveScene, composeFinal, loading } = useProjectStore();

  const handleBatchAction = async (action: string) => {
    switch (action) {
      case "generate-images":
        // For episode, we'd need per-episode image gen — fallback to project-level for now
        await generateAllImages(project.id);
        break;
      case "compose":
        await composeFinal(project.id);
        break;
    }
    // Refresh episode scenes
    const updatedScenes = await episodeApi.listScenes(episode.id);
    onScenesUpdate(updatedScenes);
  };

  return (
    <div style={{ padding: "24px" }}>
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
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 16,
          }}>
            {scenes.map((scene) => (
              <div key={scene.id} className="glass-panel" style={{ padding: 16 }}>
                <div style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "center", marginBottom: 8,
                }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    镜头 {scene.sequence_order}
                  </span>
                  <span style={{
                    fontSize: 11, padding: "2px 8px", borderRadius: 8,
                    background: scene.status === "READY" ? "rgba(46,160,67,0.15)" : "rgba(99,102,241,0.15)",
                    color: scene.status === "READY" ? "var(--accent-success)" : "var(--accent-primary)",
                  }}>
                    {scene.status}
                  </span>
                </div>
                {scene.dialogue_text && (
                  <p style={{
                    fontSize: 12, color: "var(--text-secondary)",
                    lineHeight: 1.5, marginBottom: 8,
                    display: "-webkit-box", WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical", overflow: "hidden",
                  }}>
                    "{scene.dialogue_text}"
                  </p>
                )}
                {scene.local_image_path && (
                  <img
                    src={`/media/${scene.local_image_path}`}
                    alt={`Scene ${scene.sequence_order}`}
                    style={{ width: "100%", borderRadius: 8, marginTop: 8 }}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
