"use client";

// タイトル画面（/）
// アプリロゴ「りなれす」＋2大ボタン。ログイン済みなら「つづきから」も表示。
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import Sparkles from "@/components/Sparkles";
import GameButton from "@/components/GameButton";
import { getStoredUser } from "@/lib/session";

export default function TitlePage() {
  const router = useRouter();
  const [hasSession, setHasSession] = useState(false);

  // localStorage はクライアントでのみ参照
  useEffect(() => {
    setHasSession(!!getStoredUser());
  }, []);

  return (
    <ScreenFrame bgClassName="bg-gradient-to-b from-[#ffd9ec] via-[#ffe8f2] to-[#e9dcff]">
      <Sparkles count={18} />

      <div className="relative flex flex-1 flex-col items-center justify-center gap-10 py-10">
        {/* ロゴ（ふわふわ浮く） */}
        <div className="animate-floaty flex flex-col items-center">
          <div className="relative">
            <span className="pointer-events-none absolute -left-6 -top-4 text-2xl">
              ✨
            </span>
            <span className="pointer-events-none absolute -right-5 top-2 text-xl">
              💖
            </span>
            <h1
              className="text-6xl font-extrabold tracking-wide text-white"
              style={{
                textShadow:
                  "0 3px 0 #f43f84, 0 6px 12px rgba(244,63,132,0.4), 2px 2px 0 #ffb1cf",
              }}
            >
              りなれす
            </h1>
          </div>
          <p className="mt-3 rounded-full bg-white/80 px-4 py-1 text-sm font-bold text-[var(--pink-600)] shadow">
            ⭐ 都市鉱山回収プロジェクト ⭐
          </p>
        </div>

        {/* ボタン群 */}
        <div className="flex w-full max-w-[300px] flex-col gap-4">
          {hasSession && (
            <GameButton
              variant="accent"
              fullWidth
              onClick={() => router.push("/home")}
            >
              ▶ つづきから
            </GameButton>
          )}
          {/* ログインも新規登録も入口は Google 認証（/login）に集約 */}
          <GameButton fullWidth onClick={() => router.push("/login")}>
            ログイン / はじめる
          </GameButton>
        </div>

        <p className="text-xs text-[var(--ink-soft)]">
          おうちの眠った端末を、推しと一緒にリサイクル♪
        </p>
      </div>
    </ScreenFrame>
  );
}
