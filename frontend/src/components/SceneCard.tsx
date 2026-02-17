"use client";

import { type Scene, mediaUrl, assetApi } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";

const SCENE_STATUS: Record<string, { label: string; cls: string }> = {
  PENDING: { label: "待处理", cls: "badge-ideation" },
  GENERATING: { label: "生成中", cls: "badge-rendering" },
  REVIEW: { label: "待审核", cls: "badge-approval" },
  APPROVED: { label: "已审核", cls: "badge-completed" },
  VIDEO_GEN: { label: "视频生成中", cls: "badge-generating" },
  READY: { label: "就绪", cls: "badge-ready" },
  ERROR: { label: "出错", cls: "badge-error" },
};

export default function SceneCard({ scene, index }: { scene: Scene; index: number }) {
  const { approveScene, regenerateImage, regenerateScene, updateSceneLocally } = useProjectStore();
  const status = SCENE_STATUS[scene.status] || { label: scene.status, cls: "badge-ideation" };

  const imgSrc = mediaUrl(scene.local_image_path);
  const videoSrc = mediaUrl(scene.local_video_path);

  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
        transition: "all 0.2s ease",
      }}
      className="fade-in"
    >
      {/* Header */}
      <div
        style={{
          padding: "10px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>⠿</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
            镜头 {index + 1}
          </span>
        </div>
        <span className={`badge ${status.cls}`}>{status.label}</span>
      </div>

      {/* Media Preview */}
      <div style={{ position: "relative", aspectRatio: "16/9", background: "#0a0a10" }}>
        {videoSrc ? (
          <video
            src={videoSrc}
            controls
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : imgSrc ? (
          <img
            src={imgSrc}
            alt={`Scene ${index + 1}`}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-muted)",
              fontSize: 13,
            }}
          >
            等待生成...
          </div>
        )}
      </div>

      {/* Scene Details */}
      <div style={{ padding: 14 }}>
        {scene.dialogue_text && (
          <p
            style={{
              fontSize: 12,
              color: "var(--text-secondary)",
              lineHeight: 1.5,
              marginBottom: 8,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            🎤 {scene.dialogue_text}
          </p>
        )}

        {scene.prompt_visual && (
          <p
            style={{
              fontSize: 11,
              color: "var(--text-muted)",
              lineHeight: 1.4,
              marginBottom: 10,
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical",
              overflow: "hidden",
            }}
          >
            🎨 {scene.prompt_visual}
          </p>
        )}

        {/* Action Buttons — show when scene is in REVIEW status */}
        {scene.status === "REVIEW" && (
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              className="btn-success"
              onClick={(e) => {
                e.stopPropagation();
                approveScene(scene.id);
              }}
              style={{ flex: 1, justifyContent: "center", padding: "8px 12px", fontSize: 12 }}
            >
              ✓ 审核通过
            </button>
            <button
              className="btn-secondary"
              onClick={(e) => {
                e.stopPropagation();
                regenerateImage(scene.id);
              }}
              style={{ padding: "8px 12px", fontSize: 12 }}
            >
              ↻ 重绘
            </button>
          </div>
        )}

        {/* Generate button for PENDING scenes */}
        {scene.status === "PENDING" && (
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              className="btn-primary"
              onClick={(e) => {
                e.stopPropagation();
                regenerateScene(scene.id);
              }}
              style={{ flex: 1, justifyContent: "center", padding: "8px 12px", fontSize: 12 }}
            >
              🎨 生成素材
            </button>
          </div>
        )}

        {/* Regenerate button for READY / APPROVED scenes */}
        {(scene.status === "READY" || scene.status === "APPROVED") && (
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button
              className="btn-secondary"
              onClick={(e) => {
                e.stopPropagation();
                regenerateScene(scene.id);
              }}
              style={{ flex: 1, justifyContent: "center", padding: "8px 12px", fontSize: 12 }}
            >
              ↻ 重新生成
            </button>
          </div>
        )}

        {(scene.status === "GENERATING" || scene.status === "VIDEO_GEN") && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            color: "var(--accent-primary-light)", fontSize: 12, fontWeight: 500,
            marginTop: 8,
          }}>
            <span className="spinner" style={{ width: 14, height: 14 }} />
            {scene.status === "GENERATING" ? "素材生成中..." : "视频生成中..."}
          </div>
        )}

        {/* ERROR state — show error message and retry button */}
        {scene.status === "ERROR" && (
          <div style={{ marginTop: 8 }}>
            <div style={{
              padding: "8px 10px",
              background: "rgba(255,92,92,0.1)",
              border: "1px solid rgba(255,92,92,0.2)",
              borderRadius: 6,
              fontSize: 11,
              color: "#ff5c5c",
              lineHeight: 1.5,
              marginBottom: 8,
              wordBreak: "break-word",
            }}>
              {scene.error_message
                ? (scene.error_message.length > 120
                    ? scene.error_message.slice(0, 120) + "..."
                    : scene.error_message)
                : "生成失败，请重试"}
            </div>
            <button
              className="btn-primary"
              onClick={async (e) => {
                e.stopPropagation();
                await assetApi.resetScenes([scene.id]);
                // Optimistically update locally
                updateSceneLocally(scene.id, { status: "PENDING", error_message: null });
              }}
              style={{
                width: "100%", justifyContent: "center",
                padding: "8px 12px", fontSize: 12,
                background: "linear-gradient(135deg, #ef4444, #dc2626)",
              }}
            >
              ↻ 重置并重试
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
