import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "images.unsplash.com" },
      { protocol: "https", hostname: "i.pravatar.cc" },

      // Django dev server - localhost
      { protocol: "http", hostname: "localhost", port: "8000" },
      { protocol: "http", hostname: "127.0.0.1", port: "8000" },

      // Django dev server - backend device on LAN
      {
        protocol: "http",
        hostname: "192.168.0.68",
        port: "8000",
        pathname: "/media/**",
      },
    ],
  },
};

export default nextConfig; 