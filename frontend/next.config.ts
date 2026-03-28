import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // NEXT_PUBLIC_API_URL is used in lib/api.ts to reach the FastAPI backend
  // Explicitly set the workspace root to silence the inferred-root warning
  outputFileTracingRoot: path.join(__dirname, ".."),
};

export default nextConfig;
