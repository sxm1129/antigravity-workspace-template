"use client";
/**
 * VideoEditor — Full-screen video composition editor.
 *
 * Auto-detects compose provider:
 * - Remotion: Renders @remotion/player inline with ComicDrama composition
 * - FFmpeg: Shows scene list + one-click render button
 *
 * Remotion compositions are copied into src/remotion-compositions/
 * and lazy-loaded to avoid SSR issues.
 */

import React, { useEffect, useState, useCallback } from "react";
import { Player } from "@remotion/player";
import type { ComicDramaProps } from "@/remotion-compositions/types";
import { useRenderStore } from "@/stores/useRenderStore";

// Lazy-load ComicDrama to avoid SSR issues with Remotion
const LazyComicDrama = React.lazy(() =>
  import("@/remotion-compositions/ComicDrama").then((mod) => ({
    default: mod.ComicDrama,
  }))
);

interface VideoEditorProps {
  projectId: string;
}

export default function VideoEditor({ projectId }: VideoEditorProps) {
  const {
    providerInfo,
    providerLoading,
    previewProps,
    propsLoading,
    renderStatus,
    renderResult,
    renderError,
    fetchProvider,
    fetchPreviewProps,
    updatePreviewProps,
    startRender,
  } = useRenderStore();

  const [selectedSceneIdx, setSelectedSceneIdx] = useState<number | null>(null);

  useEffect(() => {
    fetchProvider();
  }, [fetchProvider]);

  useEffect(() => {
    if (providerInfo?.supports_preview) {
      fetchPreviewProps(projectId);
    }
  }, [providerInfo, projectId, fetchPreviewProps]);

  const handleRender = useCallback(() => {
    const title = (previewProps?.title as string) || "";
    const style = (previewProps?.style as string) || "default";
    startRender(projectId, { title, style });
  }, [projectId, previewProps, startRender]);

  const handleTransitionChange = useCallback(
    (sceneIdx: number, transition: string) => {
      if (!previewProps) return;
      const scenes = [...(previewProps.scenes as Array<Record<string, unknown>>)];
      scenes[sceneIdx] = { ...scenes[sceneIdx], transition };
      updatePreviewProps({ ...previewProps, scenes });
    },
    [previewProps, updatePreviewProps]
  );

  if (providerLoading) {
    return (
      <div style={styles.loading}>
        <div style={styles.spinner} />
        <p>检测渲染引擎...</p>
      </div>
    );
  }

  const isRemotion = providerInfo?.supports_preview;
  const scenes = (previewProps?.scenes as Array<Record<string, unknown>>) || [];

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <h1 style={styles.title}>视频合成编辑器</h1>
        <div style={styles.headerRight}>
          <span style={styles.providerBadge}>
            {providerInfo?.provider === "remotion" ? "🎬 Remotion" : "⚡ FFmpeg"}
          </span>
          <button
            style={{
              ...styles.renderBtn,
              opacity: renderStatus === "rendering" ? 0.6 : 1,
            }}
            onClick={handleRender}
            disabled={renderStatus === "rendering"}
          >
            {renderStatus === "rendering"
              ? "渲染中..."
              : renderStatus === "done"
                ? "重新渲染"
                : "开始渲染"}
          </button>
        </div>
      </div>

      {/* Status bar */}
      {renderStatus === "done" && renderResult && (
        <div style={styles.successBar}>
          渲染完成: {renderResult.output_path} (via {renderResult.provider})
        </div>
      )}
      {renderStatus === "error" && renderError && (
        <div style={styles.errorBar}>渲染失败: {renderError}</div>
      )}

      <div style={styles.mainLayout}>
        {/* Left: Preview */}
        <div style={styles.previewPanel}>
          {isRemotion && previewProps && !propsLoading ? (
            <React.Suspense
              fallback={
                <div style={styles.previewPlaceholder}>加载预览组件...</div>
              }
            >
              <Player
                component={LazyComicDrama as unknown as React.LazyExoticComponent<React.FC<Record<string, unknown>>>}
                inputProps={previewProps as unknown as ComicDramaProps}
                durationInFrames={calculateTotalFrames(previewProps)}
                fps={(previewProps.fps as number) || 24}
                compositionWidth={(previewProps.width as number) || 1920}
                compositionHeight={(previewProps.height as number) || 1080}
                style={{ width: "100%", aspectRatio: "16/9", borderRadius: 8 }}
                controls
                autoPlay={false}
              />
            </React.Suspense>
          ) : (
            <div style={styles.previewPlaceholder}>
              {propsLoading ? (
                "加载预览数据..."
              ) : (
                <>
                  <p style={{ fontSize: 48, margin: 0 }}>⚡</p>
                  <p>FFmpeg 模式 — 无实时预览</p>
                  <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                    切换到 Remotion 渲染引擎以启用实时预览
                  </p>
                </>
              )}
            </div>
          )}
        </div>

        {/* Right: Timeline + Properties */}
        <div style={styles.sidePanel}>
          <h3 style={styles.sectionTitle}>时间轴</h3>
          <div style={styles.timeline}>
            {scenes.length === 0 ? (
              <p style={{ color: "var(--text-muted)", padding: 16 }}>
                暂无场景数据
              </p>
            ) : (
              scenes.map((scene, i) => (
                <div
                  key={(scene.id as string) || i}
                  style={{
                    ...styles.timelineItem,
                    borderColor:
                      selectedSceneIdx === i
                        ? "var(--accent-primary)"
                        : "var(--border)",
                  }}
                  onClick={() => setSelectedSceneIdx(i)}
                >
                  <div style={styles.sceneNum}>S{i + 1}</div>
                  <div style={styles.sceneInfo}>
                    <span style={styles.sceneDuration}>
                      {((scene.durationInFrames as number) / ((previewProps?.fps as number) || 24)).toFixed(1)}s
                    </span>
                    {typeof scene.dialogue === "string" && scene.dialogue && (
                      <span style={styles.sceneDialogue}>
                        {scene.dialogue.slice(0, 20)}...
                      </span>
                    )}
                  </div>
                  <span style={styles.transitionTag}>
                    {(scene.transition as string) || "fade"}
                  </span>
                </div>
              ))
            )}
          </div>

          {/* Properties Panel */}
          {selectedSceneIdx !== null && scenes[selectedSceneIdx] && (
            <>
              <h3 style={styles.sectionTitle}>属性 — S{selectedSceneIdx + 1}</h3>
              <div style={styles.propsPanel}>
                <label style={styles.label}>转场效果</label>
                <select
                  style={styles.select}
                  value={(scenes[selectedSceneIdx].transition as string) || "fade"}
                  onChange={(e) =>
                    handleTransitionChange(selectedSceneIdx, e.target.value)
                  }
                >
                  <option value="fade">淡入淡出</option>
                  <option value="slide">滑动</option>
                  <option value="wipe">擦除</option>
                  <option value="dissolve">溶解</option>
                  <option value="none">无转场</option>
                </select>

                <label style={styles.label}>对白</label>
                <div style={styles.dialoguePreview}>
                  {(scenes[selectedSceneIdx].dialogue as string) || "（无对白）"}
                </div>

                <label style={styles.label}>气泡样式</label>
                <select
                  style={styles.select}
                  value={(scenes[selectedSceneIdx].bubbleStyle as string) || "normal"}
                  onChange={(e) => {
                    const updated = [...scenes];
                    updated[selectedSceneIdx] = {
                      ...updated[selectedSceneIdx],
                      bubbleStyle: e.target.value,
                    };
                    updatePreviewProps({ ...previewProps!, scenes: updated });
                  }}
                >
                  <option value="normal">普通</option>
                  <option value="think">思考泡</option>
                  <option value="shout">惊叹泡</option>
                  <option value="narration">旁白框</option>
                </select>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function calculateTotalFrames(props: Record<string, unknown>): number {
  const scenes = (props.scenes as Array<Record<string, unknown>>) || [];
  if (scenes.length === 0) return 1; // Remotion requires durationInFrames >= 1
  const sceneDuration = scenes.reduce(
    (sum, s) => sum + ((s.durationInFrames as number) || 120),
    0
  );
  return 72 + sceneDuration + 72; // title + scenes + credits
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles: Record<string, React.CSSProperties> = {
  container: {
    height: "calc(100vh - 56px)",
    display: "flex",
    flexDirection: "column",
    background: "var(--bg-primary, #0a0a1a)",
    color: "var(--text-primary, #e8e8f0)",
    overflow: "hidden",
  },
  loading: {
    height: "calc(100vh - 56px)",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    color: "var(--text-muted, #666)",
  },
  spinner: {
    width: 32,
    height: 32,
    border: "3px solid var(--border, #333)",
    borderTop: "3px solid var(--accent-primary, #6366f1)",
    borderRadius: "50%",
    animation: "spin 1s linear infinite",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 24px",
    borderBottom: "1px solid var(--border, #222)",
    flexShrink: 0,
  },
  title: {
    fontSize: 18,
    fontWeight: 700,
    margin: 0,
    letterSpacing: "-0.02em",
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: 12,
  },
  providerBadge: {
    fontSize: 12,
    padding: "4px 10px",
    borderRadius: 6,
    background: "var(--bg-secondary, #1a1a2e)",
    border: "1px solid var(--border, #333)",
    fontWeight: 600,
  },
  renderBtn: {
    padding: "8px 20px",
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg, #6366f1, #8b5cf6)",
    color: "#fff",
    fontWeight: 600,
    fontSize: 14,
    cursor: "pointer",
    transition: "opacity 0.2s",
  },
  successBar: {
    padding: "8px 24px",
    background: "rgba(16, 185, 129, 0.15)",
    color: "#10b981",
    fontSize: 13,
    borderBottom: "1px solid rgba(16, 185, 129, 0.3)",
  },
  errorBar: {
    padding: "8px 24px",
    background: "rgba(239, 68, 68, 0.15)",
    color: "#ef4444",
    fontSize: 13,
    borderBottom: "1px solid rgba(239, 68, 68, 0.3)",
  },
  mainLayout: {
    display: "flex",
    flex: 1,
    overflow: "hidden",
  },
  previewPanel: {
    flex: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    background: "#000",
  },
  previewPlaceholder: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
    aspectRatio: "16/9",
    maxWidth: 960,
    borderRadius: 12,
    border: "2px dashed var(--border, #333)",
    background: "var(--bg-secondary, #1a1a2e)",
    color: "var(--text-secondary, #aaa)",
    fontSize: 15,
    gap: 8,
  },
  sidePanel: {
    width: 320,
    borderLeft: "1px solid var(--border, #222)",
    overflowY: "auto",
    flexShrink: 0,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.1em",
    color: "var(--text-muted, #888)",
    padding: "12px 16px 8px",
    margin: 0,
    borderBottom: "1px solid var(--border, #222)",
  },
  timeline: {
    display: "flex",
    flexDirection: "column",
  },
  timelineItem: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 16px",
    borderBottom: "1px solid var(--border, #222)",
    borderLeft: "3px solid var(--border, #333)",
    cursor: "pointer",
    transition: "background 0.15s",
  },
  sceneNum: {
    fontSize: 12,
    fontWeight: 700,
    color: "var(--accent-primary, #6366f1)",
    minWidth: 28,
  },
  sceneInfo: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
  },
  sceneDuration: {
    fontSize: 12,
    color: "var(--text-secondary, #aaa)",
  },
  sceneDialogue: {
    fontSize: 11,
    color: "var(--text-muted, #666)",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  transitionTag: {
    fontSize: 10,
    padding: "2px 6px",
    borderRadius: 4,
    background: "var(--bg-secondary, #1a1a2e)",
    color: "var(--text-muted, #888)",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
  },
  propsPanel: {
    padding: 16,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "var(--text-muted, #888)",
    marginTop: 4,
  },
  select: {
    padding: "6px 10px",
    borderRadius: 6,
    border: "1px solid var(--border, #333)",
    background: "var(--bg-secondary, #1a1a2e)",
    color: "var(--text-primary, #e8e8f0)",
    fontSize: 13,
  },
  dialoguePreview: {
    padding: "8px 10px",
    borderRadius: 6,
    border: "1px solid var(--border, #333)",
    background: "var(--bg-secondary, #1a1a2e)",
    fontSize: 12,
    color: "var(--text-secondary, #aaa)",
    minHeight: 40,
    lineHeight: 1.5,
  },
};
