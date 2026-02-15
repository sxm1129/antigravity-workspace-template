"use client";

import { useEffect, useState } from "react";
import { useProjectStore } from "@/stores/useProjectStore";
import ProjectCard from "@/components/ProjectCard";

export default function HomePage() {
  const { projects, fetchProjects, createProject, loading, error, setError } = useProjectStore();
  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [logline, setLogline] = useState("");

  // OPT-5: Auto-dismiss error after 8 seconds
  useEffect(() => {
    if (!error) return;
    const timer = setTimeout(() => setError(null), 8000);
    return () => clearTimeout(timer);
  }, [error, setError]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async () => {
    if (!title.trim()) return;
    try {
      await createProject(title.trim(), logline.trim() || undefined);
      setTitle("");
      setLogline("");
      setShowCreate(false);
    } catch {
      // error handled by store
    }
  };

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "40px 24px" }}>
      {/* Hero Section */}
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <h1
          style={{
            fontSize: 40,
            fontWeight: 900,
            letterSpacing: "-0.03em",
            lineHeight: 1.2,
            background: "linear-gradient(135deg, #e8e8f0 30%, #9b80ff 70%, #00d4aa)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            marginBottom: 12,
          }}
        >
          MotionWeaver
        </h1>
        <p style={{ fontSize: 16, color: "var(--text-secondary)", maxWidth: 500, margin: "0 auto", lineHeight: 1.6 }}>
          工业级端到端漫剧创作引擎 — AI 编剧 → 资产生成 → 视频合成
        </p>
      </div>

      {/* Action Bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: "var(--text-primary)" }}>
          我的项目
          <span style={{ fontSize: 13, fontWeight: 400, color: "var(--text-muted)", marginLeft: 8 }}>
            ({projects.length})
          </span>
        </h2>
        <button className="btn-primary" onClick={() => setShowCreate(!showCreate)}>
          + 新建项目
        </button>
      </div>

      {/* Create Project Form */}
      {showCreate && (
        <div
          className="glass-panel fade-in"
          style={{ padding: 24, marginBottom: 32 }}
        >
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: "var(--text-primary)" }}>
            新建漫剧项目
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <input
              className="input-field"
              placeholder="项目标题 (例: 星际拾荒者)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleCreate()}
              autoFocus
            />
            <textarea
              className="textarea-field"
              placeholder="一句话梗概 Logline (例: 一个在废弃空间站捡垃圾的少年，意外发现了一颗能改变宇宙命运的种子...)"
              value={logline}
              onChange={(e) => setLogline(e.target.value)}
              style={{ minHeight: 80 }}
            />
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button className="btn-secondary" onClick={() => setShowCreate(false)}>
                取消
              </button>
              <button className="btn-primary" onClick={handleCreate} disabled={!title.trim() || loading}>
                {loading ? <span className="spinner" /> : null}
                创建项目
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(255,92,92,0.1)",
            border: "1px solid rgba(255,92,92,0.2)",
            borderRadius: "var(--radius-md)",
            color: "var(--accent-danger)",
            fontSize: 13,
            marginBottom: 24,
          }}
        >
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && projects.length === 0 && (
        <div style={{ textAlign: "center", padding: 80 }}>
          <div className="spinner" style={{ margin: "0 auto 16px", width: 32, height: 32 }} />
          <p style={{ color: "var(--text-muted)" }}>加载中...</p>
        </div>
      )}

      {/* Project Grid */}
      {projects.length > 0 ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
            gap: 20,
          }}
        >
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      ) : (
        !loading && (
          <div
            style={{
              textAlign: "center",
              padding: 80,
              color: "var(--text-muted)",
            }}
          >
            <div style={{ fontSize: 48, marginBottom: 16, opacity: 0.3 }}>🎬</div>
            <p style={{ fontSize: 16 }}>暂无项目，点击 "新建项目" 开始创作</p>
          </div>
        )
      )}
    </div>
  );
}
