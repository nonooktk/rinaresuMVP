"use client";

// 毎日ログインボーナスの全画面オーバーレイ（3ステップ）。DESIGN_D-3 準拠。
//
//   ①挨拶（推し立ち絵＋コメント）→ タップ
//   ②封筒（タップで claim を1回だけ発火 → 開封＋ハートが舞う約1.2秒）
//   ③結果（◯ptをゲットしたよ！）→ タップで閉じる
//
// 設計上の要点:
//  - z-index は z-[80]。既存 GameDialog(90) / Toast(100) より**下**に置く。
//    結果を閉じたあとに開く達成ダイアログ・トーストが必ず前面に来るようにするため（D-3 §1.1）。
//  - claim を叩くのは**ステップ2の1回だけ**。途中離脱しても「ptは入ったが演出未視聴」に
//    ならず、翌アクセスで再度受け取れる（claim 未実行なら login_bonus_available が true のまま）。
//  - ハートの散らばり・回転は**固定配列**。レンダー中に Math.random() を使わない
//    （ハイドレーション不整合を避けるため。Sparkles と同じ方針）。
//  - prefers-reduced-motion 時は CSS のアニメ無効化だけでは 1.2 秒の無操作時間が残るため、
//    **JS 側でも待ち時間を 1200ms → 300ms に切り替える**（D-3 §4.5）。
//  - 演出はどの pt 値でも完全に同一（長さ・ハート数・色・サイズ）。値で変えるのは
//    結果のサブコピー1行だけ（D-3 §7）。
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import GameButton from "./GameButton";
import IdolImage from "./IdolImage";
import Sparkles from "./Sparkles";
import SpeechBubble from "./SpeechBubble";
import { api } from "@/lib/api";
import type { LoginBonusResult, User } from "@/lib/types";

// ---------------------------------------------------------------- 定数

/** 開封演出の長さ（D-3 §4.3）。pt 値によらず常に同じ長さにする。 */
const OPEN_ANIMATION_MS = 1200;
/** prefers-reduced-motion 時の待ち時間（D-3 §4.5）。動かないのに待たせない。 */
const REDUCED_ANIMATION_MS = 300;
/** claim の最大待ち時間。超えたらトースト＋クローズへ（D-3 §4.4）。 */
const CLAIM_TIMEOUT_MS = 3000;

/** ハート1個ぶんのパス（24×24 の viewBox 基準）。絵文字♡は環境ごとの字形差があるため SVG にする。 */
const HEART_PATH =
  "M12,21 C6,16 2,12.5 2,8.5 A4.5,4.5 0 0 1 12,6 A4.5,4.5 0 0 1 22,8.5 C22,12.5 18,16 12,21 Z";

/**
 * 舞い上がるハート7個の固定定義（D-3 §4.2）。
 * 個数・色・サイズは pt 値によらず固定。**乱数を使わない**ことでハイドレーション安全にする。
 * 色: --pink-600 ×3 / --pink-300 ×3 / --gold ×1
 */
const FLOATING_HEARTS = [
  { size: 18, color: "#f43f84", dx: -48, rot: -14, delay: 0 },
  { size: 14, color: "#ffa0c4", dx: -30, rot: -8, delay: 60 },
  { size: 22, color: "#f43f84", dx: -12, rot: -4, delay: 120 },
  { size: 18, color: "#ffd24c", dx: 0, rot: 0, delay: 180 },
  { size: 14, color: "#ffa0c4", dx: 14, rot: 6, delay: 240 },
  { size: 22, color: "#f43f84", dx: 32, rot: 10, delay: 300 },
  { size: 18, color: "#ffa0c4", dx: 50, rot: 16, delay: 360 },
] as const;

/** 結果サブコピー（D-3 §3.2）。pt の量に触れず「来てくれたこと」を褒める方向で出し分ける。 */
const RESULT_SUB_COPY: Record<number, string> = {
  1: "きょう会えたのが いちばんうれしい♡",
  5: "ちょっと多めに入れちゃった♪",
  10: "わっ、今日はとくべつ！ たくさん入れちゃった♡",
};

