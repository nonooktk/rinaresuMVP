// 特典プログラム（月間pt）のフロント側ユーティリティ。
// 月間ptは JST（Asia/Tokyo）基準で当月末に遅延リセットされる（backend app/services/monthly.py と同基準）。
// ここではその「当月末までの残り日数」を JST 固定で算出する。
// 注意: あくまで表示専用。サーバーのリセット判定には使わない（クライアント時計依存を許容する前提）。

import type { RewardGranted, RewardsStatus } from "./types";

// 指定インスタント（既定は現在時刻）を JST の暦要素（年・月・日）に分解する。
// Intl で timeZone を Asia/Tokyo に固定するため、実行環境のローカルTZに依存しない。
function jstYmd(now: Date): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const pick = (type: string) =>
    Number(parts.find((p) => p.type === type)?.value ?? "0");
  return { year: pick("year"), month: pick("month"), day: pick("day") };
}

/**
 * JST（Asia/Tokyo）基準で「当月末日 23:59」までの残り日数を返す。
 *
 * - 単純な日数差（当月末日 − 今日）で、当日を 0 として扱う（DESIGN_D-2 §4）。
 *   例: JST 7/23 → 当月末 7/31 まで「あと 8 日」／JST 7/31 → 0（＝「今日まで！」）。
 * - うるう年・各月の日数差は `Date.UTC(year, month, 0)` が月末日を返すため自動対応する
 *   （month は 1 始まりで渡すと「翌月の 0 日目＝当月末日」になる）。
 * - クライアントのローカルTZに依存せず JST 固定で算出する。
 *
 * @param now 基準インスタント（テスト用に注入可能。既定は現在時刻）
 * @returns 0 以上の整数（当月末日なら 0）
 */
export function daysUntilMonthEndJST(now: Date = new Date()): number {
  const { year, month, day } = jstYmd(now);
  // month は 1 始まり。Date.UTC(year, month, 0) = 当月末日（翌月の 0 日目）。
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return Math.max(lastDay - day, 0);
}

/**
 * 特典保有状況（`rewards`）の**前後の差分**から「今回新たに解放された特典」を組み立てる。
 *
 * 【QA_Q-6 M-1 対応】達成演出に使う `rewards_granted[]` は claim / 受領のレスポンスにしか
 * 含まれず、`GET /api/users/{id}` からは取れない。そのためレスポンスを取り逃した経路
 * （claim のタイムアウト・通信断のあとに再取得で復元した場合）では、達成演出を出す材料が
 * 無くなってしまう。ここでは保有状況のスナップショットを突き合わせて解放を検知し、
 * 演出に必要な最小限の情報を復元する。
 *
 * - あくまで**フォールバック**。レスポンスから `rewards_granted[]` が取れる通常系では使わない。
 * - `threshold` は保有状況からは特定できないため 0（不明）を入れる。`RewardDialog` /
 *   `rewardsToastMessage` は `reward_type` と `label` しか使わないため表示に影響しない。
 *
 * @param before オーバーレイ（または受領）を開始する直前の保有状況
 * @param after  処理後に再取得した保有状況
 * @returns 新たに解放された特典の一覧（無ければ空配列）
 */
export function diffGrantedRewards(
  before: RewardsStatus | null | undefined,
  after: RewardsStatus | null | undefined
): RewardGranted[] {
  // どちらか一方でも取れていなければ「解放された」と断定できない（誤検知を避ける）
  if (!before || !after) return [];

  const granted: RewardGranted[] = [];

  if (!before.limited_idol_active && after.limited_idol_active) {
    granted.push({
      tier: "T1",
      threshold: 0,
      reward_type: "limited_idol",
      label: "期間限定推し",
    });
  }
  if (!before.special_visual && after.special_visual) {
    granted.push({
      tier: "T2",
      threshold: 0,
      reward_type: "special_visual",
      label: "特殊ビジュアル",
    });
  }
  // 抽選券は積み上げ式。増えた枚数だけ列挙する（1回の処理で複数枚増えることがある）
  const addedTickets = Math.max((after.tickets ?? 0) - (before.tickets ?? 0), 0);
  for (let i = 0; i < addedTickets; i++) {
    granted.push({
      tier: "T3",
      threshold: 0,
      reward_type: "handshake_ticket",
      label: "握手会抽選券",
    });
  }

  return granted;
}
