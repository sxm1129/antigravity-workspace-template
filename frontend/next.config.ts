import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  // Proxy /api/* requests to the backend during Docker deployment.
  // In Docker Compose, the backend service is named "api" and listens on port 8000.
  // This allows browser-side fetch("/api/...") to reach the backend without CORS issues.
  async rewrites() {
    const backendUrl =
      process.env.BACKEND_INTERNAL_URL || "http://localhost:9001";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${backendUrl}/media/:path*`,
      },
      {
        source: "/health",
        destination: `${backendUrl}/health`,
      },
      {
        source: "/ws/:path*",
        destination: `${backendUrl}/ws/:path*`,
      },
    ];
  },
};

export default nextConfig;
