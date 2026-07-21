"use client";

// アカウント作成（/register）2ステップウィザード
// 前提: /login で Google 認証を済ませ、未登録だったユーザーがここに来る。
//       Google の credential は sessionStorage に一時保持されている。
// Step1: アイドル選択（GET /api/idols）
// Step2: 呼んでほしい名前（あだ名）
// 完了で POST /api/users（credential を添付）→ credential 破棄 → localStorage保存 → /home
// credential が無い/失効（401/400）なら /login へ誘導する。
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import GameButton from "@/components/GameButton";
import IdolImage from "@/components/IdolImage";
import Sparkles from "@/components/Sparkles";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";
import {
  storeSession,
  getPendingCredential,
  clearPendingCredential,
} from "@/lib/session";
import type { Idol } from "@/lib/types";
import { FALLBACK_IDOLS } from "@/lib/idols";

const STEPS = ["推しを選ぶ", "呼び名を決める"];

export default function RegisterPage() {
  const router = useRouter();
  const { show } = useToast();

  const [step, setStep] = useState(0);
  const [idolId, setIdolId] = useState<string | null>(null);
  const [nickname, setNickname] = useState("");
  const [idols, setIdols] = useState<Idol[]>(FALLBACK_IDOLS);
  const [submitting, setSubmitting] = useState(false);

  // credential が無ければ Google 認証が済んでいないので /login へ戻す
  useEffect(() => {
    if (!getPendingCredential()) {
      show("先に Google でログインしてね");
      router.replace("/login");
    }
  }, [router, show]);

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

  const selectedIdol = useMemo(
    () => idols.find((i) => i.id === idolId),
    [idols, idolId]
  );

  // 次へ進める条件
  const canNext =
    (step === 0 && !!idolId) ||
    (step === 1 && nickname.trim().length > 0);

  const submit = async () => {
    if (!idolId) return;
    const credential = getPendingCredential();
    if (!credential) {
      // credential 切れ: ログインからやり直し
      show("ログイン情報の有効期限が切れました。もう一度ログインしてね");
      router.replace("/login");
      return;
    }
    setSubmitting(true);
    try {
      const session = await api.createUser({
        credential,
        nickname: nickname.trim(),
        idol_id: idolId,
      });
      clearPendingCredential(); // 使い終わった credential は破棄
      storeSession(session.user, session.token);
      show("アカウントを作成しました！", "success");
      router.push("/home");
    } catch (e) {
      // credential 検証失敗（401）や不正リクエスト（400）はログインからやり直し
      if (e instanceof ApiError && (e.status === 401 || e.status === 400)) {
        clearPendingCredential();
        show("認証の有効期限が切れました。もう一度ログインしてね");
        router.replace("/login");
        return;
      }
      show("アカウント作成に失敗しました。時間をおいて試してね");
      setSubmitting(false);
    }
  };

  const next = () => {
    if (step < STEPS.length - 1) setStep(step + 1);
    else submit();
  };
  const back = () => {
    if (step > 0) setStep(step - 1);
    else router.push("/login");
  };

  return (
    <ScreenFrame>
      <Sparkles count={10} />

      <header className="relative mb-4 flex items-center">
        <button
          onClick={back}
          className="relative z-10 text-sm font-bold text-[var(--ink-soft)]"
        >
          ← もどる
        </button>
        <h1 className="absolute left-1/2 -translate-x-1/2 text-lg font-extrabold text-[var(--pink-600)]">
          アカウント作成
        </h1>
      </header>

      {/* ステップインジケーター */}
      <div className="relative mb-6 flex items-center justify-center gap-2">
        {STEPS.map((label, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="flex flex-col items-center">
              <div
                className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-extrabold transition-colors ${
                  i <= step
                    ? "bg-[var(--pink-500)] text-white shadow"
                    : "bg-[var(--pink-100)] text-[var(--pink-300)]"
                }`}
              >
                {i + 1}
              </div>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`h-1 w-6 rounded-full ${
                  i < step ? "bg-[var(--pink-400)]" : "bg-[var(--pink-100)]"
                }`}
              />
            )}
          </div>
        ))}
      </div>
      <p className="relative mb-5 text-center text-sm font-bold text-[var(--ink)]">
        STEP {step + 1}. {STEPS[step]}
      </p>

      {/* 本文 */}
      <div className="relative flex flex-1 flex-col">
        {step === 0 && (
          <div className="flex flex-col gap-3">
            <p className="text-center text-sm text-[var(--ink-soft)]">
              いっしょに頑張る推しを選んでね♪
            </p>
            <div className="grid grid-cols-2 gap-3 overflow-y-auto pb-2">
              {idols.map((idol) => {
                const active = idol.id === idolId;
                return (
                  <button
                    key={idol.id}
                    onClick={() => setIdolId(idol.id)}
                    className={`flex flex-col items-center gap-1 rounded-3xl border-2 bg-white p-2 transition-transform active:scale-[0.97] ${
                      active
                        ? "animate-glow border-[var(--pink-400)]"
                        : "border-[var(--pink-100)]"
                    }`}
                  >
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
        )}

        {step === 1 && (
          <div className="flex flex-col items-center gap-4">
            {selectedIdol && (
              <IdolImage
                idolId={selectedIdol.id}
                name={selectedIdol.name}
                size={120}
                height={170}
              />
            )}
            <p className="text-center text-sm text-[var(--ink-soft)]">
              {selectedIdol?.name ?? "推し"}に
              <br />
              なんて呼んでほしい？
            </p>
            <input
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder="あだ名を入力（例: モモちゃん）"
              maxLength={20}
              className="w-full rounded-2xl border-2 border-[var(--pink-200)] bg-white px-4 py-3 text-center text-lg font-bold text-[var(--ink)] outline-none focus:border-[var(--pink-400)]"
            />
          </div>
        )}
      </div>

      {/* 次へ／完了 */}
      <div className="relative mt-4">
        <GameButton
          fullWidth
          disabled={!canNext || submitting}
          onClick={next}
          themeColor={selectedIdol?.theme_color}
        >
          {submitting
            ? "作成中…"
            : step < STEPS.length - 1
            ? "つぎへ ▶"
            : "✨ この内容ではじめる"}
        </GameButton>
      </div>
    </ScreenFrame>
  );
}
