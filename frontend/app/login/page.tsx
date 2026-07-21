"use client";

// ログイン画面（/login）
// ログイン/新規登録の入口だけ Google 認証する方式。
// Google Identity Services (GIS) の公式ボタンを表示し、
// コールバックで受け取った credential を POST /api/auth/google で検証する。
// - registered: true  → セッション保存して /home へ
// - registered: false → credential を一時保持して /register へ（あだ名・推し選択）
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import Sparkles from "@/components/Sparkles";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { storeSession, storePendingCredential } from "@/lib/session";
import { loadGsiScript, type GsiCredentialResponse } from "@/lib/gsi";

// クライアントID（秘匿値ではない）。ビルド時に NEXT_PUBLIC_GOOGLE_CLIENT_ID から埋め込む。
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

export default function LoginPage() {
  const router = useRouter();
  const { show } = useToast();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true); // GIS ボタン準備中
  const [busy, setBusy] = useState(false); // 認証処理中

  // GIS コールバック: credential を受け取ってバックエンドで検証
  const handleCredential = async (res: GsiCredentialResponse) => {
    if (!res.credential) {
      show("Google 認証に失敗しました。もう一度お試しください");
      return;
    }
    setBusy(true);
    try {
      const result = await api.googleAuth(res.credential);
      if (result.registered && result.user && result.token) {
        // 既存ユーザー: 通行証とともにセッション確立
        storeSession(result.user, result.token);
        show("おかえりなさい！", "success");
        router.push("/home");
      } else {
        // 未登録: credential を持ち越して新規登録へ
        storePendingCredential(res.credential);
        router.push("/register");
      }
    } catch {
      show("Google 認証に失敗しました。時間をおいて試してね");
      setBusy(false);
    }
  };

  useEffect(() => {
    let alive = true;
    if (!GOOGLE_CLIENT_ID) {
      show("Google クライアントIDが未設定です");
      setLoading(false);
      return;
    }
    (async () => {
      try {
        const google = await loadGsiScript();
        if (!alive) return;
        google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: (r) => {
            void handleCredential(r);
          },
          cancel_on_tap_outside: true,
        });
        if (buttonRef.current) {
          google.accounts.id.renderButton(buttonRef.current, {
            type: "standard",
            theme: "filled_blue",
            size: "large",
            text: "continue_with",
            shape: "pill",
            width: 280,
            locale: "ja",
          });
        }
      } catch {
        if (alive) show("Google ログインの読み込みに失敗しました");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // handleCredential は毎レンダー生成されるが依存に含めない（初期化は一度でよい）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show]);

  return (
    <ScreenFrame bgClassName="bg-gradient-to-b from-[#ffd9ec] via-[#ffe8f2] to-[#e9dcff]">
      <Sparkles count={12} />

      <header className="relative mb-5 flex items-center">
        <button
          onClick={() => router.push("/")}
          className="relative z-10 text-sm font-bold text-[var(--ink-soft)]"
        >
          ← もどる
        </button>
        <h1 className="absolute left-1/2 -translate-x-1/2 text-lg font-extrabold text-[var(--pink-600)]">
          ログイン
        </h1>
      </header>

      <div className="relative flex flex-1 flex-col items-center justify-center gap-8 text-center">
        <div className="animate-floaty flex flex-col items-center gap-2">
          <span className="text-5xl">💖</span>
          <p className="text-base font-extrabold text-[var(--pink-600)]">
            Googleでかんたんログイン
          </p>
          <p className="text-sm text-[var(--ink-soft)]">
            お持ちの Google アカウントで
            <br />
            ログイン・新規登録ができるよ♪
          </p>
        </div>

        {/* GIS 公式ボタンの描画先 */}
        <div className="flex min-h-[44px] items-center justify-center">
          {busy ? (
            <span className="text-sm font-bold text-[var(--ink-soft)]">
              認証中…
            </span>
          ) : (
            <div ref={buttonRef} />
          )}
          {loading && !busy && (
            <span className="text-sm text-[var(--ink-soft)]">
              読み込み中…
            </span>
          )}
        </div>

        <p className="max-w-[280px] text-xs leading-relaxed text-[var(--ink-soft)]">
          初めての方も、ボタンを押すだけでOK。
          <br />
          はじめての場合は続けて推し選びに進むよ。
        </p>
      </div>
    </ScreenFrame>
  );
}
