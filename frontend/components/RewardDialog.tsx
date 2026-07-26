"use client";

// 特典達成演出（Toast 文面＋達成ダイアログ）の共用コンポーネント。
//
// もともと app/history/page.tsx 内に直書きされていた達成演出（rewardsToastMessage /
// 特典種別ごとの説明マップ / 達成 GameDialog）を、履歴の検収フローと
// 毎日ログインボーナス（LoginBonusOverlay 後の接続）で共用するために切り出したもの。
// **見た目・文言・挙動は history の現行実装と完全に同一**（リグレッション禁止）。
import GameDialog from "./GameDialog";
import type { RewardGranted } from "@/lib/types";

// 付与特典（複数可）を1つにまとめたトースト文面を作る（D-1 §3.1）。
// 呼び出し側は `show(\`✨ ${rewardsToastMessage(granted)}\`, "success")` の形で使う。
export function rewardsToastMessage(granted: RewardGranted[]): string {
  if (granted.length === 1) {
    const type = granted[0].reward_type;
    if (type === "limited_idol") return "期間限定推しが解放されたよ！";
    if (type === "special_visual") return "特殊ビジュアルをゲットしたよ！";
    return "握手会の抽選券をゲット！";
  }
  return `特典を${granted.length}個ゲット！ 詳しくはダイアログをチェック`;
}

// 特典種別ごとの達成ダイアログ用の説明（アイコン＋名称＋一言）。
function rewardDialogLine(g: RewardGranted): { icon: string; note: string } {
  if (g.reward_type === "limited_idol") {
    return { icon: "🌸", note: "今月いっぱい /oshi で選べるよ" };
  }
  if (g.reward_type === "special_visual") {
    return { icon: "✨", note: "ホームからいつでも切り替えられるよ" };
  }
  return { icon: "🎫", note: "抽選の権利がたまっていくよ" };
}

interface RewardDialogProps {
  /** 表示するかどうか（granted が空のときは open でも表示しない） */
  open: boolean;
  /** 今回新規付与された特典の一覧 */
  granted: RewardGranted[];
  /** 「うれしい！」または背景タップで閉じたとき。呼び出し側が次の演出へ繋ぐ */
  onClose: () => void;
}

export default function RewardDialog({
  open,
  granted,
  onClose,
}: RewardDialogProps) {
  return (
    <GameDialog
      open={open && granted.length > 0}
      title="とくてん げっとだよ！"
      hideCancel
      confirmLabel="うれしい！"
      onConfirm={onClose}
      onCancel={onClose}
    >
      <div className="flex flex-col gap-3 text-left">
        {granted.map((g, i) => {
          const line = rewardDialogLine(g);
          return (
            <div key={`${g.tier}-${g.threshold}-${i}`}>
              <p className="font-bold text-[var(--ink)]">
                {line.icon} {g.label} をゲット！
              </p>
              <p className="text-[12px] text-[var(--ink-soft)]">{line.note}</p>
            </div>
          );
        })}
      </div>
    </GameDialog>
  );
}
