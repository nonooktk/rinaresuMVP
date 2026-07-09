import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Azure Container Apps 向けにスタンドアロン出力を生成する。
  // .next/standalone に server.js と最小限の依存が同梱され、
  // Dockerイメージを小さく保てる。
  output: "standalone",

  // PWA の Service Worker / manifest は HTTP キャッシュで固定されると
  // 更新が遅延する。この2パスは常に再検証させる。
  // headers() は Node サーバー配信（next start / standalone の server.js）で有効。
  // 無効化されるのは output: "export"（静的エクスポート）の場合のみで、
  // 本プロジェクトは standalone のため適用される。
  async headers() {
    const noCache = {
      key: "Cache-Control",
      value: "no-cache, max-age=0, must-revalidate",
    };
    return [
      { source: "/sw.js", headers: [noCache] },
      { source: "/manifest.webmanifest", headers: [noCache] },
    ];
  },
};

export default nextConfig;
