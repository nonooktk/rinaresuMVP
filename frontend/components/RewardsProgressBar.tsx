"use client";

// 特典プログレスバー（pt特典プログラム）— 動機づけ強化版（DESIGN_D-2 準拠）。
// ホーム上部の RankBadge 直下に置く。D-1 からの主な変更点:
//  - 上段を「⏰ 期間終了まで あと◯日」主表示＋「🌸 こんげつ◯pt」併記へ再編（締切効果で行動を後押し）
//  - マイルストーンを「アイコン+pt／短縮特典名」の2行ラベル付きカードへ（目標を言語化）
//  - 🎫T3（握手会抽選券）を RankBadge ゴールド配色で特別枠化（常時ゴールド輪郭・達成後は強調＋保有枚数バッジ）
//  - 促しコピーを「残日数＋特典名」の複合文へ（状態別に出し分け）
// 数値ロジック（次閾値・残pt）はバックエンド（GET /api/users/{id} の next_reward）を
// そのまま使い、フロントで閾値計算を再実装しない。残日数のみクライアント側で JST 固定計算（表示専用）。
import { useEffect, useState } from "react";
import type { NextReward, RewardsStatus } from "@/lib/types";
import { daysUntilMonthEndJST } from "@/lib/rewards";

interface RewardsProgressBarProps {
  monthlyPoints: number;
  nextReward?: NextReward | null;
  rewards?: RewardsStatus;
  nickname?: string;
  themeColor?: string;
}

// マイルストーン定義（当面狙う3段階）。label は表示用短縮名、fullName は aria-label 用の正式名称。
interface Milestone {
  key: "T1" | "T2" | "T3";
  icon: string;
  // 1行目に出す閾値ラベル（T3 は 1000pt〜 の固定表記）
  thresholdLabel: string;
  // 2行目に出す短縮特典名
  label: string;
  // 正式名称（aria-label / title 用）
  fullName: string;
  reached: boolean;
}

// tier → 促しコピーで使う特典アイコン・名称。next_reward.tier から機械的に差し込む。
const REWARD_META: Record<string, { icon: string; name: string }> = {
  T1: { icon: "🌸", name: "期間限定推し" },
  T2: { icon: "✨", name: "特殊ビジュアル" },
  T3: { icon: "🎫", name: "握手会抽選券" },
};

// ゴールド配色（RankBadge のランク3＝ゴールドを再利用。新色を増やさない）
const GOLD = "#f5b400";
const GOLD_GRAD = "linear-gradient(135deg,#ffe08a,#f5b400)";

