// ランクバッジ（rank 1〜3 を☆の数とメダル色で表現）＋現在ポイント表示
interface RankBadgeProps {
  rank: number;
  points: number;
}

// ランク別のメダル色・ラベル
const RANK_STYLES: Record<
  number,
  { grad: string; label: string; ring: string }
> = {
  1: {
    grad: "linear-gradient(135deg,#e6a15c,#c77b34)", // ブロンズ
    label: "ブロンズ",
    ring: "#c77b34",
  },
  2: {
    grad: "linear-gradient(135deg,#cfd6e0,#9aa6b8)", // シルバー
    label: "シルバー",
    ring: "#9aa6b8",
  },
  3: {
    grad: "linear-gradient(135deg,#ffe08a,#f5b400)", // ゴールド
    label: "ゴールド",
    ring: "#f5b400",
  },
};

export default function RankBadge({ rank, points }: RankBadgeProps) {
  const style = RANK_STYLES[rank] ?? RANK_STYLES[1];
  const stars = Math.min(Math.max(rank, 1), 3);

  return (
    <div className="flex items-center gap-2 rounded-full bg-white/90 px-3 py-1.5 shadow-md backdrop-blur">
      {/* メダル */}
      <div
        className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-extrabold text-white shadow"
        style={{ background: style.grad }}
        title={style.label}
      >
        {"★".repeat(stars)}
      </div>
      {/* ポイント */}
      <div className="flex flex-col leading-none">
        <span className="text-[10px] font-bold text-[var(--ink-soft)]">
          {style.label}
        </span>
        <span className="text-sm font-extrabold text-[var(--pink-600)]">
          {points.toLocaleString()}
          <span className="ml-0.5 text-[10px]">pt</span>
        </span>
      </div>
    </div>
  );
}
