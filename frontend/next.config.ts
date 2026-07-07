import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Azure Container Apps 向けにスタンドアロン出力を生成する。
  // .next/standalone に server.js と最小限の依存が同梱され、
  // Dockerイメージを小さく保てる。
  output: "standalone",
};

export default nextConfig;
