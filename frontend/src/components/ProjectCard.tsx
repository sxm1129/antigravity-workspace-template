"use client";

import { type Project } from "@/lib/api";
import { useRouter } from "next/navigation";

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  DRAFT: { label: "草稿", cls: "badge-ideation" },
  OUTLINE_REVIEW: { label: "大纲审阅", cls: "badge-review" },
  SCRIPT_REVIEW: { label: "剧本审阅", cls: "badge-review" },
  STORYBOARD: { label: "分镜", cls: "badge-generating" },
  PRODUCTION: { label: "制作中", cls: "badge-approval" },
  COMPOSING: { label: "合成中", cls: "badge-rendering" },
  COMPLETED: { label: "已完成", cls: "badge-completed" },
};

export default function ProjectCard({ project }: { project: Project }) {
  const router = useRouter();
  const status = STATUS_MAP[project.status] || { label: project.status, cls: "badge-ideation" };

  return (
    <div
      onClick={() => router.push(`/project/${project.id}`)}
      className="fade-in"
      style={{
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        padding: 24,
        cursor: "pointer",
        transition: "all 0.25s ease",
        position: "relative",
        overflow: "hidden",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "var(--accent-primary)";
        e.currentTarget.style.background = "var(--bg-card-hover)";
        e.currentTarget.style.transform = "translateY(-2px)";
        e.currentTarget.style.boxShadow = "var(--shadow-glow)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "var(--border)";
        e.currentTarget.style.background = "var(--bg-card)";
        e.currentTarget.style.transform = "translateY(0)";
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {/* Gradient accent bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "linear-gradient(90deg, var(--accent-primary), var(--accent-secondary))",
          opacity: 0.6,
        }}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <h3
          style={{
            fontSize: 18,
            fontWeight: 700,
            color: "var(--text-primary)",
            letterSpacing: "-0.01em",
            lineHeight: 1.3,
          }}
        >
          {project.title}
        </h3>
        <span className={`badge ${status.cls}`}>{status.label}</span>
      </div>

      {project.logline && (
        <p
          style={{
            fontSize: 13,
            color: "var(--text-secondary)",
            lineHeight: 1.5,
            marginBottom: 16,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {project.logline}
        </p>
      )}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: 11,
          color: "var(--text-muted)",
        }}
      >
        <span>{new Date(project.created_at).toLocaleDateString("zh-CN")}</span>
        <span style={{ color: "var(--accent-primary-light)", fontWeight: 500 }}>
          进入项目 →
        </span>
      </div>
    </div>
  );
}
