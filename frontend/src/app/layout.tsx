import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MotionWeaver | 漫剧创作引擎",
  description: "工业级端到端漫剧创作引擎 — AI 编剧 → 本地资产生成 → 视频自动合成",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        {/* Top Navigation Bar */}
        <nav
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            height: 56,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 24px",
            background: "var(--glass)",
            backdropFilter: "blur(20px)",
            borderBottom: "1px solid var(--border)",
            zIndex: 100,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: "linear-gradient(135deg, var(--accent-primary), #6045d6)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 16,
                fontWeight: 800,
                color: "#fff",
              }}
            >
              M
            </div>
            <span
              style={{
                fontSize: 18,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                background: "linear-gradient(135deg, #e8e8f0, #9b80ff)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              MotionWeaver
            </span>
          </div>

          <div style={{
            fontSize: 12,
            color: "var(--text-muted)",
            fontWeight: 500,
          }}>
            漫剧创作引擎 v0.1
          </div>
        </nav>

        {/* Main Content */}
        <main style={{ paddingTop: 56, minHeight: "100vh" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
