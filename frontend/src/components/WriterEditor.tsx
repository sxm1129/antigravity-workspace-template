"use client";

import { type Project } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import { useState, useEffect, useRef } from "react";

const STATUS_INFO: Record<string, { title: string; description: string; action: string }> = {
  DRAFT: {
    title: "第一步: 构思故事",
    description: "填写你的故事标题和一句话梗概(Logline), 然后让 AI 生成世界观大纲。",
    action: "生成世界观大纲",
  },
  OUTLINE_REVIEW: {
    title: "第二步: 审阅大纲",
    description: "审阅 AI 生成的世界观大纲, 确认后生成完整剧本。可以在下方编辑修改。",
    action: "确认大纲, 生成剧本",
  },
  SCRIPT_REVIEW: {
    title: "第三步: 审阅剧本",
    description: "审阅完整剧本, 确认后解析成分镜画面。可以在下方编辑修改。",
    action: "确认剧本, 解析分镜",
  },
};

const ALL_STEPS = ["DRAFT", "OUTLINE_REVIEW", "SCRIPT_REVIEW", "STORYBOARD", "PRODUCTION", "COMPOSING", "COMPLETED"];

export default function WriterEditor({ project }: { project: Project }) {
  const { generateOutline, generateScript, parseScenes, saveProjectContent, rollbackToWriter, loading, error } = useProjectStore();
  const [localOutline, setLocalOutline] = useState(project.world_outline || "");
  const [localScript, setLocalScript] = useState(project.full_script || "");
  const [scriptExpanded, setScriptExpanded] = useState(false);
  const info = STATUS_INFO[project.status];

  // Whether we're past the writing phase
  const isReadOnly = !info;

  // Track last synced project ID to properly reset on project switch (BUG-5 fix)
  const lastProjectId = useRef(project.id);

  useEffect(() => {
    // Sync local state when project data changes or project switches
    if (project.id !== lastProjectId.current) {
      // Project switched — reset everything
      setLocalOutline(project.world_outline || "");
      setLocalScript(project.full_script || "");
      setScriptExpanded(false);
      lastProjectId.current = project.id;
    } else {
      // Same project but data refreshed (e.g., from API call) — sync only empty fields
      if (project.world_outline && !localOutline) {
        setLocalOutline(project.world_outline);
      }
      if (project.full_script && !localScript) {
        setLocalScript(project.full_script);
      }
    }
  }, [project.id, project.world_outline, project.full_script]);

  const handleAction = async () => {
    switch (project.status) {
      case "DRAFT":
        await generateOutline(project.id);
        break;
      case "OUTLINE_REVIEW":
        // BUG-2 FIX: Save user edits to backend BEFORE generating script
        await saveProjectContent(project.id, {
          world_outline: localOutline,
        });
        await generateScript(project.id);
        break;
      case "SCRIPT_REVIEW":
        // BUG-2 FIX: Save user edits to backend BEFORE parsing scenes
        await saveProjectContent(project.id, {
          full_script: localScript,
        });
        await parseScenes(project.id);
        break;
    }
  };

  const handleRollback = async () => {
    if (!confirm("确定要回退到编剧模式吗？这将允许你重新编辑剧本。")) return;
    await rollbackToWriter(project.id);
  };

  // ── Pipeline Progress Bar (shared between edit & read-only mode) ──
  const pipelineBar = (
    <div style={{ display: "flex", gap: 4, marginBottom: 32 }}>
      {ALL_STEPS.map((step, i) => {
        const currentIdx = ALL_STEPS.indexOf(project.status);
        const isActive = i === currentIdx;
        const isDone = i < currentIdx;
        return (
          <div
            key={step}
            style={{
              flex: 1,
              height: 4,
              borderRadius: 2,
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
  // READ-ONLY MODE — display content as cards
  // ══════════════════════════════════════════════
  if (isReadOnly) {
    return (
      <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
        {/* Header with re-edit button */}
        <div
          className="glass-panel"
          style={{
            padding: 24,
            marginBottom: 32,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "linear-gradient(135deg, rgba(16,185,129,0.08), rgba(99,102,241,0.08))",
            border: "1px solid rgba(16,185,129,0.2)",
          }}
        >
          <div>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: "var(--accent-success)", marginBottom: 6 }}>
              ✅ 编剧阶段已完成
            </h3>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              大纲和剧本已锁定。如需修改，可点击「重新编辑」回到编剧模式。
            </p>
          </div>
          <button
            className="btn-primary"
            onClick={handleRollback}
            disabled={loading}
            style={{
              flexShrink: 0,
              marginLeft: 24,
              background: "rgba(255,255,255,0.08)",
              border: "1px solid var(--border)",
              color: "var(--text-primary)",
            }}
          >
            {loading ? <span className="spinner" /> : null}
            🔄 重新编辑剧本
          </button>
        </div>

        {/* Pipeline Progress */}
        {pipelineBar}

        {/* Logline Card */}
        {project.logline && (
          <div style={{ marginBottom: 24 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8, display: "block" }}>
              故事梗概 (Logline)
            </label>
            <div
              style={{
                padding: "14px 16px",
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)",
                fontSize: 14,
                color: "var(--text-secondary)",
                lineHeight: 1.6,
                fontStyle: "italic",
              }}
            >
              {project.logline}
            </div>
          </div>
        )}

        {/* World Outline Read-Only Card */}
        {project.world_outline && (
          <div style={{ marginBottom: 24 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8, display: "block" }}>
              世界观大纲
            </label>
            <div
              className="glass-panel"
              style={{
                padding: "20px 24px",
                fontSize: 14,
                color: "var(--text-secondary)",
                lineHeight: 1.8,
                whiteSpace: "pre-wrap",
                maxHeight: 300,
                overflowY: "auto",
              }}
            >
              {project.world_outline}
            </div>
          </div>
        )}

        {/* Full Script Read-Only Card (collapsible) */}
        {project.full_script && (
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 8,
              }}
            >
              <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                完整剧本
              </label>
              <button
                onClick={() => setScriptExpanded(!scriptExpanded)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--accent-primary)",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 500,
                  padding: "4px 8px",
                }}
              >
                {scriptExpanded ? "▲ 收起" : "▼ 展开全文"}
              </button>
            </div>
            <div
              className="glass-panel"
              style={{
                padding: "20px 24px",
                fontSize: 14,
                color: "var(--text-secondary)",
                lineHeight: 1.8,
                whiteSpace: "pre-wrap",
                maxHeight: scriptExpanded ? "none" : 200,
                overflow: scriptExpanded ? "visible" : "hidden",
                position: "relative",
                transition: "max-height 0.3s ease",
              }}
            >
              {project.full_script}
              {!scriptExpanded && (
                <div
                  style={{
                    position: "absolute",
                    bottom: 0,
                    left: 0,
                    right: 0,
                    height: 60,
                    background: "linear-gradient(transparent, var(--bg-primary))",
                    pointerEvents: "none",
                  }}
                />
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // ══════════════════════════════════════════════
  // EDIT MODE — original interactive editor
  // ══════════════════════════════════════════════
  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: "32px 24px" }}>
      {/* Stage Gate Header */}
      <div
        className="glass-panel"
        style={{
          padding: 24,
          marginBottom: 32,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
            {info.title}
          </h3>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5 }}>
            {info.description}
          </p>
        </div>
        <button
          className="btn-primary pulse-glow"
          onClick={handleAction}
          disabled={loading}
          style={{ flexShrink: 0, marginLeft: 24 }}
        >
          {loading ? <span className="spinner" /> : null}
          {info.action}
        </button>
      </div>

      {/* Pipeline Progress */}
      {pipelineBar}

      {/* Logline Display */}
      {project.logline && (
        <div style={{ marginBottom: 24 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8, display: "block" }}>
            故事梗概 (Logline)
          </label>
          <div
            style={{
              padding: "14px 16px",
              background: "var(--bg-card)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              fontSize: 14,
              color: "var(--text-secondary)",
              lineHeight: 1.6,
              fontStyle: "italic",
            }}
          >
            {project.logline}
          </div>
        </div>
      )}

      {/* World Outline Editor */}
      {(project.status === "OUTLINE_REVIEW" || project.status === "SCRIPT_REVIEW") && (
        <div style={{ marginBottom: 24 }} className="fade-in">
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8, display: "block" }}>
            世界观大纲
          </label>
          <textarea
            className="textarea-field"
            value={localOutline}
            onChange={(e) => setLocalOutline(e.target.value)}
            readOnly={project.status === "SCRIPT_REVIEW"}
            style={{
              minHeight: 200,
              fontFamily: '"JetBrains Mono", "SF Mono", monospace',
              fontSize: 13,
              lineHeight: 1.7,
              opacity: project.status === "SCRIPT_REVIEW" ? 0.6 : 1,
            }}
          />
        </div>
      )}

      {/* Full Script Editor */}
      {project.status === "SCRIPT_REVIEW" && project.full_script && (
        <div className="fade-in">
          <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8, display: "block" }}>
            完整剧本
          </label>
          <textarea
            className="textarea-field"
            value={localScript}
            onChange={(e) => setLocalScript(e.target.value)}
            style={{
              minHeight: 400,
              fontFamily: '"JetBrains Mono", "SF Mono", monospace',
              fontSize: 13,
              lineHeight: 1.7,
            }}
          />
        </div>
      )}

      {/* Placeholder for DRAFT */}
      {project.status === "DRAFT" && (
        <div
          style={{
            padding: 60,
            textAlign: "center",
            border: "2px dashed var(--border)",
            borderRadius: "var(--radius-lg)",
            color: "var(--text-muted)",
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>✨</div>
          <p style={{ fontSize: 14 }}>点击上方按钮, AI 将根据你的 Logline 生成世界观大纲</p>
        </div>
      )}
    </div>
  );
}
