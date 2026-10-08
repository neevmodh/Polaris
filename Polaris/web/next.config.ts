import type { NextConfig } from "next";

/** The Python engines cannot run on Vercel's serverless functions (they are long-lived child processes in their own
 *  virtual environments). When POLARIS_API_ORIGIN is set, this deployment serves the identical UI and forwards every
 *  /api call to the server that does run them, so the page the visitor sees is the one built here. Unset (local,
 *  Railway), nothing is rewritten and the route handlers answer directly. */
const origin = process.env.POLARIS_API_ORIGIN?.replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return origin ? { beforeFiles: [{ source: "/api/:path*", destination: `${origin}/api/:path*` }], afterFiles: [], fallback: [] } : [];
  },
};
export default nextConfig;
