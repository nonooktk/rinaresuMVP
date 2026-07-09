import type { Metadata, Viewport } from "next";
import { M_PLUS_Rounded_1c } from "next/font/google";
import "./globals.css";
import { ToastProvider } from "@/components/Toast";
import ServiceWorkerRegister from "@/components/ServiceWorkerRegister";

// 丸ゴシック（M PLUS Rounded 1c）をアプリ全体に適用
const rounded = M_PLUS_Rounded_1c({
  weight: ["400", "500", "700", "800"],
  subsets: ["latin"],
  variable: "--font-rounded",
  display: "swap",
});

export const metadata: Metadata = {
  title: "りなれす | 都市鉱山回収プロジェクト",
  description: "推しと一緒に、おうちの都市鉱山をリサイクル。りなれす MVP",
  // ホーム画面追加時のアプリ名。PWA 化ステップ1（Android 主目的だが iOS も最小限対応）。
  // apple-mobile-web-app-capable 等のメタタグを Next.js が自動生成する。
  appleWebApp: {
    capable: true,
    title: "りなれす",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#ff87b2",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja" className={`${rounded.variable} h-full`}>
      <body className="min-h-full">
        {/* Service Worker 登録（本番ビルドのみ有効。UI は描画しない） */}
        <ServiceWorkerRegister />
        {/* トースト（API失敗時などに表示）をアプリ全体で使えるように */}
        <ToastProvider>{children}</ToastProvider>
      </body>
    </html>
  );
}
