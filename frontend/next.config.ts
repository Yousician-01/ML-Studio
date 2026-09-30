import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep local development from writing unrelated agent instruction files.
  agentRules: false,
};

export default nextConfig;