/** 次特典アイコン（DESIGN_D-2 §1.3 の対応表と同一）。 */
const NEXT_REWARD_ICON: Record<string, string> = {
  T1: "🌸",
  T2: "✨",
  T3: "🎫",
};

/** pt 数値の色。白地 5.91:1 / ベール上 4.82:1 で AA を満たす（D-3 §6.1）。 */
const POINT_COLOR = "#b3306b";

type Step = "greet" | "envelope" | "opening" | "result";

// ---------------------------------------------------------------- claim の発火管理

/**
 * claim の発火状態を**モジュールスコープ**（＝コンポーネントのマウント外）で保持する。
 *
 * 【R-3 M-1 対応】ガードをコンポーネント内の `useRef` だけに置くと、通信完了前に
 * オーバーレイ（や `/home`）がアンマウント→再マウントされた瞬間に初期化され、
 * `POST /api/login-bonus/claim` が何度も飛び得る（pt の二重付与は DB の UNIQUE 制約が
 * 防ぐが、LB-8 ③「二重タップ・連打のガード必須」の意図には届かない）。
 *
 * ここでは「1つのボーナス表示機会（`claimKey`）につき」
 *   - 初回 claim = **最大1リクエスト**（再マウントしても同じ Promise を共有する）
 *   - 復元のための再送 = **最大1リクエスト**（M-1 の意図した再送だけを許す）
 * に固定する。これにより「意図した再送」と「事故による多重発火」が構造的に区別される。
 *
 * `claimKey` はホーム側がオーバーレイを開くたびに新しく発行するため、翌日以降の
 * 新しいボーナス機会ではきちんと新規リクエストが飛ぶ（スロットは常に1つだけ保持）。
 */
let claimSlot: {
  key: string;
  first: Promise<LoginBonusResult>;
  resend?: Promise<LoginBonusResult>;
} | null = null;

/** 初回 claim。同じ `claimKey` なら再マウント後も同一リクエストを共有する。 */
function startClaim(claimKey: string): Promise<LoginBonusResult> {
  if (!claimSlot || claimSlot.key !== claimKey) {
    const first = api.claimLoginBonus();
    // 待ち合わせ前に reject しても未処理拒否にしない（後段で改めて await して捕まえる）
    first.catch(() => {});
    claimSlot = { key: claimKey, first };
  }
  return claimSlot.first;
}

/** 復元のための再送。同じ `claimKey` につき最大1回しか実リクエストを発行しない。 */
function resendClaim(claimKey: string): Promise<LoginBonusResult> {
  if (!claimSlot || claimSlot.key !== claimKey) return startClaim(claimKey);
  if (!claimSlot.resend) {
    const resend = api.claimLoginBonus();
    resend.catch(() => {});
    claimSlot.resend = resend;
  }
  return claimSlot.resend;
}

// ---------------------------------------------------------------- SVG パーツ

/** 単一のハート（装飾専用。意味はすべてテキスト側が持つ）。 */
function Heart({ size, color }: { size: number; color: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path d={HEART_PATH} fill={color} />
    </svg>
  );
}

/** SVG 内へハートを配置する（中心座標指定）。 */
function HeartShape({
  cx,
  cy,
  size,
  color,
}: {
  cx: number;
  cy: number;
  size: number;
  color: string;
}) {
  const scale = size / 24;
  return (
    <g transform={`translate(${cx - size / 2} ${cy - size / 2}) scale(${scale})`}>
      <path d={HEART_PATH} fill={color} />
    </g>
  );
}

/**
 * 封筒（インライン SVG・画像アセット追加なし。D-3 §4.1）。
 * 重なり順は body → letter → front → flap → seal。
 * letter を front より先に描くことで「中身が封筒の内側にある」ように見える。
 * 文字は SVG 内に一切載せない（テーマカラーによってはコントラストを保証できないため）。
 */
