import path from "node:path";
import type { NextConfig } from "next";

// BACKEND_URL is read when the config is loaded. For `next dev` / `next start` that is at runtime;
// for the standalone Docker image rewrites are baked in at build time, so pass it as a build arg.
const BACKEND_URL = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin the project root (a stray lockfile higher up the tree would otherwise be picked as the root).
  outputFileTracingRoot: path.resolve(__dirname),
  turbopack: { root: path.resolve(__dirname) },
  poweredByHeader: false,
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
