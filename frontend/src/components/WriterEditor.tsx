"use client";

import { type Project, styleApi } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import { useRouter } from "next/navigation";
import { useState, useEffect, useRef } from "react";

/* ── Writer pipeline steps (only the writer-relevant ones) ── */
const WRITER_STEPS = ["DRAFT", "OUTLINE_REVIEW"];

const STATUS_INFO: Record<string, { label: string; description: string; action: string }> = {
  DRAFT: {
    label: "草案阶段",
    description: "输入故事灵感（logline），AI 将生成世界观大纲。",
    action: "生成世界观大纲",
  },
  OUTLINE_REVIEW: {
    label: "大纲审核",
    description: "审核并编辑世界观大纲，确认后将提取剧集并批量生成剧本。",
    action: "确认大纲，批量生成剧本",
  },
};

/* ── Episode status labels ── */
const EPISODE_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  SCRIPT_GENERATING: { label: "剧本生成中", color: "#f0ad4e" },
  SCRIPT_REVIEW: { label: "剧本待审核", color: "var(--accent-primary)" },
  STORYBOARD: { label: "分镜就绪", color: "#5bc0de" },
  PRODUCTION: { label: "制作中", color: "#d9534f" },
  COMPOSING: { label: "合成中", color: "#f0ad4e" },
  COMPLETED: { label: "已完成", color: "var(--accent-success)" },
};

/* ── All project pipeline steps for the progress bar ── */
const ALL_STEPS = [
  "DRAFT", "OUTLINE_REVIEW", "IN_PRODUCTION", "COMPLETED",
];