function EnvelopeSvg({
  themeColor,
  opening,
  reduced,
}: {
  themeColor: string;
  opening: boolean;
  reduced: boolean;
}) {
  return (
    <svg
      width={176}
      height={120}
      viewBox="0 0 176 120"
      aria-hidden="true"
      focusable="false"
      style={{ overflow: "visible" }}
    >
      <defs>
        <linearGradient id="lbEnvelopeBody" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fffdfe" />
          <stop offset="100%" stopColor="#ffe9f2" />
        </linearGradient>
        <linearGradient id="lbEnvelopeFlap" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={themeColor} />
          <stop offset="100%" stopColor={`${themeColor}cc`} />
        </linearGradient>
      </defs>

      {/* 本体 */}
      <rect
        x="2"
        y="26"
        width="172"
        height="92"
        rx="10"
        fill="url(#lbEnvelopeBody)"
        stroke="#ffa0c4"
        strokeWidth="2"
      />

      {/* 中身（レター）: 開封時に上へせり出す。0.30s 遅延で 0.55s（D-3 §4.3） */}
      <g
        style={{
          transform: opening ? "translateY(-26px)" : "translateY(0)",
          transition: reduced
            ? "none"
            : "transform 0.55s cubic-bezier(.18,.89,.32,1.28) 0.3s",
        }}
      >
        <rect
          x="22"
          y="18"
          width="132"
          height="84"
          rx="8"
          fill="#ffffff"
          stroke="#ffc2d9"
          strokeWidth="2"
        />
        <HeartShape cx={88} cy={60} size={40} color="#f43f84" />
      </g>

      {/* 前面の折り返し（中身より手前） */}
      <path d="M2,118 L88,62 L174,118 Z" fill="#ffe0ec" />

      {/* ふた（閉じた状態の下向き三角）。淡いテーマカラーでも背景から分離するよう白縁を常時付与 */}
      <path
        d="M2,26 L88,86 L174,26 Z"
        fill="url(#lbEnvelopeFlap)"
        stroke="#ffffff"
        strokeWidth="2"
        className={opening ? "animate-envelope-open" : ""}
      />

      {/* シール（開封で消える） */}
      <g
        style={{
          opacity: opening ? 0 : 1,
          transition: reduced ? "none" : "opacity 0.1s ease-out 0.1s",
        }}
      >
        <HeartShape cx={88} cy={60} size={22} color={POINT_COLOR} />
      </g>
    </svg>
  );
}

// ---------------------------------------------------------------- 本体

interface LoginBonusOverlayProps {
  /** 表示中のユーザー（推しスラッグ・あだ名・active_visual を使う） */
  user: User;
  /**
   * このボーナス表示機会を識別するキー（ホームが開くたびに新規発行する）。
   * claim の発火回数をマウントのライフサイクルから切り離すために使う（R-3 M-1）。
   */
  claimKey: string;
  /** 推しの表示名（未解決なら省略可） */
  idolName?: string;
  /** 推しのテーマカラー（封筒のふた・吹き出しの枠・ボタンに使う。文字色には使わない） */
  themeColor?: string;
  /**
   * オーバーレイを閉じたとき。
   * claim 済みなら結果、claim 前の離脱（Esc）なら null を渡す。
   */
  onFinish: (result: LoginBonusResult | null) => void;
  /** claim の失敗・タイムアウト時（呼び出し側でトースト＋クローズする） */
  onFail: () => void;
}

