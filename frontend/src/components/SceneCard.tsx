"use client";

import { type Scene, mediaUrl } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";

const SCENE_STATUS: Record<string, { label: string; cls: string }> = {
  DRAFT: { label: "草稿", cls: "badge-ideation" },
  TTS_DONE: { label: "语音就绪", cls: "badge-generating" },
  IMAGE_DONE: { label: "图片就绪", cls: "badge-approval" },
  VIDEO_DONE: { label: "视频就绪", cls: "badge-ready" },
  APPROVED: { label: "已审核", cls: "badge-completed" },
  GENERATING: { label: "生成中", cls: "badge-rendering" },
};

export default function SceneCard({ scene, index }: { scene: Scene; index: number }) {
  const { approveScene } = useProjectStore();
  const status = SCENE_STATUS[scene.status] || { label: scene.status, cls: "badge-ideation" };

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: scene.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const imgSrc = mediaUrl(scene.local_image_path);
  const videoSrc = mediaUrl(scene.local_video_path);

  return (
    <div
      ref={setNodeRef}
      style={{
        ...style,
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        overflow: "hidden",
        transition: "all 0.2s ease",
      }}
      className="fade-in"
    >
      {/* Drag Handle */}
      <div
        {...attributes}
        {...listeners}
        style={{
          padding: "10px 16px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderBottom: "1px solid var(--border)",
          cursor: "grab",
          background: "var(--bg-secondary)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)", cursor: "grab" }}>⠿</span>
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

        {/* Action Buttons */}
        {scene.status === "IMAGE_DONE" && (
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
              onClick={(e) => e.stopPropagation()}
              style={{ padding: "8px 12px", fontSize: 12 }}
            >
              ↻ 重绘
            </button>
          </div>
        )}

        {scene.status === "GENERATING" && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            color: "var(--accent-primary-light)", fontSize: 12, fontWeight: 500,
            marginTop: 8,
          }}>
            <span className="spinner" style={{ width: 14, height: 14 }} />
            生成中...
          </div>
        )}
      </div>
    </div>
  );
}
