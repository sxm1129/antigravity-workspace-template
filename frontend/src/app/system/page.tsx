"use client";

import { useEffect, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:9001";

interface ServiceStatus {
  status: string;
  latency_ms?: number;
  error?: string;
  [key: string]: unknown;
}

interface CeleryStatus extends ServiceStatus {
  workers: { name: string; status: string }[];
  count: number;
  active_tasks?: number;
  reserved_tasks?: number;
  registered_tasks?: string[];
  message?: string;
}

interface QueueStatus {
  queue_name: string;
  pending_tasks: number;
  error?: string;
}

interface ExternalApi {
  name: string;
  status: string;
  latency_ms?: number;
  endpoint: string;
  error?: string;
}

interface SystemStatusData {
  overall: string;
  services: {
    redis: ServiceStatus;
    database: ServiceStatus;
    celery: CeleryStatus;
    queue: QueueStatus;
  };
  external_apis: ExternalApi[];
  settings?: {
    image_providers: string;
    video_providers: string;
  };
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string; dot: string }> = {
    ok: { bg: "rgba(16,185,129,0.12)", text: "#10b981", dot: "#10b981" },
    error: { bg: "rgba(239,68,68,0.12)", text: "#ef4444", dot: "#ef4444" },
    offline: { bg: "rgba(245,158,11,0.12)", text: "#f59e0b", dot: "#f59e0b" },
    degraded: { bg: "rgba(245,158,11,0.12)", text: "#f59e0b", dot: "#f59e0b" },
    loading: { bg: "rgba(99,102,241,0.12)", text: "#6366f1", dot: "#6366f1" },
  };
  const c = colors[status] || colors.error;
  const labels: Record<string, string> = {
    ok: "正常",
    error: "异常",
    offline: "离线",
    degraded: "部分异常",
    loading: "检测中...",
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "4px 10px",
        borderRadius: 20,
        background: c.bg,
        fontSize: 12,
        fontWeight: 600,
        color: c.text,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: c.dot,
          ...(status === "ok"
            ? { boxShadow: `0 0 6px ${c.dot}`, animation: "pulse 2s infinite" }
            : {}),
        }}
      />
      {labels[status] || status}
    </span>
  );
}

function ServiceCard({
  title,
  icon,
  status,
  latency,
  details,
  error,
  children,
}: {
  title: string;
  icon: string;
  status: string;
  latency?: number;
  details?: { label: string; value: string }[];
  error?: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      style={{
        background: "var(--bg-card)",
        border: `1px solid ${status === "ok" ? "var(--border)" : status === "error" ? "rgba(239,68,68,0.3)" : "rgba(245,158,11,0.3)"}`,
        borderRadius: "var(--radius-lg)",
        padding: "20px 24px",
        transition: "all 0.2s ease",
      }}
      className="fade-in"
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 22 }}>{icon}</span>
          <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
            {title}
          </h3>
        </div>
        <StatusBadge status={status} />
      </div>

      {latency !== undefined && (
        <div
          style={{
            fontSize: 12,
            color: "var(--text-muted)",
            marginBottom: 12,
          }}
        >
          延迟: <span style={{ color: "var(--text-secondary)", fontWeight: 500 }}>{latency}ms</span>
        </div>
      )}

      {details && details.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {details.map((d) => (
            <div
              key={d.label}
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 12,
              }}
            >
              <span style={{ color: "var(--text-muted)" }}>{d.label}</span>
              <span
                style={{
                  color: "var(--text-secondary)",
                  fontFamily: "monospace",
                  fontSize: 11,
                }}
              >
                {d.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            padding: "10px 12px",
            background: "rgba(239,68,68,0.08)",
            borderRadius: "var(--radius-sm)",
            fontSize: 11,
            color: "#ef4444",
            fontFamily: "monospace",
            wordBreak: "break-all",
          }}
        >
          {error}
        </div>
      )}

      {children}
    </div>
  );
}

