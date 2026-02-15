"use client";

import { type Project } from "@/lib/api";
import { useProjectStore } from "@/stores/useProjectStore";
import SceneCard from "@/components/SceneCard";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
} from "@dnd-kit/sortable";
import { useEffect } from "react";
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
    reorderScenes,
    updateSceneLocally,
    refreshCurrentProject,
    loading,
  } = useProjectStore();

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  );

  // WebSocket for real-time updates
  useEffect(() => {
    const conn = connectProjectWS(project.id, (msg: WSMessage) => {
      if (msg.type === "scene_update" && msg.scene_id && msg.status) {
        updateSceneLocally(msg.scene_id, { status: msg.status });
      }
      if (msg.type === "project_update") {
        refreshCurrentProject();
      }
    });
    return () => conn.close();
  }, [project.id, updateSceneLocally, refreshCurrentProject]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = scenes.findIndex((s) => s.id === active.id);
    const newIndex = scenes.findIndex((s) => s.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const newOrder = [...scenes];
    const [moved] = newOrder.splice(oldIndex, 1);
    newOrder.splice(newIndex, 0, moved);
    reorderScenes(project.id, newOrder.map((s) => s.id));
  };

  const phase = PHASE_ACTIONS[project.status];

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
          {project.status !== "COMPLETED" && project.status !== "PRODUCTION" && (
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
        </div>
      )}

      {/* Scene Grid */}
      {scenes.length > 0 ? (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={scenes.map((s) => s.id)} strategy={rectSortingStrategy}>
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
          </SortableContext>
        </DndContext>
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
