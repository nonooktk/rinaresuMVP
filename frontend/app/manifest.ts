import type { MetadataRoute } from "next";

// Web App Manifest（PWA 化ステップ1）
// Next.js App Router の規約に従い、app/manifest.ts が
// /manifest.webmanifest として配信され、<link rel="manifest"> も自動注入される。
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "りなれす",
    short_name: "りなれす",
    // 既存の layout.tsx metadata.description と揃える
    description: "推しと一緒に、おうちの都市鉱山をリサイクル。りなれす MVP",
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    // テーマカラーは layout.tsx の viewport.themeColor と一致させる（#ff87b2 = --pink-400）
    theme_color: "#ff87b2",
    // 起動スプラッシュの背景。アプリ外側グラデーション（globals.css body background）の
    // 起点色 #ffd9e8 を単色として採用（同じピンク系トーン）
    background_color: "#ffd9e8",
    icons: [
      {
        src: "/icons/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any",
      },
      {
        src: "/icons/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any",
      },
      {
        // maskable: Android のアダプティブアイコン用（セーフゾーン確保済み）
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
