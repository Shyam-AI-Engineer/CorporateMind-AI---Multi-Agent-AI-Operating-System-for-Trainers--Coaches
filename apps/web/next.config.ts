import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // API base URL — requests proxied to FastAPI in development
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/:path*`,
      },
    ];
  },

  images: {
    remotePatterns: [
      { protocol: "https", hostname: "res.cloudinary.com" },
    ],
  },

  typedRoutes: true,
};

export default nextConfig;