export default function WriterEditor({ project }: { project: Project }) {
  const router = useRouter();
  const {
    generateOutline, regenerateOutline, extractAndGenerate, parseEpisodeScenes,
    saveProjectContent, rollbackToWriter, episodes, loading, error,
  } = useProjectStore();

  const [localOutline, setLocalOutline] = useState(project.world_outline || "");
  const [expandedEpisode, setExpandedEpisode] = useState<string | null>(null);
  const [showPromptEditor, setShowPromptEditor] = useState(false);
  const [customPrompt, setCustomPrompt] = useState("");
  const [defaultPrompt, setDefaultPrompt] = useState("");
  const [promptLoading, setPromptLoading] = useState(false);
  const info = STATUS_INFO[project.status];

  // Whether we're past the writer phase (episodes created)
  const isEpisodePhase = !info && (project.status === "IN_PRODUCTION" || project.status === "COMPLETED");
  // Legacy read-only states
  const isLegacyReadOnly = !info && !isEpisodePhase;

  const lastProjectId = useRef(project.id);

  useEffect(() => {
    if (project.id !== lastProjectId.current) {
      setLocalOutline(project.world_outline || "");
      setExpandedEpisode(null);
      lastProjectId.current = project.id;
    } else {
      if (project.world_outline && !localOutline) {
        setLocalOutline(project.world_outline);
      }
    }
  }, [project.id, project.world_outline]);

  const handleAction = async () => {
    switch (project.status) {
      case "DRAFT":
        await generateOutline(project.id);
        break;
      case "OUTLINE_REVIEW":
        // Save edits before extracting episodes
        await saveProjectContent(project.id, { world_outline: localOutline });
        await extractAndGenerate(project.id);
        break;
    }
  };

  const handleRegenerate = async (prompt?: string) => {
    await regenerateOutline(project.id, prompt || undefined);
    // Sync local outline after regeneration
    const updated = useProjectStore.getState().currentProject;
    if (updated?.world_outline) setLocalOutline(updated.world_outline);
  };

  const handleTogglePromptEditor = async () => {
    const willOpen = !showPromptEditor;
    setShowPromptEditor(willOpen);
    if (willOpen && !defaultPrompt) {
      setPromptLoading(true);
      try {
        const style = project.style_preset || "default";
        const res = await styleApi.getPromptTemplate(style, "outline");
        setDefaultPrompt(res.content);
        setCustomPrompt(res.content);
      } catch {
        setCustomPrompt("(Failed to load prompt template)");
      } finally {
        setPromptLoading(false);
      }
    }
  };

  const handleRollback = async () => {
    if (!confirm("确定要回退到大纲审核阶段吗？")) return;
    await rollbackToWriter(project.id);
  };

  const handleParseScenes = async (episodeId: string) => {
    if (!confirm("确认剧本，开始解析分镜？")) return;
    await parseEpisodeScenes(episodeId);
  };

  // ── Pipeline Progress Bar ──
  const pipelineBar = (
    <div style={{ display: "flex", gap: 4, marginBottom: 32 }}>
      {ALL_STEPS.map((step, i) => {
        const currentIdx = ALL_STEPS.indexOf(project.status);
        const isActive = i === currentIdx;
        const isDone = i < currentIdx || (currentIdx === -1 && project.status === "COMPLETED");
        return (
          <div
            key={step}
            style={{
              flex: 1, height: 4, borderRadius: 2,
              background: isDone
                ? "var(--accent-success)"
                : isActive
                ? "linear-gradient(90deg, var(--accent-primary), var(--accent-primary-light))"
                : "var(--border)",
              transition: "all 0.3s ease",
            }}
          />
        );
      })}
    </div>
  );

  // ══════════════════════════════════════════════
  // EPISODE PHASE — show outline + episode cards
  // ══════════════════════════════════════════════
  if (isEpisodePhase) {
    return (
      <div style={{ maxWidth: 1000, margin: "0 auto", padding: "32px 24px" }}>
        {/* Header */}
        <div
          className="glass-panel"
          style={{
            padding: 24, marginBottom: 32,
            display: "flex", alignItems: "center", justifyContent: "space-between",
            background: "linear-gradient(135deg, rgba(46,160,67,0.15), rgba(46,160,67,0.05))",
          }}
        >
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--accent-success)" }}>
              剧集制作中
            </h2>
            <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
              {episodes.length} 集剧本已生成，点击剧集卡片进入导演看板
            </p>
          </div>
          <button
            className="btn-secondary"
            onClick={handleRollback}
            disabled={loading}
            style={{ fontSize: 13 }}
          >
            🔄 回退到大纲
          </button>
        </div>

        {pipelineBar}

        {/* World Outline Card (collapsible) */}
        <div
          className="glass-panel"
          style={{ padding: 20, marginBottom: 24 }}
        >
          <h3 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 8 }}>
            📖 世界观大纲
          </h3>
          <div
            style={{
              maxHeight: 200, overflow: "auto",
              fontSize: 13, lineHeight: 1.8, color: "var(--text-secondary)",
              whiteSpace: "pre-wrap", padding: "0 4px",
            }}
          >
            {project.world_outline || "暂无大纲"}
          </div>
        </div>

        {/* Episode Cards Grid */}
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: "var(--text-primary)" }}>
          📺 剧集列表
        </h3>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 16 }}>
          {episodes.map((ep) => {
            const statusInfo = EPISODE_STATUS_LABELS[ep.status] || { label: ep.status, color: "var(--text-muted)" };
            const isExpanded = expandedEpisode === ep.id;
            const canParseScenes = ep.status === "SCRIPT_REVIEW" && ep.full_script;
            const canNavigate = ["STORYBOARD", "PRODUCTION", "COMPOSING", "COMPLETED"].includes(ep.status);

            return (
              <div
                key={ep.id}
                className="glass-panel"
                style={{
                  padding: 20,
                  cursor: canNavigate ? "pointer" : "default",
                  transition: "all 0.2s ease",
                  border: canNavigate ? "1px solid transparent" : undefined,
                }}
                onMouseEnter={(e) => {
                  if (canNavigate) (e.currentTarget as HTMLDivElement).style.borderColor = "var(--accent-primary)";
                }}
                onMouseLeave={(e) => {
                  if (canNavigate) (e.currentTarget as HTMLDivElement).style.borderColor = "transparent";
                }}
                onClick={() => {
                  if (canNavigate) router.push(`/project/${project.id}/episode/${ep.id}`);
                }}
              >
                {/* Episode Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h4 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>
                    第{ep.episode_number}集：{ep.title}
                  </h4>
                  <span
                    style={{
                      fontSize: 11, fontWeight: 600,
                      padding: "3px 8px", borderRadius: 12,
                      background: `${statusInfo.color}22`,
                      color: statusInfo.color,
                    }}
                  >
                    {statusInfo.label}
                  </span>
                </div>

                {/* Synopsis */}
                {ep.synopsis && (
                  <p style={{
                    fontSize: 12, color: "var(--text-muted)",
                    lineHeight: 1.6, marginBottom: 12,
                    display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
                  }}>
                    {ep.synopsis}
                  </p>
                )}

                {/* Scenes count */}
                {ep.scenes_count != null && ep.scenes_count > 0 && (
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
                    🎬 {ep.scenes_count} 个分镜
                  </div>
                )}

                {/* Script toggle */}
                {ep.full_script && (
                  <button
                    className="btn-ghost"
                    style={{ fontSize: 12, padding: "4px 8px", marginBottom: isExpanded ? 8 : 0 }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setExpandedEpisode(isExpanded ? null : ep.id);
                    }}
                  >
                    {isExpanded ? "▲ 收起剧本" : "▼ 查看剧本"}
                  </button>
                )}

                {isExpanded && ep.full_script && (
                  <div
                    style={{
                      maxHeight: 300, overflow: "auto",
                      fontSize: 12, lineHeight: 1.7, color: "var(--text-secondary)",
                      whiteSpace: "pre-wrap", padding: 12,
                      background: "var(--bg-primary)", borderRadius: 8,
                      marginTop: 8,
                    }}
                  >
                    {ep.full_script}
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: 8, marginTop: 12 }} onClick={(e) => e.stopPropagation()}>
                  {canParseScenes && (
                    <button
                      className="btn-primary"
                      style={{ fontSize: 12, padding: "6px 12px" }}
                      disabled={loading}
                      onClick={() => handleParseScenes(ep.id)}
                    >
                      {loading ? "解析中..." : "确认剧本，解析分镜"}
                    </button>
                  )}
                  {canNavigate && (
                    <button
                      className="btn-primary"
                      style={{ fontSize: 12, padding: "6px 12px" }}
                      onClick={() => router.push(`/project/${project.id}/episode/${ep.id}`)}
                    >
                      进入看板 →
                    </button>
                  )}
                </div>

                {/* Video preview */}
                {ep.status === "COMPLETED" && ep.final_video_path && (
                  <div style={{ marginTop: 12, borderRadius: 8, overflow: "hidden" }}>
                    <video
                      src={`/media/${ep.final_video_path}`}
                      controls
                      style={{ width: "100%", borderRadius: 8 }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // ══════════════════════════════════════════════
  // LEGACY READ-ONLY — for old projects using flat script
  // ══════════════════════════════════════════════
  if (isLegacyReadOnly) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
        <div className="glass-panel" style={{ padding: 24, marginBottom: 32, textAlign: "center" }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "var(--accent-success)" }}>
            ✅ 编剧阶段已完成
          </h2>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
            请切换到导演看板查看分镜和制作进度
          </p>
        </div>
        {pipelineBar}
      </div>
    );
  }

  // ══════════════════════════════════════════════
  // INTERACTIVE EDITING MODE (DRAFT / OUTLINE_REVIEW)
  // ══════════════════════════════════════════════
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
      {/* Stage Header */}
      <div
        className="glass-panel"
        style={{
          padding: 24, marginBottom: 32,
          background: "linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.02))",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <span style={{
            fontSize: 11, fontWeight: 600, padding: "3px 10px",
            borderRadius: 100, background: "var(--accent-primary)", color: "#fff",
          }}>
            {info?.label}
          </span>
        </div>
        <p style={{ fontSize: 13, color: "var(--text-muted)" }}>{info?.description}</p>
      </div>

      {pipelineBar}

      {/* Logline (always visible) */}
      {project.logline && (
        <div className="glass-panel" style={{ padding: 16, marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-muted)", marginBottom: 8 }}>
            故事灵感
          </h3>
          <p style={{ fontSize: 14, fontStyle: "italic", color: "var(--text-primary)", lineHeight: 1.6 }}>
            {project.logline}
          </p>
        </div>
      )}

      {/* World Outline Editor */}
      {project.status === "OUTLINE_REVIEW" && (
        <div className="glass-panel" style={{ padding: 20, marginBottom: 24 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 12 }}>
            世界观大纲
          </h3>
          <textarea
            value={localOutline}
            onChange={(e) => setLocalOutline(e.target.value)}
            placeholder="AI 生成的世界观大纲将在此显示..."
            style={{
              width: "100%", minHeight: 400, padding: 16,
              background: "var(--bg-primary)", border: "1px solid var(--border)",
              borderRadius: 8, color: "var(--text-primary)",
              fontSize: 13, lineHeight: 1.8, resize: "vertical",
              fontFamily: "inherit",
            }}
          />
        </div>
      )}

      {/* Prompt Editor Panel (OUTLINE_REVIEW only) */}
      {project.status === "OUTLINE_REVIEW" && (
        <div className="glass-panel" style={{ padding: 16, marginBottom: 24 }}>
          <button
            className="btn-ghost"
            onClick={handleTogglePromptEditor}
            style={{
              fontSize: 13, fontWeight: 600, color: "var(--text-secondary)",
              display: "flex", alignItems: "center", gap: 6,
              padding: 0, background: "none", border: "none", cursor: "pointer",
            }}
          >
            {showPromptEditor ? "▲" : "▼"} 调整提示词
          </button>

          {showPromptEditor && (
            <div style={{ marginTop: 12 }}>
              {promptLoading ? (
                <div style={{ fontSize: 13, color: "var(--text-muted)", padding: 16, textAlign: "center" }}>
                  正在加载提示词模板...
                </div>
              ) : (
                <>
                  <textarea
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder="系统提示词模板..."
                    style={{
                      width: "100%", minHeight: 180, padding: 12,
                      background: "var(--bg-primary)", border: "1px solid var(--border)",
                      borderRadius: 8, color: "var(--text-primary)",
                      fontSize: 12, lineHeight: 1.7, resize: "vertical",
                      fontFamily: "monospace",
                    }}
                  />
                  <div style={{ display: "flex", gap: 8, marginTop: 10, justifyContent: "flex-end" }}>
                    <button
                      className="btn-ghost"
                      onClick={() => setCustomPrompt(defaultPrompt)}
                      disabled={loading}
                      style={{ fontSize: 12, padding: "6px 12px" }}
                    >
                      重置为默认
                    </button>
                    <button
                      className="btn-primary"
                      onClick={() => handleRegenerate(customPrompt)}
                      disabled={loading}
                      style={{ fontSize: 12, padding: "6px 14px" }}
                    >
                      {loading ? "生成中..." : "使用此提示词重新生成"}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{
          padding: "10px 16px", marginBottom: 16,
          background: "rgba(255,92,92,0.1)", borderRadius: 8,
          color: "var(--accent-danger)", fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Action Buttons */}
      <div style={{ display: "flex", gap: 12 }}>
        {project.status === "OUTLINE_REVIEW" && (
          <button
            className="btn-secondary"
            onClick={() => handleRegenerate()}
            disabled={loading}
            style={{
              padding: "14px 24px",
              fontSize: 14, fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            {loading ? "生成中..." : "重新生成"}
          </button>
        )}
        <button
          className="btn-primary"
          onClick={handleAction}
          disabled={loading}
          style={{
            flex: 1, padding: "14px 24px",
            fontSize: 15, fontWeight: 600,
          }}
        >
          {loading ? (
            <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              <span className="spinner" style={{ width: 16, height: 16 }} />
              AI 正在创作中...
            </span>
          ) : (
            info?.action
          )}
        </button>
      </div>
    </div>
  );
}
