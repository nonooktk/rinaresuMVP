"use client";

// 推し変更（/oshi）
// - /register の推し選択ステップと同じビジュアル・作法（6人グリッド・IdolImage 立ち絵・テーマカラー）
// - 現在の推しには「いまの推し」バッジを表示
// - 別のアイドルを選ぶ → GameDialog で確認 → PATCH /api/users/me
//   → storeUser で localStorage 更新 → トースト → /home
// - ポイント / ランクは引き継ぐ（idol_id のみ変更）
// - 未ログイン時は既存作法どおりトップへリダイレクト
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import GameButton from "@/components/GameButton";
import GameDialog from "@/components/GameDialog";
import IdolImage from "@/components/IdolImage";
import Sparkles from "@/components/Sparkles";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";
import { getStoredUser, storeUser } from "@/lib/session";
import type { Idol, User } from "@/lib/types";
import { FALLBACK_IDOLS } from "@/lib/idols";

export default function OshiPage() {
  const router = useRouter();
  const { show } = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [idols, setIdols] = useState<Idol[]>(FALLBACK_IDOLS);
  // 変更先として選択中のアイドル（現在の推しと別のものを選んだときだけ確認へ進む）
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [ready, setReady] = useState(false);

  // 未ログインならトップへ。ログイン済みなら現在の推しを初期選択にする。
  useEffect(() => {
    const stored = getStoredUser();
    if (!stored) {
      router.replace("/");
      return;
    }
    setUser(stored);
    setSelectedId(stored.idol_id);
    setReady(true);
  }, [router]);

  // アイドル一覧を取得（失敗時はフォールバック）
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const ids = await api.getIdols();
        if (alive && ids?.length) setIdols(ids);
      } catch {
        if (alive) show("アイドル一覧を取得できませんでした（仮データを表示）");
      }
    })();
    return () => {
      alive = false;
    };
  }, [show]);

  const currentIdol = useMemo(
    () => idols.find((i) => i.id === user?.idol_id) ?? null,
    [idols, user]
  );
  const selectedIdol = useMemo(
    () => idols.find((i) => i.id === selectedId) ?? null,
    [idols, selectedId]
  );

  // 現在の推しと別のアイドルを選んでいるときだけ変更できる
  const changed = !!user && !!selectedId && selectedId !== user.idol_id;

  const submit = async () => {
    if (!selectedId) return;
    setSubmitting(true);
    try {
      const updated = await api.updateMe({ idol_id: selectedId });
      storeUser(updated);
      setUser(updated);
      setConfirmOpen(false);
      show(`${selectedIdol?.name ?? "推し"}に推し変したよ！`, "success");
      router.push("/home");
    } catch (e) {
      // 未ログイン扱い（401）ならログインからやり直し
      if (e instanceof ApiError && e.status === 401) {
        show("ログイン情報が切れました。もう一度ログインしてね");
        router.replace("/");
        return;
      }
      show("推し変更に失敗しました。時間をおいて試してね");
      setSubmitting(false);
    }
  };

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
    <ScreenFrame>
      <Sparkles count={10} />

      <header className="relative mb-4 flex items-center">
        <button
          onClick={() => router.push("/home")}
          className="relative z-10 text-sm font-bold text-[var(--ink-soft)]"
        >
          ← もどる
        </button>
        <h1 className="absolute left-1/2 -translate-x-1/2 text-lg font-extrabold text-[var(--pink-600)]">
          推しをかえる
        </h1>
      </header>

      {/* 本文 */}
      <div className="relative flex flex-1 flex-col">
        <p className="mb-4 text-center text-sm text-[var(--ink-soft)]">
          あたらしく応援したい推しを選んでね♪
          <br />
          <span className="text-[12px]">
            いままでのポイントとランクはそのまま引き継がれるよ
          </span>
        </p>
        <div className="grid grid-cols-2 gap-3 overflow-y-auto pb-2">
          {idols.map((idol) => {
            const active = idol.id === selectedId;
            const isCurrent = idol.id === user.idol_id;
            return (
              <button
                key={idol.id}
                onClick={() => setSelectedId(idol.id)}
                className={`relative flex flex-col items-center gap-1 rounded-3xl border-2 bg-white p-2 transition-transform active:scale-[0.97] ${
                  active
                    ? "animate-glow border-[var(--pink-400)]"
                    : "border-[var(--pink-100)]"
                }`}
              >
                {isCurrent && (
                  <span className="absolute left-2 top-2 z-10 rounded-full bg-[var(--pink-500)] px-2 py-0.5 text-[10px] font-extrabold text-white shadow">
                    いまの推し
                  </span>
                )}
                <IdolImage
                  idolId={idol.id}
                  name={idol.name}
                  size={72}
                  height={100}
                />
                <span className="text-sm font-bold text-[var(--ink)]">
                  {idol.name}
                </span>
                <span className="text-[10px] leading-tight text-[var(--ink-soft)]">
                  {idol.catchphrase}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 変更ボタン */}
      <div className="relative mt-4">
        <GameButton
          fullWidth
          disabled={!changed || submitting}
          onClick={() => setConfirmOpen(true)}
          themeColor={selectedIdol?.theme_color}
        >
          {changed ? "💖 この推しにかえる" : "いまの推しを応援中♪"}
        </GameButton>
      </div>

      {/* 確認ダイアログ */}
      <GameDialog
        open={confirmOpen}
        title="推し変の確認"
        confirmLabel={submitting ? "変更中…" : "推し変する"}
        cancelLabel="やめる"
        onConfirm={submit}
        onCancel={() => (submitting ? undefined : setConfirmOpen(false))}
        themeColor={selectedIdol?.theme_color}
      >
        {currentIdol?.name ?? "いまの推し"}から
        <br />
        {selectedIdol?.name ?? "この推し"}に推し変してもいい？
        <br />
        いままでのポイントはそのまま引き継がれるよ。
      </GameDialog>
    </ScreenFrame>
  );
}
