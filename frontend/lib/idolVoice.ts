// 毎日ログインボーナスの文言の引き当て（DESIGN_D-4 §3）。
//
// 【この設計の要点＝キャラ軸と pt 軸を交差させない（D-4 §3.1）】
//   ・キャラ別文言（greet1/greet2/envelope/result1/result2/already）は **pt に一切依存しない**。
//     サーバー（GET /api/idols・/api/idols/limited の login_bonus_lines）から受け取る。
//   ・pt 別サブコピー（1/5/10）は **キャラに一切依存しない**中立文体の定数（BONUS_SUBCOPY）。
//   両者は独立に引き当てるため 7×3 の交差表は存在せず、キャラが1人増えても +0（サーバー側 +1行）、
//   pt 帯が1つ増えても +1文で済む。
//
// 【slug は「キー」であって「意味」ではない（D-4 §6.2 原則1）】
//   `if (idol_id === "rinaresu")` のような分岐は書かない。限定推しは月替わりで slug ごと
//   差し替わるため、必ず「引き当て or DEFAULT」の形にする。

import type { Idol, LoginBonusLines } from "./types";

/**
 * キャラ未定義 slug 用のフォールバック文言（DESIGN_D-4 §3.3 DEFAULT）。
 *
 * 内容は DESIGN_D-3 §3.1 の確定文言そのまま（「私」表記＝ D-3 §9-1 の決着を保持）。
 * 限定推しの差し替えで文言を用意し忘れても、ここに落ちるので画面は壊れない。
 * バックエンドの `seed.py::DEFAULT_LOGIN_LINES` と同一内容（API が落ちたときの保険）。
 */
export const DEFAULT_LOGIN_LINES: LoginBonusLines = {
  greet1: "{nickname}、今日も会いにきてくれてありがとう♡",
  greet2: "私からの気持ち、受け取ってね！",
  envelope: "はい、これ。あけてみて…♡",
  result1: "{points}ptをゲットしたよ！",
  result2: "また明日も会いにきてね！",
  already: "今日のぶんは もう受け取ってるみたい…！ また明日ね♡",
};

/**
 * 付与pt 別のサブコピー（DESIGN_D-4 §3.4・**全キャラ共通・中立文体**）。
 *
 * D-3 §3.2 の「pt 帯ごとの意図」はそのまま維持し、**文体だけを中立化**している。
 * 旧文言（`ちょっと多めに入れちゃった♪` 等）は女性キャラ前提の語尾・記号を含み、
 * イーサンの口から出た瞬間に破綻するため。ここをキャラ別にすると 21 パターンになる。
 * 体言止め・記号なしに寄せることで、直上のキャラ別 result の語尾が引き立つ。
 */
export const BONUS_SUBCOPY: Record<number, string> = {
  // pt の量に触れず、褒める対象を「来てくれたこと」に置き換える
  1: "きょう会えたのが いちばんうれしい",
  // 気持ちのおまけ、というトーン
  5: "きもち、ちょっと多めに",
  // 上振れの日だけ素直に喜ぶ（賭けの語彙は使わない）
  10: "今日はとくべつ。めいっぱい",
};

/**
 * 推しのログインボーナス文言を引き当てる。
 *
 * サーバーが文言を持っていない slug（月替わりで差し替えたばかりの限定推しなど）や、
 * `GET /api/idols` が失敗してフォールバック定義を使っている場合は DEFAULT に落ちる。
 */
export function resolveLoginLines(idol?: Idol | null): LoginBonusLines {
  return idol?.login_bonus_lines ?? DEFAULT_LOGIN_LINES;
}

/**
 * 付与pt に対応するサブコピーを返す。
 *
 * **フォールバック必須**（D-4 §8 #8）。付与pt候補は
 * `backend/app/services/login_bonus.py::BONUS_POINT_CHOICES` の定数で将来調整されうるため、
 * 例えば 3pt が追加された瞬間に undefined にならないよう 1pt のコピーへ落とす。
 */
export function resolveBonusSubcopy(points: number): string {
  return BONUS_SUBCOPY[points] ?? BONUS_SUBCOPY[1];
}

/**
 * `{nickname}` を差し込む。
 *
 * あだ名が取得できない場合は **先頭の `{nickname}、` ごと落とす**（DESIGN_D-3 §3.1 1-1）。
 * D-4 §3.2 の規約により `greet1` は必ず「`{nickname}、` ＋ 独立した1文」の形なので、
 * 前置を落とすだけで自然な文として成立する。
 */
export function applyNickname(template: string, nickname?: string): string {
  if (nickname) return template.replace("{nickname}", nickname);
  return template.replace(/^\{nickname\}、/, "").replace("{nickname}", "");
}

/** `{points}` を差し込む。 */
export function applyPoints(template: string, points: number): string {
  return template.replace("{points}", String(points));
}
