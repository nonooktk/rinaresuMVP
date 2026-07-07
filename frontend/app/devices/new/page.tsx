"use client";

// 新規デバイス追加（/devices/new）4ステップウィザード
// Step1: 注意事項（回収対象・データ消去の案内）に同意して次へ
// Step2: 撮影（写真を選択→プレビュー表示）→ POST /api/devices/classify
// Step3: 判定候補から1つ選ぶ（手動選択も device-types マスタから可能）
// Step4: POST /api/devices で登録 → 完了ダイアログ → ホームへ
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import GameButton from "@/components/GameButton";
import GameDialog from "@/components/GameDialog";
import Sparkles from "@/components/Sparkles";
import { useToast } from "@/components/Toast";
import { api, mediaUrl } from "@/lib/api";
import { getStoredUser } from "@/lib/session";
import type { ClassifyResult, DeviceType } from "@/lib/types";

const STEPS = ["注意事項", "写真をとる", "種類をえらぶ", "登録"];

// 回収対象・注意事項（FAQシードの内容に沿った自然な文面）
const NOTICES = [
  {
    icon: "📱",
    title: "回収できるもの",
    body:
      "スマホ・ガラケー・タブレット・デジカメ・携帯ゲーム機など、家庭の小型端末（都市鉱山）が対象だよ。",
  },
  {
    icon: "🔒",
    title: "データはしっかり消去",
    body:
      "提携業者が専用ソフトで写真や連絡先を完全に消去してくれるから、初期化しなくても大丈夫。消去証明も発行されるよ。",
  },
  {
    icon: "✨",
    title: "きれいに写してね",
    body:
      "端末が中央に写るように撮ると、種類の判定がうまくいくよ。うまく判定できなくても、あとから手動で選べるから安心してね。",
  },
];