export default function RewardsProgressBar({
  monthlyPoints,
  nextReward,
  rewards,
  nickname,
  themeColor,
}: RewardsProgressBarProps) {
  const mp = Math.max(monthlyPoints ?? 0, 0);

  // 残日数はクライアント時計依存のため、ハイドレーション不整合を避けてマウント後に算出する
  // （SSR と初回クライアントレンダーでは null＝数値を出さない）。
  const [days, setDays] = useState<number | null>(null);
  useEffect(() => {
    setDays(daysUntilMonthEndJST());
  }, []);

  const milestones: Milestone[] = [
    {
      key: "T1",
      icon: "🌸",
      thresholdLabel: "🌸100pt",
      label: "限定推し",
      fullName: "🌸100pt 期間限定推し",
      reached: mp >= 100,
    },
    {
      key: "T2",
      icon: "✨",
      thresholdLabel: "✨500pt",
      label: "ビジュアル",
      fullName: "✨500pt 特殊ビジュアル",
      reached: mp >= 500,
    },
    {
      key: "T3",
      icon: "🎫",
      thresholdLabel: "🎫1000pt〜",
      label: "握手会抽選券",
      fullName: "🎫1000pt以上 握手会抽選券",
      reached: mp >= 1000,
    },
  ];

  // バーの塗り割合: 現在の目標（next_reward.threshold）を最大値としたときの到達率。
  const barMax = nextReward?.threshold ?? 100;
  const pct = Math.min(Math.max(mp / barMax, 0), 1) * 100;

  // 当月コンプ判定（T1・T2 達成済み＝残るは T3 積み上げのみ）
  const allTierDone = mp >= 500;
  const t3Reached = mp >= 1000;

  const remaining = nextReward?.remaining ?? 0;
  const tickets = rewards?.tickets ?? 0;

  // 促しコピー（DESIGN_D-2 §3）。残日数＋特典名の複合文を基本形に、状態別で出し分ける。
  //  - 状態D（コンプ後・T3積み上げ中）を最優先で常時表示
  //  - 状態B（あと少し=進捗70%以上）／状態A（それ以外）
  // 月末当日（days===0）は専用文言へ差し替える。days===null（マウント前）は残日数を含めない単純形。
  const daysPrefix =
    days === 0 ? "今日まで！" : days !== null ? `あと${days}日！` : "";
  const meta = nextReward ? REWARD_META[nextReward.tier] : undefined;
  const rewardName = meta ? `${meta.icon}${meta.name}` : "特典";
  const progressRatio = nextReward ? mp / (nextReward.threshold || 1) : 1;

  let copy: string;
  if (!nextReward) {
    // 次目標が取れない場合の安全なフォールバック
    copy = allTierDone ? "ここからはボーナスタイムだよ♪" : "いっしょに集めよ、応援してるよ♪";
  } else if (allTierDone) {
    // 状態D: 当月全特典コンプ後（T3積み上げ中）— 最優先で毎回表示。
    // 当月チケット保有ありのときのみ「次の」を付ける（0枚のときは1枚目なので「次の」を外す）。
    const nextPrefix = tickets > 0 ? "次の" : "";
    copy =
      days === 0
        ? `今日まで！あと${remaining}ptで🎫${nextPrefix}握手会抽選券、間に合うよ！`
        : `${daysPrefix}あと${remaining}ptで🎫${nextPrefix}握手会抽選券！`;
  } else if (progressRatio >= 0.7) {
    // 状態B: あと少し
    copy =
      days === 0
        ? `今日まで！あと${remaining}ptで${rewardName}、間に合うよ！`
        : `${daysPrefix}あと${remaining}ptで${rewardName}、ドキドキしてきた♪`;
  } else {
    // 状態A: まだ遠い（あだ名があれば差し込み。無ければ複合形にフォールバック）
    copy = nickname
      ? `${daysPrefix}${nickname}ならあと${remaining}ptで${rewardName}に届くよ`
      : `${daysPrefix}あと${remaining}ptで${rewardName}、いっしょに集めよ♪`;
  }

  const fill = themeColor
    ? `linear-gradient(90deg, ${themeColor}, ${themeColor}cc)`
    : "linear-gradient(90deg, var(--pink-400), var(--pink-600))";

  // スクリーンリーダー向けのカウントダウン文言（DOM順: 主表示→バー→マイルストーン→コピー）
  const countdownText =
    days === 0
      ? "今月分は今日まで"
      : days !== null
        ? `今月分の期間終了まであと${days}日`
        : "今月分の期間はもうすぐ終了";

  return (
    <div
      className={`rounded-2xl bg-white/80 px-4 py-3 shadow backdrop-blur ${
        allTierDone ? "shadow-[0_0_12px_var(--pink-300)]" : ""
      }`}
    >
      {/* 上段: カウントダウン主表示（左・強調）＋ こんげつpt 併記（右・控えめ） */}
      <div className="mb-2 flex items-center justify-between gap-2">
        <span
          className="text-[13px] font-extrabold text-[var(--pink-600)]"
          aria-label={countdownText}
        >
          {days === 0
            ? "⏳ 今日まで！"
            : days !== null
              ? `⏰ 期間終了まで あと${days}日`
              : "⏰ 期間終了まで"}
        </span>
        <span className="shrink-0 text-[11px] font-bold text-[var(--ink-soft)]">
          🌸 こんげつ {mp}pt
        </span>
      </div>

      {/* プログレスバー本体（ピル型・D-1 踏襲） */}
      <div
        className="relative h-3 w-full overflow-hidden rounded-full bg-[var(--pink-100)]"
        role="progressbar"
        aria-valuenow={mp}
        aria-valuemin={0}
        aria-valuemax={barMax}
        aria-label={`今月の月間ポイント ${mp} / 次の特典まで ${barMax}。${countdownText}`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${pct}%`, background: fill }}
        />
      </div>

      {/* 下段: 3段階マイルストーン（特典名ラベル付きカード。T3のみゴールド特別枠） */}
      <div className="mt-2.5 flex items-stretch justify-between gap-1.5">
        {milestones.map((m) => {
          const isT3 = m.key === "T3";
          // T3 特別枠のスタイル（DESIGN_D-2 §2）
          const t3CardStyle = isT3
            ? {
                border: `1.5px solid ${t3Reached ? GOLD : "rgba(245,180,0,0.5)"}`,
                boxShadow: t3Reached
                  ? `0 0 0 2px ${GOLD}, 0 0 10px 1px rgba(245,180,0,0.5)`
                  : undefined,
              }
            : undefined;
          return (
            <div
              key={m.key}
              className={`relative flex flex-col items-center gap-1 rounded-xl py-1.5 ${
                isT3 ? "flex-[1.3] px-1" : "flex-1"
              } ${isT3 && t3Reached ? "scale-[1.04]" : ""}`}
              style={t3CardStyle}
              aria-label={m.fullName}
              title={m.fullName}
            >
              {/* アイコン丸（T3 は一回り大きく＝視線の到達点） */}
              <div
                className={`relative flex items-center justify-center rounded-full text-sm ${
                  isT3 ? "h-8 w-8" : "h-7 w-7 border-2"
                } ${
                  m.reached
                    ? isT3
                      ? "text-white"
                      : "border-transparent bg-[var(--pink-400)]"
                    : isT3
                      ? "bg-white"
                      : "border-[var(--pink-200)] bg-white opacity-40 grayscale"
                }`}
                style={
                  isT3 && m.reached ? { background: GOLD_GRAD } : undefined
                }
              >
                <span
                  aria-hidden
                  className={!m.reached && !isT3 ? "opacity-90" : ""}
                >
                  {m.icon}
                </span>
                {/* 達成済みは色だけに頼らず✓バッジ（形状差）でも区別（D-1 §5）。✓は左下・枚数バッジは右上で衝突回避。 */}
                {m.reached && (
                  <span
                    className={`absolute -bottom-1 -left-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white text-[8px] font-extrabold shadow ${
                      isT3 ? "text-[#c78a00]" : "text-[var(--pink-600)]"
                    }`}
                    aria-label="達成済み"
                  >
                    ✓
                  </span>
                )}
                {/* T3保有枚数バッジ（達成後のみ・右上）。DESIGN_D-2 §2 */}
                {isT3 && t3Reached && tickets > 0 && (
                  <span
                    className="absolute -right-2 -top-2 flex min-w-[18px] items-center justify-center rounded-full px-1 text-[9px] font-extrabold text-white shadow"
                    style={{ background: GOLD }}
                    aria-label={`握手会抽選券 ${tickets}枚 保有`}
                  >
                    🎫×{tickets}
                  </span>
                )}
                {/* 達成後のゆっくりしたゴールドきらめき（点滅なし・reduced-motion で無効化）。装飾のため固定位置。 */}
                {isT3 && t3Reached && (
                  <span aria-hidden>
                    <span className="animate-gold-fade pointer-events-none absolute -left-1.5 top-0 text-[9px] text-[#f5b400]">
                      ✦
                    </span>
                    <span
                      className="animate-gold-fade pointer-events-none absolute -right-1 bottom-0 text-[7px] text-[#ffcf4d]"
                      style={{ animationDelay: "1.2s" }}
                    >
                      ✧
                    </span>
                  </span>
                )}
              </div>
              {/* 1行目: アイコン+閾値。ラベル文字は小サイズ帯のためコントラスト重視で
                  T3 も --ink-soft（4.71:1）に統一する（ゴールドは枠・アイコン・バッジ・きらめきで表現・D-2 §6/QA F1）。 */}
              <span className="whitespace-nowrap text-[10px] font-bold text-[var(--ink-soft)]">
                {m.thresholdLabel}
              </span>
              {/* 2行目: 短縮特典名（最小9px。白カード上×--ink-soft でコントラスト担保・D-1 §5） */}
              <span
                className={`whitespace-nowrap text-[9px] font-bold text-[var(--ink-soft)] ${
                  !m.reached && !isT3 ? "opacity-60" : ""
                }`}
              >
                {m.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* 促しコピー（残日数＋特典名の複合文） */}
      <div className="mt-2">
        <span className="text-[11px] text-[var(--ink-soft)]">{copy}</span>
      </div>
    </div>
  );
}