export default function SystemPage() {
  const [data, setData] = useState<SystemStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState("");
  const [imageProvider, setImageProvider] = useState("flux,openrouter");
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/api/system/status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setData(json);
      setError(null);
      setLastRefresh(new Date());
      // Sync settings from status response
      if (json.settings?.image_providers) {
        setImageProvider(json.settings.image_providers);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "获取系统状态失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const celeryAction = useCallback(async (action: "start" | "stop") => {
    setActionLoading(action);
    setActionMsg(null);
    try {
      const res = await fetch(`${API_URL}/api/system/celery/${action}`, {
        method: "POST",
      });
      const json = await res.json();
      setActionMsg(json.message || json.status);
      // Refresh status after a brief delay to let celery boot/shutdown
      setTimeout(() => {
        fetchStatus();
        setActionLoading(null);
      }, 3000);
    } catch (e) {
      setActionMsg(`操作失败: ${e instanceof Error ? e.message : "unknown"}`);
      setActionLoading(null);
    }
  }, [fetchStatus]);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system/celery/logs`);
      const json = await res.json();
      setLogs(json.logs || "暂无日志");
    } catch {
      setLogs("获取日志失败");
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchStatus]);

  // Auto-refresh logs when visible
  useEffect(() => {
    if (!showLogs) return;
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [showLogs, fetchLogs]);

  const celeryOnline = data?.services.celery.status === "ok";

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-primary)",
        padding: "32px 40px",
      }}
    >
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 32,
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <a
              href="/"
              style={{
                color: "var(--text-muted)",
                textDecoration: "none",
                fontSize: 13,
              }}
            >
              ← 返回
            </a>
          </div>
          <h1
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: "var(--text-primary)",
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            🖥 系统监控
            {data && <StatusBadge status={data.overall} />}
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginTop: 4 }}>
            MotionWeaver 服务和依赖组件运行状态
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {lastRefresh && (
            <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
              上次刷新: {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              color: "var(--text-secondary)",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ accentColor: "var(--accent-primary)" }}
            />
            自动刷新 (15s)
          </label>
          <button
            className="btn-secondary"
            onClick={fetchStatus}
            disabled={loading}
            style={{ padding: "8px 16px", fontSize: 12 }}
          >
            {loading ? "检测中..." : "🔄 刷新"}
          </button>
        </div>
      </div>

      {error && !data && (
        <div
          style={{
            padding: "20px 24px",
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: "var(--radius-lg)",
            color: "#ef4444",
            fontSize: 14,
            marginBottom: 24,
          }}
        >
          ❌ 无法连接后端 API: {error}
          <br />
          <span style={{ fontSize: 12, opacity: 0.7 }}>
            请确认后端服务运行在 {API_URL}
          </span>
        </div>
      )}

      {data && (
        <>
          {/* Core Services */}
          <h2
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: "var(--text-secondary)",
              marginBottom: 16,
              textTransform: "uppercase",
              letterSpacing: 1,
            }}
          >
            核心服务
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 16,
              marginBottom: 32,
            }}
          >
            <ServiceCard
              title="MySQL 数据库"
              icon="🗄"
              status={data.services.database.status}
              latency={data.services.database.latency_ms}
              details={[
                { label: "主机", value: String(data.services.database.host || "") },
                { label: "数据库", value: String(data.services.database.database || "") },
              ]}
              error={data.services.database.error as string}
            />

            <ServiceCard
              title="Redis"
              icon="⚡"
              status={data.services.redis.status}
              latency={data.services.redis.latency_ms}
              details={[
                { label: "版本", value: String(data.services.redis.version || "") },
                { label: "地址", value: String(data.services.redis.url || "") },
              ]}
              error={data.services.redis.error as string}
            />

            {/* Celery Workers — with action buttons */}
            <ServiceCard
              title="Celery Workers"
              icon="⚙️"
              status={data.services.celery.status}
              details={[
                { label: "在线 Workers", value: String(data.services.celery.count) },
                ...(data.services.celery.active_tasks !== undefined
                  ? [{ label: "执行中任务", value: String(data.services.celery.active_tasks) }]
                  : []),
                ...(data.services.celery.reserved_tasks !== undefined
                  ? [{ label: "排队任务", value: String(data.services.celery.reserved_tasks) }]
                  : []),
              ]}
              error={
                data.services.celery.status === "offline"
                  ? (data.services.celery.message || "没有运行中的 Worker")
                  : (data.services.celery.error as string)
              }
            >
              {/* Action Buttons */}
              <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {!celeryOnline ? (
                  <button
                    onClick={() => celeryAction("start")}
                    disabled={actionLoading !== null}
                    style={{
                      flex: 1,
                      padding: "10px 16px",
                      fontSize: 13,
                      fontWeight: 600,
                      border: "none",
                      borderRadius: "var(--radius-sm)",
                      background: "linear-gradient(135deg, #10b981, #059669)",
                      color: "#fff",
                      cursor: actionLoading ? "wait" : "pointer",
                      opacity: actionLoading ? 0.7 : 1,
                      transition: "all 0.2s",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 6,
                    }}
                  >
                    {actionLoading === "start" ? (
                      <>
                        <span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⏳</span>
                        启动中...
                      </>
                    ) : (
                      "▶ 启动 Worker"
                    )}
                  </button>
                ) : (
                  <button
                    onClick={() => celeryAction("stop")}
                    disabled={actionLoading !== null}
                    style={{
                      flex: 1,
                      padding: "10px 16px",
                      fontSize: 13,
                      fontWeight: 600,
                      border: "1px solid rgba(239,68,68,0.3)",
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(239,68,68,0.1)",
                      color: "#ef4444",
                      cursor: actionLoading ? "wait" : "pointer",
                      opacity: actionLoading ? 0.7 : 1,
                      transition: "all 0.2s",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 6,
                    }}
                  >
                    {actionLoading === "stop" ? (
                      <>
                        <span style={{ display: "inline-block", animation: "spin 1s linear infinite" }}>⏳</span>
                        停止中...
                      </>
                    ) : (
                      "⏹ 停止 Worker"
                    )}
                  </button>
                )}
                <button
                  onClick={() => {
                    setShowLogs(!showLogs);
                    if (!showLogs) fetchLogs();
                  }}
                  style={{
                    padding: "10px 16px",
                    fontSize: 13,
                    fontWeight: 600,
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius-sm)",
                    background: showLogs ? "rgba(99,102,241,0.15)" : "transparent",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    transition: "all 0.2s",
                  }}
                >
                  📄 日志
                </button>
              </div>

              {/* Action feedback */}
              {actionMsg && (
                <div
                  style={{
                    marginTop: 10,
                    padding: "8px 12px",
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(99,102,241,0.08)",
                    fontSize: 12,
                    color: "var(--text-secondary)",
                  }}
                >
                  {actionMsg}
                </div>
              )}
            </ServiceCard>

            <ServiceCard
              title="任务队列"
              icon="📋"
              status={data.services.queue.pending_tasks >= 0 ? "ok" : "error"}
              details={[
                { label: "队列名", value: data.services.queue.queue_name },
                { label: "等待中任务", value: String(data.services.queue.pending_tasks) },
              ]}
              error={data.services.queue.error}
            />
          </div>

          {/* Celery Log Viewer */}
          {showLogs && (
            <div style={{ marginBottom: 32 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <h2
                  style={{
                    fontSize: 15,
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  Worker 日志
                </h2>
                <div style={{ display: "flex", gap: 8 }}>
                  <button
                    onClick={fetchLogs}
                    style={{
                      padding: "4px 12px",
                      fontSize: 11,
                      border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)",
                      background: "transparent",
                      color: "var(--text-muted)",
                      cursor: "pointer",
                    }}
                  >
                    🔄 刷新日志
                  </button>
                  <span style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: "26px" }}>
                    自动刷新 5s
                  </span>
                </div>
              </div>
              <pre
                style={{
                  background: "#0d1117",
                  border: "1px solid var(--border)",
                  borderRadius: "var(--radius-lg)",
                  padding: "16px 20px",
                  fontSize: 11,
                  lineHeight: 1.6,
                  color: "#c9d1d9",
                  fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
                  maxHeight: 400,
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {logs || "加载中..."}
              </pre>
            </div>
          )}

          {/* Celery Worker Details */}
          {data.services.celery.workers.length > 0 && (
            <>
              <h2
                style={{
                  fontSize: 15,
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  marginBottom: 16,
                  textTransform: "uppercase",
                  letterSpacing: 1,
                }}
              >
                Worker 列表
              </h2>
              <div
                className="glass-panel"
                style={{ padding: "16px 20px", marginBottom: 32 }}
              >
                {data.services.celery.workers.map((w) => (
                  <div
                    key={w.name}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "8px 0",
                      borderBottom: "1px solid var(--border)",
                    }}
                  >
                    <span
                      style={{
                        fontSize: 13,
                        color: "var(--text-primary)",
                        fontFamily: "monospace",
                      }}
                    >
                      {w.name}
                    </span>
                    <StatusBadge status={w.status} />
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Registered Tasks */}
          {data.services.celery.registered_tasks &&
            data.services.celery.registered_tasks.length > 0 && (
              <>
                <h2
                  style={{
                    fontSize: 15,
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: 16,
                    textTransform: "uppercase",
                    letterSpacing: 1,
                  }}
                >
                  已注册任务
                </h2>
                <div
                  className="glass-panel"
                  style={{ padding: "16px 20px", marginBottom: 32 }}
                >
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {data.services.celery.registered_tasks.map((t) => (
                      <span
                        key={t}
                        style={{
                          padding: "4px 10px",
                          borderRadius: "var(--radius-sm)",
                          background: "rgba(99,102,241,0.1)",
                          border: "1px solid rgba(99,102,241,0.2)",
                          fontSize: 11,
                          fontFamily: "monospace",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
              </>
            )}

          {/* Provider Settings */}
          <h2
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: "var(--text-secondary)",
              marginBottom: 16,
              textTransform: "uppercase",
              letterSpacing: 1,
            }}
          >
            生成设置
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 16,
              marginBottom: 32,
            }}
          >
            <div
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-lg)",
                padding: "20px 24px",
              }}
              className="fade-in"
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                <span style={{ fontSize: 22 }}>🎨</span>
                <h3 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                  文生图引擎
                </h3>
              </div>

              <div style={{ marginBottom: 14 }}>
                <label
                  style={{
                    display: "block",
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginBottom: 6,
                  }}
                >
                  图片生成方式
                </label>
                <select
                  value={imageProvider}
                  onChange={(e) => setImageProvider(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "8px 12px",
                    fontSize: 13,
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border)",
                    background: "var(--bg-primary)",
                    color: "var(--text-primary)",
                    cursor: "pointer",
                    outline: "none",
                  }}
                >
                  <option value="flux">🚀 Flux (私有部署) — 快速</option>
                  <option value="openrouter">🌐 OpenRouter (Gemini) — 高质量</option>
                  <option value="flux,openrouter">🔄 Flux → OpenRouter (级联)</option>
                  <option value="openrouter,flux">🔄 OpenRouter → Flux (级联)</option>
                </select>
              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <button
                  onClick={async () => {
                    setSettingsSaving(true);
                    setSettingsMsg(null);
                    try {
                      const res = await fetch(`${API_URL}/api/system/settings`, {
                        method: "PUT",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ image_providers: imageProvider }),
                      });
                      const json = await res.json();
                      setSettingsMsg(json.status === "ok" ? "✅ 已保存" : "⚠️ 无变化");
                      setTimeout(() => setSettingsMsg(null), 3000);
                    } catch (e) {
                      setSettingsMsg(`❌ 保存失败: ${e instanceof Error ? e.message : "unknown"}`);
                    } finally {
                      setSettingsSaving(false);
                    }
                  }}
                  disabled={settingsSaving}
                  style={{
                    padding: "6px 16px",
                    fontSize: 12,
                    fontWeight: 600,
                    borderRadius: "var(--radius-sm)",
                    border: "none",
                    background: "rgba(16,185,129,0.15)",
                    color: "#10b981",
                    cursor: settingsSaving ? "not-allowed" : "pointer",
                    transition: "all 0.2s",
                  }}
                >
                  {settingsSaving ? "保存中..." : "💾 保存"}
                </button>
                {settingsMsg && (
                  <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                    {settingsMsg}
                  </span>
                )}
              </div>

              <div
                style={{
                  marginTop: 14,
                  padding: "10px 12px",
                  background: "rgba(99,102,241,0.06)",
                  borderRadius: "var(--radius-sm)",
                  fontSize: 11,
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                }}
              >
                当前: <span style={{ color: "var(--text-secondary)", fontFamily: "monospace" }}>{imageProvider}</span>
                <br />
                级联模式下，优先使用第一个引擎，失败时自动切换到第二个
              </div>
            </div>
          </div>

          {/* External APIs */}
          <h2
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: "var(--text-secondary)",
              marginBottom: 16,
              textTransform: "uppercase",
              letterSpacing: 1,
            }}
          >
            外部 API
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: 16,
              marginBottom: 32,
            }}
          >
            {data.external_apis.map((api) => (
              <ServiceCard
                key={api.name}
                title={api.name}
                icon="🌐"
                status={api.status}
                latency={api.latency_ms}
                details={[{ label: "端点", value: api.endpoint }]}
                error={api.error}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
