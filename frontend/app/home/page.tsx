"use client";

// ホーム画面（/home）
// - 右上: ポイント＆ランクバッジ（GET /api/users/{id} で最新化）
// - 中央: 推しアイドルの大きなイラスト
// - 上部: 吹き出しコメント（表示のたびに GET /api/users/{id}/comment）
// - 下部: メニュー各種＋ログアウト（確認ダイアログ）
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import Sparkles from "@/components/Sparkles";
import GameButton from "@/components/GameButton";
import GameDialog from "@/components/GameDialog";
import SpeechBubble from "@/components/SpeechBubble";
import RankBadge from "@/components/RankBadge";
import IdolImage from "@/components/IdolImage";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { clearUser, getStoredUser, storeUser } from "@/lib/session";
import type { Idol, User } from "@/lib/types";
import { FALLBACK_IDOLS } from "@/lib/idols";

export default function HomePage() {
  const router = useRouter();
  const { show } = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [idol, setIdol] = useState<Idol | null>(null);
  const [comment, setComment] = useState<string>("");
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [ready, setReady] = useState(false);

  // ホーム表示のたびにユーザー最新化＋コメント取得
  const load = useCallback(async () => {
    const stored = getStoredUser();
    if (!stored) {
      router.replace("/");
      return;
    }
    setUser(stored);

    // アイドル情報（フォールバックから先に引いておく）
    const fb = FALLBACK_IDOLS.find((i) => i.id === stored.idol_id) ?? null;
    setIdol(fb);

    // ユーザー最新化
    try {
      const fresh = await api.getUser(stored.id);
      setUser(fresh);
      storeUser(fresh);
    } catch {
      // 取得失敗時は保存済みを使う（トーストは控えめに）
    }

    // アイドル一覧（テーマカラー等の最新化）
    try {
      const idols = await api.getIdols();
      const found = idols.find((i) => i.id === stored.idol_id);
      if (found) setIdol(found);
    } catch {
      /* フォールバック済み */
    }

    // 推しコメント（毎回取得）
    try {
      const { comment } = await api.getComment(stored.id);
      setComment(comment);
    } catch {
      // 取得失敗時はデフォルトの一言
      setComment(`${stored.nickname}、今日も来てくれてうれしい♪`);
    }

    setReady(true);
  }, [router]);

  useEffect(() => {
    load();
  }, [load]);

  const logout = () => {
    clearUser();
    router.replace("/");
  };

  const theme = idol?.theme_color ?? "#ff87b2";

  if (!ready || !user) {
    return (
      <ScreenFrame>
        <div className="flex flex-1 items-center justify-center text-[var(--ink-soft)]">
          読み込み中…
        </div>
      </ScreenFrame>
    );
  }

  return (
    <ScreenFrame
      bgClassName="bg-gradient-to-b from-[#fff2f8] to-[#efe6ff]"
      noPadding
    >
      <Sparkles count={14} />

      {/* 上部バー: ランク＆ポイント */}
      <div className="relative flex items-start justify-between px-5 pt-5">
        <div className="rounded-2xl bg-white/70 px-3 py-1.5 text-sm font-extrabold text-[var(--pink-600)] shadow backdrop-blur">
          りなれす
        </div>
        <RankBadge rank={user.rank} points={user.points} />
      </div>

      {/* 吹き出し＋推しイラスト */}
      <div className="relative flex flex-col items-center px-5 pt-4">
        <div className="mb-4 w-full px-2">
          <SpeechBubble themeColor={theme}>{comment}</SpeechBubble>
        </div>
        {/* ラッパーにtransformを持たせるとmix-blend-modeが効かなくなるため、画像自体に付与する */}
        <IdolImage
          idolId={user.idol_id}
          name={idol?.name}
          size={230}
          height={330}
          className="animate-floaty"
        />
        <p className="mt-1 text-sm font-bold text-[var(--ink)]">
          {idol?.name ?? "推し"}
        </p>
      </div>

      {/* メニュー */}
      <div className="relative mt-auto px-5 pb-6 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <GameButton
            fullWidth
            themeColor={theme}
            onClick={() => router.push("/devices/new")}
          >
            📷 新規デバイス追加
          </GameButton>
          <GameButton
            fullWidth
            variant="accent"
            onClick={() => router.push("/ship")}
          >
            📦 りなれすに送る
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/history")}
          >
            📜 履歴
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/faq")}
          >
            💬 相談する
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/oshi")}
          >
            💖 推しをかえる
          </GameButton>
        </div>
        <div className="mt-3">
          <GameButton
            fullWidth
            variant="ghost"
            onClick={() => setLogoutOpen(true)}
          >
            ログアウト
          </GameButton>
        </div>
      </div>

      {/* ログアウト確認 */}
      <GameDialog
        open={logoutOpen}
        title="ログアウト"
        confirmLabel="ログアウトする"
        cancelLabel="やめる"
        onConfirm={logout}
        onCancel={() => setLogoutOpen(false)}
      >
        またね！ ログアウトしても、
        <br />
        あなたのデータは残っているよ。
      </GameDialog>
    </ScreenFrame>
  );
}