export default function NewDevicePage() {
  const router = useRouter();
  const { show } = useToast();

  const [step, setStep] = useState(0);
  // 撮影
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [classifying, setClassifying] = useState(false);
  // 判定
  const [result, setResult] = useState<ClassifyResult | null>(null);
  const [selectedType, setSelectedType] = useState<string | null>(null);
  const [deviceTypes, setDeviceTypes] = useState<DeviceType[]>([]);
  const [manualOpen, setManualOpen] = useState(false);
  // 登録
  const [registering, setRegistering] = useState(false);
  const [doneOpen, setDoneOpen] = useState(false);
  const [earnedPoints, setEarnedPoints] = useState(0);

  // セッションガード（未ログインならタイトルへ）
  useEffect(() => {
    if (!getStoredUser()) router.replace("/");
  }, [router]);

  // 手動選択用のデバイス種別マスタを取得（失敗しても致命的ではない）
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const types = await api.getDeviceTypes();
        if (alive) setDeviceTypes(types);
      } catch {
        /* 手動選択が使えないだけなので黙って無視 */
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // オブジェクトURLの後始末（メモリリーク防止）
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  // 選択中の候補ラベル・ポイント（判定候補＋手動選択の両方から解決）
  const selected = useMemo(() => {
    if (!selectedType) return null;
    const cand = result?.candidates.find((c) => c.device_type === selectedType);
    if (cand) return { label: cand.label, points: cand.points };
    const dt = deviceTypes.find((t) => t.code === selectedType);
    if (dt) return { label: dt.label, points: dt.points };
    return null;
  }, [selectedType, result, deviceTypes]);

  // 写真を選んだら即プレビュー＆判定へ進む
  const onPick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    // 前のプレビューを破棄
    if (preview) URL.revokeObjectURL(preview);
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setSelectedType(null);
  };

  // 判定を実行し、成功したら判定ステップへ
  const doClassify = async () => {
    if (!file) return;
    setClassifying(true);
    try {
      const res = await api.classifyDevice(file);
      setResult(res);
      // 最有力候補を初期選択にしておく
      setSelectedType(res.candidates[0]?.device_type ?? null);
      setStep(2);
    } catch {
      show("判定に失敗しました。時間をおいて試してね");
    } finally {
      setClassifying(false);
    }
  };

  // デバイスを登録
  const doRegister = async () => {
    if (!selectedType) return;
    setRegistering(true);
    try {
      const device = await api.createDevice({
        device_type: selectedType,
        photo_id: result?.photo_id,
      });
      setEarnedPoints(device.points);
      setDoneOpen(true);
    } catch {
      show("登録に失敗しました。時間をおいて試してね");
    } finally {
      setRegistering(false);
    }
  };

  // もどる（ステップ内なら1つ戻る／先頭ならホームへ）
  const back = () => {
    if (step > 0) setStep(step - 1);
    else router.push("/home");
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
          新規デバイス追加
        </h1>
      </header>

      {/* ステップインジケーター（registerと同じ作法） */}
      <div className="relative mb-5 flex items-center justify-center gap-2">
        {STEPS.map((_, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-extrabold transition-colors ${
                i <= step
                  ? "bg-[var(--pink-500)] text-white shadow"
                  : "bg-[var(--pink-100)] text-[var(--pink-300)]"
              }`}
            >
              {i + 1}
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`h-1 w-5 rounded-full ${
                  i < step ? "bg-[var(--pink-400)]" : "bg-[var(--pink-100)]"
                }`}
              />
            )}
          </div>
        ))}
      </div>
      <p className="relative mb-4 text-center text-sm font-bold text-[var(--ink)]">
        STEP {step + 1}. {STEPS[step]}
      </p>

      {/* 本文 */}
      <div className="relative flex flex-1 flex-col overflow-y-auto pb-2">
        {/* ===== Step1: 注意事項 ===== */}
        {step === 0 && (
          <div className="flex flex-col gap-3">
            {NOTICES.map((n) => (
              <div
                key={n.title}
                className="flex gap-3 rounded-2xl border-2 border-[var(--pink-100)] bg-white p-4 shadow-sm"
              >
                <div className="text-2xl">{n.icon}</div>
                <div className="min-w-0">
                  <p className="font-bold text-[var(--ink)]">{n.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--ink-soft)]">
                    {n.body}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ===== Step2: 撮影 ===== */}
        {step === 1 && (
          <div className="flex flex-col items-center gap-4">
            <p className="text-center text-sm text-[var(--ink-soft)]">
              回収したい端末の写真をとってね。
              <br />
              カメラでも、保存済みの画像でもOK！
            </p>

            {/* プレビュー枠（兼ファイル選択トリガー） */}
            <label className="flex aspect-square w-full max-w-[280px] cursor-pointer items-center justify-center overflow-hidden rounded-3xl border-2 border-dashed border-[var(--pink-300)] bg-[var(--pink-50)]">
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={preview}
                  alt="えらんだ写真"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex flex-col items-center gap-2 text-[var(--pink-400)]">
                  <span className="text-5xl">📷</span>
                  <span className="text-sm font-bold">タップして撮影・選択</span>
                </div>
              )}
              <input
                type="file"
                accept="image/*"
                capture="environment"
                onChange={onPick}
                className="hidden"
              />
            </label>

            {preview && (
              <p className="text-xs text-[var(--ink-soft)]">
                写真をとりなおす場合は、もう一度タップしてね
              </p>
            )}
          </div>
        )}

        {/* ===== Step3: 判定候補から選ぶ ===== */}
        {step === 2 && (
          <div className="flex flex-col gap-3">
            <p className="text-center text-sm text-[var(--ink-soft)]">
              写真から種類を判定したよ。
              <br />
              合っているものを選んでね♪
            </p>

            {/* プレビュー（小） */}
            {result?.photo_url && (
              <div className="mx-auto h-24 w-24 overflow-hidden rounded-2xl bg-[var(--pink-50)] shadow-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl(result.photo_url)}
                  alt="判定した写真"
                  className="h-full w-full object-cover"
                />
              </div>
            )}

            <ul className="flex flex-col gap-2">
              {result?.candidates.map((c) => {
                const active = c.device_type === selectedType;
                return (
                  <li key={c.device_type}>
                    <button
                      onClick={() => setSelectedType(c.device_type)}
                      className={`flex w-full items-center gap-3 rounded-2xl border-2 bg-white p-3 text-left transition-transform active:scale-[0.98] ${
                        active
                          ? "border-[var(--pink-400)] shadow"
                          : "border-[var(--pink-100)]"
                      }`}
                    >
                      {/* 選択マーカー */}
                      <span
                        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${
                          active ? "bg-[var(--pink-500)]" : "bg-[var(--pink-100)]"
                        }`}
                      >
                        {active ? "✓" : ""}
                      </span>
                      <span className="flex-1 font-bold text-[var(--ink)]">
                        {c.label}
                      </span>
                      {/* 信頼度 */}
                      <span className="text-[11px] font-bold text-[var(--ink-soft)]">
                        一致度 {Math.round(c.confidence * 100)}%
                      </span>
                      <span className="text-sm font-bold text-[var(--pink-600)]">
                        {c.points}pt
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            {/* 手動選択（該当なし時） */}
            <button
              onClick={() => setManualOpen(true)}
              className="mt-1 text-center text-xs font-bold text-[var(--pink-500)] underline"
            >
              候補にない・ちがうときは手動で選ぶ
            </button>

            {/* 手動選択に切り替えた場合の表示 */}
            {selected &&
              !result?.candidates.some(
                (c) => c.device_type === selectedType
              ) && (
                <div className="rounded-2xl border-2 border-[var(--pink-400)] bg-white p-3 text-center text-sm font-bold text-[var(--ink)] shadow">
                  手動で選択中: {selected.label}（{selected.points}pt）
                </div>
              )}
          </div>
        )}

        {/* ===== Step4: 登録内容の確認 ===== */}
        {step === 3 && (
          <div className="flex flex-col items-center gap-4">
            <p className="text-center text-sm text-[var(--ink-soft)]">
              この内容で登録するよ。
              <br />
              よければ「登録する」を押してね！
            </p>

            {(preview || result?.photo_url) && (
              <div className="h-40 w-40 overflow-hidden rounded-3xl bg-[var(--pink-50)] shadow-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={result?.photo_url ? mediaUrl(result.photo_url) : preview}
                  alt="登録する写真"
                  className="h-full w-full object-cover"
                />
              </div>
            )}

            <div className="w-full rounded-2xl border-2 border-[var(--pink-100)] bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm text-[var(--ink-soft)]">種類</span>
                <span className="font-bold text-[var(--ink)]">
                  {selected?.label ?? "-"}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <span className="text-sm text-[var(--ink-soft)]">獲得予定</span>
                <span className="text-lg font-extrabold text-[var(--pink-600)]">
                  {selected?.points ?? 0}pt
                </span>
              </div>
            </div>
            <p className="text-center text-[11px] text-[var(--ink-soft)]">
              ※ ポイントはりなれすが受領・確認したあとに付与されるよ
            </p>
          </div>
        )}
      </div>

      {/* フッター操作 */}
      <div className="relative mt-4">
        {step === 0 && (
          <GameButton fullWidth onClick={() => setStep(1)}>
            同意して次へ ▶
          </GameButton>
        )}

        {step === 1 && (
          <GameButton
            fullWidth
            disabled={!file || classifying}
            onClick={doClassify}
          >
            {classifying ? "判定中…" : "この写真で判定する ▶"}
          </GameButton>
        )}

        {step === 2 && (
          <GameButton
            fullWidth
            disabled={!selectedType}
            onClick={() => setStep(3)}
          >
            この種類で進む ▶
          </GameButton>
        )}

        {step === 3 && (
          <GameButton
            fullWidth
            disabled={!selectedType || registering}
            onClick={doRegister}
          >
            {registering ? "登録中…" : "✨ 登録する"}
          </GameButton>
        )}
      </div>

      {/* 手動選択ダイアログ */}
      {manualOpen && (
        <div
          className="fixed inset-0 z-[90] flex items-center justify-center p-6"
          style={{ background: "rgba(90,58,74,0.45)" }}
          onClick={() => setManualOpen(false)}
        >
          <div
            className="animate-dialog-in relative flex max-h-[80dvh] w-full max-w-[360px] flex-col overflow-hidden rounded-3xl bg-white shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 text-center text-lg font-extrabold text-white [background:linear-gradient(135deg,var(--pink-400),var(--pink-500))]">
              種類を手動で選ぶ
            </div>
            <ul className="flex flex-col gap-2 overflow-y-auto px-5 py-5">
              {deviceTypes.map((t) => (
                <li key={t.code}>
                  <button
                    onClick={() => {
                      setSelectedType(t.code);
                      setManualOpen(false);
                    }}
                    className="flex w-full items-center justify-between rounded-2xl border-2 border-[var(--pink-100)] bg-white p-3 text-left transition-transform active:scale-[0.98]"
                  >
                    <span className="font-bold text-[var(--ink)]">
                      {t.label}
                    </span>
                    <span className="text-sm font-bold text-[var(--pink-600)]">
                      {t.points}pt
                    </span>
                  </button>
                </li>
              ))}
              {deviceTypes.length === 0 && (
                <li className="py-4 text-center text-sm text-[var(--ink-soft)]">
                  種別一覧を取得できませんでした
                </li>
              )}
            </ul>
            <div className="px-6 pb-6">
              <GameButton
                variant="secondary"
                fullWidth
                onClick={() => setManualOpen(false)}
              >
                とじる
              </GameButton>
            </div>
          </div>
        </div>
      )}

      {/* 完了ダイアログ */}
      <GameDialog
        open={doneOpen}
        title="登録 完了！"
        hideCancel
        confirmLabel="ホームへもどる"
        onConfirm={() => router.push("/home")}
      >
        デバイスを登録したよ！
        <br />
        獲得予定ポイントは{" "}
        <span className="font-extrabold text-[var(--pink-600)]">
          {earnedPoints}pt
        </span>{" "}
        。<br />
        「りなれすに送る」から伝票を出して送ってね♪
      </GameDialog>
    </ScreenFrame>
  );
}
