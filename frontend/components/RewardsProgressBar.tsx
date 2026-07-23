"use client";

// 特典プログレスバー（pt特典プログラム）。
// ホーム上部の RankBadge 直下に置き、「今月◯pt」「次特典まで残り◯pt」と
// 3段階マイルストーン（🌸100 / ✨500 / 🎫1000刻み）を表示する。
// デザイン指針: DESIGN_D-1_rewards-progress.md に準拠。
// 数値ロジック（次閾値・残pt）はバックエンド（GET /api/users/{id} の next_reward）を
// そのまま使い、フロントで閾値計算を再実装しない。
import type { NextReward, RewardsStatus } from "@/lib/types";

interface RewardsProgressBarProps {
  monthlyPoints: number;
  nextReward?: NextReward | null;
  rewards?: RewardsStatus;
  nickname?: string;
  themeColor?: string;
}

// マイルストーン定義（当面狙う3段階）。T3 は「直近で狙う次の1000刻み」を動的に差し込む。
interface Milestone {
  key: string;
  icon: string;
  threshold: number;
  reached: boolean;
}

export default function RewardsProgressBar({
  monthlyPoints,
  nextReward,
  rewards,
  nickname,
  themeColor,
}: RewardsProgressBarProps) {
  const mp = Math.max(monthlyPoints ?? 0, 0);

  // 直近で狙う T3 の閾値（未達なら next_reward、達成済みなら現在ptの1つ上の1000刻み）
  const nextT3 =
    nextReward && nextReward.tier === "T3"
      ? nextReward.threshold
      : (Math.floor(mp / 1000) + 1) * 1000;

  const milestones: Milestone[] = [
    { key: "T1", icon: "🌸", threshold: 100, reached: mp >= 100 },
    { key: "T2", icon: "✨", threshold: 500, reached: mp >= 500 },
    { key: "T3", icon: "🎫", threshold: nextT3, reached: mp >= 1000 },
  ];

  // バーの塗り割合: 現在の目標（next_reward.threshold）を最大値としたときの到達率。
  const barMax = nextReward?.threshold ?? 100;
  const pct = Math.min(Math.max(mp / barMax, 0), 1) * 100;

  // 当月コンプ判定（T1・T2 達成済み＝残るは T3 積み上げのみ）
  const allTierDone = mp >= 500;

  // 促しコピー（D-1 §2）。あだ名が取れれば差し込む。
  const remaining = nextReward?.remaining ?? 0;
  const progressRatio = nextReward ? mp / (nextReward.threshold || 1) : 1;
  let copy: string;
  if (allTierDone) {
    copy = "ここからはボーナスタイムだよ♪";
  } else if (progressRatio >= 0.7) {
    copy = "あと少し…！ ドキドキしてきた♪";
  } else {
    copy = nickname
      ? `コツコツいこ！ ${nickname}ならできるよ`
      : "いっしょに集めよ、応援してるよ♪";
  }

  const fill = themeColor
    ? `linear-gradient(90deg, ${themeColor}, ${themeColor}cc)`
    : "linear-gradient(90deg, var(--pink-400), var(--pink-600))";

  const tickets = rewards?.tickets ?? 0;

  return (
    <div
      className={`rounded-2xl bg-white/80 px-4 py-3 shadow backdrop-blur ${
        allTierDone ? "shadow-[0_0_12px_var(--pink-300)]" : ""
      }`}
    >
      {/* 上段: 今月pt / 次特典まで残りpt */}
      <div className="mb-2 flex items-center justify-between text-[12px] font-bold">
        <span className="text-[var(--ink)]">🌸 こんげつ {mp}pt</span>
        {nextReward ? (
          <span className="text-[var(--ink-soft)]">
            {allTierDone ? "つぎの抽選券まで" : "つぎまで"} あと{remaining}pt
          </span>
        ) : null}
      </div>

      {/* プログレスバー本体（ピル型） */}
      <div
        className="relative h-3 w-full overflow-hidden rounded-full bg-[var(--pink-100)]"
        role="progressbar"
        aria-valuenow={mp}
        aria-valuemin={0}
        aria-valuemax={barMax}
        aria-label={`今月の月間ポイント ${mp} / 次の特典まで ${barMax}`}
      >
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${pct}%`, background: fill }}
        />
      </div>

      {/* 下段: 3段階マイルストーン */}
      <div className="mt-2 flex items-start justify-between">
        {milestones.map((m) => (
          <div key={m.key} className="flex flex-col items-center gap-0.5">
            <div
              className={`relative flex h-7 w-7 items-center justify-center rounded-full border-2 text-sm ${
                m.reached
                  ? "border-transparent bg-[var(--pink-400)]"
                  : "border-[var(--pink-200)] bg-white opacity-40 grayscale"
              }`}
            >
              <span aria-hidden>{m.icon}</span>
              {/* 達成済みは色だけに頼らず✓バッジ（形状差）でも区別（D-1 §5） */}
              {m.reached && (
                <span
                  className="absolute -bottom-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-white text-[8px] font-extrabold text-[var(--pink-600)] shadow"
                  aria-label="達成済み"
                >
                  ✓
                </span>
              )}
            </div>
            <span className="text-[10px] font-bold text-[var(--ink-soft)]">
              {m.threshold}
            </span>
          </div>
        ))}
      </div>

      {/* 促しコピー＋抽選券保有数（補助表示） */}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[11px] text-[var(--ink-soft)]">{copy}</span>
        {tickets > 0 && (
          <span className="text-[10px] font-bold text-[var(--ink-soft)]">
            🎫 保有{tickets}枚
          </span>
        )}
      </div>
    </div>
  );
}