/** prefers-reduced-motion の判定（SSR・非対応環境では false）。 */
function detectReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export default function LoginBonusOverlay({
  user,
  claimKey,
  idolName,
  themeColor,
  onFinish,
  onFail,
}: LoginBonusOverlayProps) {
  const [step, setStep] = useState<Step>("greet");
  const [result, setResult] = useState<LoginBonusResult | null>(null);
  // 開封演出（1.2秒）が終わっても API が返ってこないときの待機中フラグ。
  // true の間はハートの余韻をループさせる（D-3 §4.4・QA_Q-6 m-1）。
  const [waiting, setWaiting] = useState(false);
  // タイムアウト後の再送で結果を復元したか（QA_Q-6 M-1）。
  // true なら `granted=false` でも「受け取れた」として通常の結果表示にする。
  const [recovered, setRecovered] = useState(false);
  // マウント時に一度だけ判定する（このコンポーネントはクライアント側でのみマウントされる）
  const [reduced] = useState<boolean>(detectReducedMotion);

  const rootRef = useRef<HTMLDivElement>(null);
  // claim の二重発火ガード（連打・多重タップ・キーボード同時押し）
  const claimedRef = useRef(false);
  // onFinish の二重呼び出しガード
  const finishedRef = useRef(false);
  // アンマウント後の setState を避けるための生存フラグ
  const aliveRef = useRef(true);
  const timersRef = useRef<number[]>([]);

  const theme = themeColor ?? "var(--pink-400)";
  // テーマカラーが CSS 変数（未解決）の場合、SVG グラデーションには実色が必要なので既定色にフォールバック
  const svgTheme = themeColor ?? "#ff87b2";
  const visual = user.active_visual === "special" ? "special" : "main";

  // アンマウント時に保留中のタイマーを片付ける
  useEffect(() => {
    aliveRef.current = true;
    const timers = timersRef;
    return () => {
      aliveRef.current = false;
      timers.current.forEach((id) => window.clearTimeout(id));
      timers.current = [];
    };
  }, []);

  // オーバーレイ表示中は背面のスクロールを止める
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  // 各ステップの主要ボタンへ初期フォーカスを当てる（演出中はルートへ退避）
  useEffect(() => {
    const target = rootRef.current?.querySelector<HTMLElement>(
      "[data-lb-autofocus]"
    );
    (target ?? rootRef.current)?.focus();
  }, [step]);

  const finish = useCallback(
    (value: LoginBonusResult | null) => {
      if (finishedRef.current) return;
      finishedRef.current = true;
      onFinish(value);
    },
    [onFinish]
  );

  /** 指定ミリ秒待つ（タイマーはアンマウント時にまとめて解除する）。 */
  const wait = useCallback(
    (ms: number) =>
      new Promise<void>((resolve) => {
        timersRef.current.push(window.setTimeout(resolve, ms));
      }),
    []
  );

  /** 指定ミリ秒で reject するタイマー（`Promise.race` の相方に使う）。 */
  const rejectAfter = useCallback(
    (ms: number) =>
      new Promise<never>((_, reject) => {
        timersRef.current.push(
          window.setTimeout(
            () => reject(new Error("login-bonus claim timeout")),
            ms
          )
        );
      }),
    []
  );

  /**
   * ステップ2: claim を1回だけ発火し、開封演出と足並みをそろえてステップ3へ進む。
   *
   * 【QA_Q-6 M-1 対応】claim がタイムアウト／通信失敗しても、サーバー側では付与が
   * 成功していることがある。その状態で「受け取れなかった」と閉じてしまうと、pt も
   * 特典解放の告知も永久に伝えられない。claim は**冪等**（`UNIQUE(user_id, bonus_date)`）
   * なので、失敗時は **1回だけ再送**して結果を復元する。
   */
  const openEnvelope = useCallback(async () => {
    // 【二重タップ・連打ガード（同一マウント内）】ここを通れるのは一度きり
    if (claimedRef.current) return;
    claimedRef.current = true;
    setStep("opening");

    // 演出は API の応答を待たずに即開始する（通信が遅い日に「タップしたのに無反応」に
    // ならないため）。ステップ3へ進むのは「演出完了」と「API 完了」の両方が揃ってから。
    // 【R-3 M-1】実リクエストの発行は startClaim() が claimKey 単位で1回に抑える
    // （再マウントで初期化されない）。
    let settled = false;
    const claimPromise = startClaim(claimKey).then(
      (r) => {
        settled = true;
        return r;
      },
      (e) => {
        settled = true;
        throw e;
      }
    );
    // 演出待ちの間に reject しても未処理拒否にしない（後段で改めて await して捕まえる）
    claimPromise.catch(() => {});

    // 開封演出の最短時間。pt 値によらず常に同じ長さ（D-3 §7-1）
    await wait(reduced ? REDUCED_ANIMATION_MS : OPEN_ANIMATION_MS);
    if (!aliveRef.current) return;

    try {
      // 【QA_Q-6 m-1 対応】API が演出より遅いときは、ハートの余韻をループさせたまま待つ
      // （D-3 §4.4。スピナーは出さない）。既に応答済みならループへ入れずそのまま進む。
      if (!settled) setWaiting(true);
      const claimed = await Promise.race([
        claimPromise,
        rejectAfter(CLAIM_TIMEOUT_MS),
      ]);
      if (!aliveRef.current) return;
      setWaiting(false);
      setResult(claimed);
      setStep("result");
      return;
    } catch {
      if (!aliveRef.current) return;
    }

    // ---- ここから復元（M-1） ----
    // 1回目の応答が取れなかった。サーバーには届いて付与済みの可能性があるため、
    // 冪等な claim を **1回だけ** 再送して当日の付与内容を取り直す。
    // 余韻ループは出したまま（ユーザーから見れば「まだ開封中」）。
    // 【R-3 M-1】この再送は resendClaim() が claimKey 単位で1リクエストに固定する
    // ＝「意図した再送」であり、事故による多重発火とは構造的に区別される。
    try {
      const restored = await Promise.race([
        resendClaim(claimKey),
        rejectAfter(CLAIM_TIMEOUT_MS),
      ]);
      if (!aliveRef.current) return;
      if (restored.points > 0) {
        // その日ぶんは実際に付与されていた → 通常どおり結果画面へ進める。
        // `granted` は false（付与したのは1回目）だが、体験としては「受け取れた」が正しい。
        setWaiting(false);
        setRecovered(true);
        setResult(restored);
        setStep("result");
        return;
      }
    } catch {
      if (!aliveRef.current) return;
    }

    // 再送でも復元できなかった＝本当に通信できていない。
    // ホームは壊さず、トースト＋クローズで復帰させる（D-3 §4.4・LB-10 ④）。
    setWaiting(false);
    onFail();
  }, [claimKey, reduced, onFail, wait, rejectAfter]);

  /** 画面タップ・進行ボタンの共通処理。演出中（opening）は何も受け付けない。 */
  const advance = useCallback(() => {
    if (step === "greet") {
      setStep("envelope");
    } else if (step === "envelope") {
      void openEnvelope();
    } else if (step === "result") {
      finish(result);
    }
  }, [step, openEnvelope, finish, result]);

  // Esc で閉じる／Tab をオーバーレイ内で循環させる（フォーカストラップ）。
  // ハンドラは ref 経由で最新化し、リスナー自体は付け外ししない。
  const keyHandlerRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyHandlerRef.current = (e: KeyboardEvent) => {
    if (step === "opening") return; // 演出中は操作不可

    if (e.key === "Escape") {
      e.preventDefault();
      // claim 済み（result あり）なら通常クローズと同じ扱い。未 claim なら翌アクセスで再表示。
      finish(result);
      return;
    }
    if (e.key !== "Tab") return;

    const root = rootRef.current;
    if (!root) return;
    const focusable = Array.from(
      root.querySelectorAll<HTMLElement>("button:not([disabled])")
    );
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  useEffect(() => {
    const listener = (e: KeyboardEvent) => keyHandlerRef.current(e);
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, []);

  // ---------- 表示用の値 ----------

  const greeting = user.nickname
    ? `${user.nickname}、今日も会いにきてくれてありがとう♡`
    : "今日も会いにきてくれてありがとう♡";

  const points = result?.points ?? 0;
  // 「受け取れた」として通常の結果（pt数値・サブコピー）を出すかどうか。
  // - 通常系（granted=true）はもちろん出す
  // - 【M-1】タイムアウト後の再送で復元した場合も、実際に付与されているので出す
  // - 初回 claim で granted=false（＝別経路で受領済み）のときだけ E-1 の文言にする
  const granted = (result?.granted === true || recovered) && points > 0;
  const monthlyPoints = result?.monthly_points ?? 0;
  const nextReward = result?.next_reward;
  const stackText =
    `こんげつ ${monthlyPoints}pt` +
    (nextReward
      ? ` ／ つぎの${NEXT_REWARD_ICON[nextReward.tier] ?? "✨"}まで あと${nextReward.remaining}pt`
      : "");

  // ステップ切替のクロスフェード（reduce 時は即時表示）
  const stepAnimation = reduced ? "" : "animate-dialog-in";
  // 封筒の待機ふわふわ（reduce 時は停止）
  const idleFloat = reduced ? "" : "animate-floaty";
  const isOpening = step === "opening";
  // 開封の最後（1.05〜1.20s）で封筒をフェードアウトさせる。reduce 時はフェードしない。
  const envelopeFadeStyle: CSSProperties = reduced
    ? {}
    : {
        opacity: isOpening ? 0 : 1,
        transition: "opacity 0.15s ease-out 1.05s",
      };

  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="lb-title"
      aria-busy={isOpening}
      tabIndex={-1}
      // aria-modal="true" により、支援技術は背面のホームを不活性として扱う。
      // z-[80]: GameDialog(90) / Toast(100) より下（D-3 §1.1）
      className="fixed inset-0 z-[80] flex justify-center outline-none backdrop-blur-sm"
      style={{
        background:
          "linear-gradient(160deg, rgba(255,240,246,0.97), rgba(255,224,236,0.97))",
      }}
      // 画面のどこをタップしても進む。全面を <button> にはしない（読み上げの二重化を避ける）
      onClick={advance}
    >
      <div
        className="relative flex min-h-[100dvh] w-full max-w-[430px] flex-col items-center justify-center px-6"
        style={{
          paddingTop: "calc(env(safe-area-inset-top, 0px) + 1.5rem)",
          paddingBottom: "calc(env(safe-area-inset-bottom, 0px) + 1.5rem)",
        }}
      >
        <Sparkles count={10} />

        <div
          // 封筒（envelope）と開封演出（opening）は**同一の DOM を保つ**。
          // ここで再マウントすると、ふた・レター・シールの CSS transition が
          // 「開始値からの変化」を持てず、演出が一瞬で終わってしまう。
          key={isOpening ? "envelope" : step}
          className={`relative flex w-full flex-col items-center ${stepAnimation} ${
            isOpening ? "pointer-events-none" : ""
          }`}
        >
          {/* ===== ステップ1: 挨拶 ===== */}
          {step === "greet" && (
            <>
              <div className="mb-4 w-full px-2">
                <SpeechBubble themeColor={theme}>
                  <span id="lb-title">
                    {greeting}
                    <br />
                    私からの気持ち、受け取ってね！
                  </span>
                </SpeechBubble>
              </div>
              <IdolImage
                idolId={user.idol_id}
                name={idolName}
                size={230}
                height={330}
                visual={visual}
                className={idleFloat}
              />
              <p className="mt-1 text-sm font-bold text-[var(--ink)]">
                {idolName ?? "推し"}
              </p>
              <div className="mt-4 w-full max-w-[240px]">
                <GameButton
                  fullWidth
                  themeColor={themeColor}
                  type="button"
                  data-lb-autofocus
                  onClick={(e) => {
                    e.stopPropagation();
                    advance();
                  }}
                >
                  うれしい！
                </GameButton>
              </div>
              <p className="mt-2 text-[11px] text-[var(--ink)]">
                がめんをタップしてもすすめるよ
              </p>
            </>
          )}

          {/* ===== ステップ2: 封筒 ／ 開封演出 ===== */}
          {(step === "envelope" || isOpening) && (
            <>
              <div className="mb-4 w-full px-2">
                <SpeechBubble themeColor={theme}>
                  <span id="lb-title">はい、これ。あけてみて…♡</span>
                </SpeechBubble>
              </div>
              <IdolImage
                idolId={user.idol_id}
                name={idolName}
                size={170}
                height={240}
                visual={visual}
                className={idleFloat}
              />

              {/* 封筒（タップ領域 200×160。SVG は 176×120） */}
              <div className="relative mt-3 h-[160px] w-[200px]">
                <button
                  type="button"
                  aria-label="封筒をあける"
                  data-lb-autofocus={step === "envelope" ? true : undefined}
                  disabled={isOpening}
                  onClick={(e) => {
                    e.stopPropagation();
                    void openEnvelope();
                  }}
                  className={`flex h-full w-full items-center justify-center rounded-3xl ${
                    isOpening ? "" : idleFloat
                  }`}
                  style={envelopeFadeStyle}
                >
                  <EnvelopeSvg
                    themeColor={svgTheme}
                    opening={isOpening}
                    reduced={reduced}
                  />
                </button>

                {/* 舞い上がるハート7個（装飾・固定配列） */}
                {isOpening && (
                  <div
                    className="pointer-events-none absolute inset-0"
                    aria-hidden="true"
                  >
                    {FLOATING_HEARTS.map((h, i) => (
                      <span
                        key={i}
                        // 【m-1】API が演出より遅いときは余韻をループさせて待つ（D-3 §4.4）
                        className={`absolute ${
                          waiting
                            ? "animate-heart-float-loop"
                            : "animate-heart-float"
                        }`}
                        style={
                          {
                            left: "50%",
                            top: 70,
                            marginLeft: -h.size / 2,
                            "--dx": `${h.dx}px`,
                            "--rot": `${h.rot}deg`,
                            animationDelay: `${h.delay}ms`,
                          } as CSSProperties
                        }
                      >
                        <Heart size={h.size} color={h.color} />
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {step === "envelope" && (
                <div className="mt-3 w-full max-w-[240px]">
                  <GameButton
                    fullWidth
                    themeColor={themeColor}
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void openEnvelope();
                    }}
                  >
                    あけてみる
                  </GameButton>
                </div>
              )}
            </>
          )}

          {/* ===== ステップ3: 結果 ===== */}
          {step === "result" && (
            <>
              {/* 切替時に自動で読み上げられるようにする */}
              <div
                aria-live="polite"
                className="flex w-full flex-col items-center"
              >
                <div className="mb-5 w-full px-2">
                  <SpeechBubble themeColor={theme}>
                    <span id="lb-title">
                      {granted ? (
                        <>
                          {points}ptをゲットしたよ！
                          <br />
                          また明日も会いにきてね！
                        </>
                      ) : (
                        <>
                          今日のぶんは もう受け取ってるみたい…！
                          <br />
                          また明日ね♡
                        </>
                      )}
                    </span>
                  </SpeechBubble>
                </div>

                {/* 本日受領済み（granted=false）では数値・サブコピーを出さない（D-3 E-1） */}
                {granted && (
                  <>
                    <Heart size={96} color="#f43f84" />
                    <p
                      className="mt-1 text-[32px] font-extrabold leading-none"
                      style={{ color: POINT_COLOR }}
                    >
                      {points}pt
                    </p>
                    <p className="mt-3 text-[13px] text-[var(--ink)]">
                      {RESULT_SUB_COPY[points] ?? "うけとってくれて ありがとう♡"}
                    </p>
                  </>
                )}

                {/* 積み上げ表示（D-3 §3.1 3-5・§7-4）。1pt の日でも合計は確実に増える */}
                <p className="mt-4 text-[13px] font-bold text-[var(--ink)]">
                  {stackText}
                </p>
              </div>

              <div className="mt-5 w-full max-w-[240px]">
                <GameButton
                  fullWidth
                  themeColor={themeColor}
                  type="button"
                  data-lb-autofocus
                  onClick={(e) => {
                    e.stopPropagation();
                    advance();
                  }}
                >
                  ホームへもどる
                </GameButton>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
