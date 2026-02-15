"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { useProjectStore } from "@/stores/useProjectStore";
import WriterEditor from "@/components/WriterEditor";
import KanbanBoard from "@/components/KanbanBoard";

type PageParams = { id: string };

export default function ProjectDetailPage(props: { params: Promise<PageParams> }) {
  const resolvedParams = use(props.params);
  const projectId = resolvedParams.id;
  const router = useRouter();
  const { currentProject, fetchProject, loading, error } = useProjectStore();
  const [activeTab, setActiveTab] = useState<"writer" | "director">("writer");

  useEffect(() => {
    fetchProject(projectId);
  }, [projectId, fetchProject]);

  const isWriterPhase = ["DRAFT", "OUTLINE_REVIEW", "SCRIPT_REVIEW"].includes(
    currentProject?.status || ""
  );

  useEffect(() => {
    if (currentProject) {
      setActiveTab(isWriterPhase ? "writer" : "director");
    }
  }, [currentProject?.status]);

  if (loading && !currentProject) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "calc(100vh - 56px)" }}>
        <div className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  if (!currentProject) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: "var(--text-muted)" }}>
        <p>项目未找到</p>
        <button className="btn-secondary" style={{ marginTop: 16 }} onClick={() => router.push("/")}>
          返回首页
        </button>
      </div>
    );
  }

  return (
    <div style={{ height: "calc(100vh - 56px)", display: "flex", flexDirection: "column" }}>
      {/* Project Header */}
      <div
        style={{
          padding: "16px 24px",
          borderBottom: "1px solid var(--border)",
          background: "var(--bg-secondary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button
            onClick={() => router.push("/")}
            style={{
              background: "none",
              border: "none",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: 14,
              padding: "4px 8px",
            }}
          >
            ← 返回
          </button>
          <div>
            <h2
              style={{
                fontSize: 18, fontWeight: 700, color: "var(--text-primary)",
                letterSpacing: "-0.01em",
              }}
            >
              {currentProject.title}
            </h2>
            {currentProject.logline && (
              <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 2 }}>
                {currentProject.logline}
              </p>
            )}
          </div>
        </div>

        {/* Tab Switcher */}
        <div
          style={{
            display: "flex",
            background: "var(--bg-primary)",
            borderRadius: "var(--radius-md)",
            padding: 3,
            gap: 2,
          }}
        >
          {[
            { key: "writer" as const, label: "编剧模式", icon: "✍️" },
            { key: "director" as const, label: "导演看板", icon: "🎬" },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: "8px 18px",
                fontSize: 13,
                fontWeight: activeTab === tab.key ? 600 : 400,
                color: activeTab === tab.key ? "#fff" : "var(--text-muted)",
                background: activeTab === tab.key
                  ? "linear-gradient(135deg, var(--accent-primary), #6045d6)"
                  : "transparent",
                border: "none",
                borderRadius: "var(--radius-sm)",
                cursor: "pointer",
                transition: "all 0.2s ease",
              }}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: "10px 24px",
          background: "rgba(255,92,92,0.1)",
          borderBottom: "1px solid rgba(255,92,92,0.2)",
          color: "var(--accent-danger)",
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Content Area */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {activeTab === "writer" ? (
          <WriterEditor project={currentProject} />
        ) : (
          <KanbanBoard project={currentProject} />
        )}
      </div>
    </div>
  );
}
