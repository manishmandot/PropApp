import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // End-to-end tests build twice (seeded and empty database) into separate folders.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
};

export default nextConfig;
