// 特典プログラム（月間pt）のフロント側ユーティリティ。
// 月間ptは JST（Asia/Tokyo）基準で当月末に遅延リセットされる（backend app/services/monthly.py と同基準）。
// ここではその「当月末までの残り日数」を JST 固定で算出する。
// 注意: あくまで表示専用。サーバーのリセット判定には使わない（クライアント時計依存を許容する前提）。

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
