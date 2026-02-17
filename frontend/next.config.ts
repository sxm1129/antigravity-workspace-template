import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",

  // Allow long-running backend API calls (e.g. extract-and-generate ~33s)
  // to complete without the rewrite proxy timing out and returning 500.
  experimental: {
    proxyTimeout: 120_000, // 120 seconds
  },

  // Let Next.js transpile Remotion packages (they ship ESM/TS)
  transpilePackages: [
    "remotion",
    "@remotion/player",
    "@remotion/transitions",
  ],

  // Proxy /api/* requests to the backend during Docker deployment.
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

