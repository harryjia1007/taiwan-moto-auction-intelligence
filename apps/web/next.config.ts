import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep production builds away from the live development cache. Running
  // `next build` while `next dev` is open must not corrupt the local site.
  distDir: process.env.NODE_ENV === "production" ? ".next-production" : ".next",
  transpilePackages: ["@tm-ai/shared", "@tm-ai/ui"],
  images: {
    remotePatterns: [{ protocol: "https", hostname: "shwoo.gov.taipei", pathname: "/shwoo/**" }],
  },
  poweredByHeader: false,
};

export default nextConfig;
