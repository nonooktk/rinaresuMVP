"use client";

// ホーム画面（/home）
// - 右上: ポイント＆ランクバッジ（GET /api/users/{id} で最新化）
// - 中央: 推しアイドルの大きなイラスト
// - 上部: 吹き出しコメント（表示のたびに GET /api/users/{id}/comment）
// - 下部: メニュー各種＋ログアウト（確認ダイアログ）
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import Sparkles from "@/components/Sparkles";
import GameButton from "@/components/GameButton";
import GameDialog from "@/components/GameDialog";
import SpeechBubble from "@/components/SpeechBubble";
import RankBadge from "@/components/RankBadge";
import IdolImage from "@/components/IdolImage";
import LoginBonusOverlay from "@/components/LoginBonusOverlay";
import RewardDialog, { rewardsToastMessage } from "@/components/RewardDialog";
import RewardsProgressBar from "@/components/RewardsProgressBar";
import { useToast } from "@/components/Toast";
import { api, ApiError } from "@/lib/api";
import {
  clearPendingLoginBonus,
  clearUser,
  getPendingLoginBonus,
  getStoredUser,
  storePendingLoginBonus,
  storeUser,
} from "@/lib/session";
import type {
  Idol,
  LoginBonusResult,
  RewardGranted,
  RewardsStatus,
  User,
} from "@/lib/types";
import { FALLBACK_IDOLS } from "@/lib/idols";
import { diffGrantedRewards } from "@/lib/rewards";

export default function HomePage() {
  const router = useRouter();
  const { show } = useToast();
  const [user, setUser] = useState<User | null>(null);
  const [idol, setIdol] = useState<Idol | null>(null);
  const [comment, setComment] = useState<string>("");
  const [logoutOpen, setLogoutOpen] = useState(false);
  const [ready, setReady] = useState(false);
  // 特殊ビジュアル切替の送信中フラグ（二度押し防止）
  const [visualSaving, setVisualSaving] = useState(false);

  // ---------- 毎日ログインボーナス（LB-10） ----------
  // 表示可否は **サーバーの login_bonus_available（当日ぶん未受領なら true）だけ** で決める。
  // localStorage の保存値は古い可能性があるため使わない。
  const [loginBonusOpen, setLoginBonusOpen] = useState(false);
  // このボーナス表示機会を識別するキー。オーバーレイが再マウントされても値は変わらないため、
  // claim の発火回数をマウントのライフサイクルから切り離せる（R-3 M-1）。
  const [loginBonusKey, setLoginBonusKey] = useState<string>("");
  // 1回のマウントで最大1度しか出さない（claim 後の再取得で再表示されないように）
  const loginBonusShownRef = useRef(false);
  // オーバーレイを開く直前の特典保有状況。claim のレスポンスを取り逃した場合に、
  // 再取得後の保有状況との差分から「新たに解放された特典」を復元する（QA_Q-6 M-1）。
  const rewardsSnapshotRef = useRef<RewardsStatus | null>(null);
  // ログインボーナスで閾値を跨いだときの達成演出（history と同じ RewardDialog を共用）
  const [grantedRewards, setGrantedRewards] = useState<RewardGranted[] | null>(
    null
  );

  /**
   * 達成演出（Toast → 600ms → RewardDialog）を出す。
   * 履歴画面（検収フロー）と同じ間合いにそろえる（DESIGN_D-3 §5.1）。
   */
  const announceRewards = useCallback(
    (granted: RewardGranted[]) => {
      if (granted.length === 0) return;
      window.setTimeout(() => {
        show(`✨ ${rewardsToastMessage(granted)}`, "success");
        window.setTimeout(() => setGrantedRewards(granted), 600);
      }, 300);
    },
    [show]
  );

  // ホーム表示のたびにユーザー最新化＋コメント取得
  const load = useCallback(async () => {
    const stored = getStoredUser();
    if (!stored) {
      router.replace("/");
      return;
    }
    setUser(stored);

    // アイドル情報（フォールバックから先に引いておく）
    const fb = FALLBACK_IDOLS.find((i) => i.id === stored.idol_id) ?? null;
    setIdol(fb);

    // ユーザー最新化。月替わりで限定推しから自動復帰していることがあるため、
    // 以降のアイドル解決は必ず「再取得後の idol_id」を基準にする（H-4）。
    let currentIdolId = stored.idol_id;
    try {
      const fresh = await api.getUser(stored.id);
      setUser(fresh);
      storeUser(fresh);
      currentIdolId = fresh.idol_id;
      // フォールバック表示も最新 idol_id に合わせて更新
      const fb2 = FALLBACK_IDOLS.find((i) => i.id === currentIdolId) ?? null;
      if (fb2) setIdol(fb2);

      // 【QA_Q-6 M-1】前回「結果を確認できなかった claim」の持ち越しがあれば、ここで回収する。
      // 送信が遅延して失敗表示のあとにサーバー側で付与が確定した場合、この経路でしか
      // 達成告知を拾えない（rewards_granted[] は GET /api/users/{id} には含まれないため）。
      const pending = getPendingLoginBonus();
      if (pending && pending.userId === fresh.id) {
        announceRewards(diffGrantedRewards(pending.rewards, fresh.rewards));
      }
      // 照合できない持ち越し（別アカウント等）も含めて、ここで必ず破棄する
      // （持ち越しは「次の1回のホーム表示まで」と決めている）。
      if (pending) clearPendingLoginBonus();

      // 当日ぶんが未受領ならログインボーナスのオーバーレイを出す（1マウント1回まで）。
      // 判定は必ず**再取得したサーバー値**で行う（保存済みユーザーは古い可能性がある）。
      if (fresh.login_bonus_available === true && !loginBonusShownRef.current) {
        loginBonusShownRef.current = true;
        // 達成演出を復元するための基準（QA_Q-6 M-1）
        rewardsSnapshotRef.current = fresh.rewards ?? null;
        // claim の発火回数を固定するためのキー（R-3 M-1）
        setLoginBonusKey(`${fresh.id}-${Date.now()}`);
        // 「これから claim する」ことを永続化しておく。結果を確認できたら破棄する。
        storePendingLoginBonus({
          userId: fresh.id,
          monthlyPoints: fresh.monthly_points ?? 0,
          rewards: fresh.rewards ?? null,
        });
        setLoginBonusOpen(true);
      }
    } catch {
      // 取得失敗時は保存済みを使う（トーストは控えめに）
    }

    // アイドル一覧（テーマカラー等の最新化）。再取得後の idol_id で解決する。
    try {
      const idols = await api.getIdols();
      const found = idols.find((i) => i.id === currentIdolId);
      if (found) {
        setIdol(found);
      } else {
        // 通常一覧に無い＝期間限定推しを選択中。獲得者なら限定推し情報で解決する。
        try {
          const limited = await api.getLimitedIdol();
          if (limited.id === currentIdolId) setIdol(limited);
        } catch {
          /* 非保有(404)等では通常フォールバックのまま */
        }
      }
    } catch {
      /* フォールバック済み */
    }

    // 推しコメント（毎回取得）
    try {
      const { comment } = await api.getComment(stored.id);
      setComment(comment);
    } catch {
      // 取得失敗時はデフォルトの一言
      setComment(`${stored.nickname}、今日も来てくれてうれしい♪`);
    }

    setReady(true);
  }, [router, announceRewards]);

  useEffect(() => {
    load();
  }, [load]);

  const logout = () => {
    clearUser();
    router.replace("/");
  };

  // 特殊ビジュアル（T2特典）の表示切替。獲得者のみ表示されるトグルから呼ぶ。
  const setVisual = async (visual: "main" | "special") => {
    if (!user || visualSaving || user.active_visual === visual) return;
    setVisualSaving(true);
    try {
      const updated = await api.updateMe({ active_visual: visual });
      setUser(updated);
      storeUser(updated);
      show(
        visual === "special"
          ? "とくべつなすがたに変えたよ"
          : "いつものすがたに戻したよ",
        "info"
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        show("ログイン情報が切れました。もう一度ログインしてね");
        router.replace("/");
        return;
      }
      show("ビジュアルの切替に失敗しました");
    } finally {
      setVisualSaving(false);
    }
  };

  /**
   * ユーザーを再取得し、必要なら特典の達成演出へ接続する（ログインボーナス共通の後処理）。
   *
   * `fromResponse`（claim レスポンスの `rewards_granted[]`）が取れていればそれを使う。
   * 取れなかった場合（タイムアウト後の再送で復元した・通信に失敗した）は、
   * **オーバーレイを開く前の保有状況との差分**から解放を復元する（QA_Q-6 M-1）。
   * これが無いと「サーバーは付与済みなのに達成演出が永久に出ない」状態が残る。
   *
   * @returns 再取得できたユーザー（失敗時は null）
   */
  const refreshAndAnnounce = useCallback(
    async (
      fromResponse: RewardGranted[],
      outcomeKnown: boolean
    ): Promise<User | null> => {
      let fresh: User | null = null;
      const stored = getStoredUser();
      if (stored) {
        try {
          fresh = await api.getUser(stored.id);
          setUser(fresh);
          storeUser(fresh);
        } catch {
          // 再取得に失敗しても付与自体は完了している。次回のホーム表示で整合する
        }
      }

      const granted =
        fromResponse.length > 0
          ? fromResponse
          : diffGrantedRewards(rewardsSnapshotRef.current, fresh?.rewards);
      // 同じ特典を二重に告知しないよう、基準を最新の保有状況へ進めておく
      if (fresh?.rewards) rewardsSnapshotRef.current = fresh.rewards;

      // 持ち越しの後始末:
      //  - 結果が確定している（outcomeKnown）→ 破棄する
      //  - 確定していない（失敗経路）→ **いま観測した値へ基準を更新して持ち越す**。
      //    送信が遅延してこの後にサーバー側で付与が確定しても、次のホーム表示で拾える。
      if (outcomeKnown || !fresh) {
        clearPendingLoginBonus();
      } else {
        storePendingLoginBonus({
          userId: fresh.id,
          monthlyPoints: fresh.monthly_points ?? 0,
          rewards: fresh.rewards ?? null,
        });
      }

      announceRewards(granted);
      return fresh;
    },
    [announceRewards]
  );

  // ログインボーナスの結果表示を閉じたとき（LB-10 ②③）。
  // claim 済みなら結果が渡る。Esc 等で claim 前に離脱した場合は null（翌アクセスで再表示）。
  const handleLoginBonusFinish = useCallback(
    async (result: LoginBonusResult | null) => {
      setLoginBonusOpen(false);
      if (!result) {
        // claim 前の離脱（Esc）。まだ何も投げていないので持ち越しは不要。
        clearPendingLoginBonus();
        return;
      }
      // 結果を確認できている＝告知は完了。持ち越しは破棄する。
      await refreshAndAnnounce(result.rewards_granted ?? [], true);
    },
    [refreshAndAnnounce]
  );

  // claim 失敗・タイムアウト時（LB-10 ④）。
  // ホーム画面は壊さず、トーストで知らせてオーバーレイだけ閉じる。
  //
  // 【QA_Q-6 M-1 対応】オーバーレイ側で「冪等な claim の再送」まで試みたうえでここへ来る。
  // それでも復元できなかった＝ほぼ通信不能だが、送信済みリクエストがサーバー側で通って
  // いる可能性は残る。そこで必ず再取得し、
  //   ①月間ptが増えていたら「受け取れなかった」と**断定しない**（誤情報を出さない）
  //   ②保有状況の差分から特典解放を検知したら達成演出へ接続する
  // ことで、「UI は失敗・サーバーは成功」で告知が消える状態を残さない。
  const handleLoginBonusFail = useCallback(async () => {
    setLoginBonusOpen(false);
    const before = user?.monthly_points ?? 0;
    // outcomeKnown=false: 結果が確定していないため、持ち越しを残して次のホーム表示でも拾う
    const fresh = await refreshAndAnnounce([], false);
    const actuallyGranted = fresh != null && (fresh.monthly_points ?? 0) > before;
    if (!actuallyGranted) {
      show("うまく受け取れなかったみたい…また来てね");
    }
  }, [refreshAndAnnounce, show, user]);

  const theme = idol?.theme_color ?? "#ff87b2";
  // 特殊ビジュアル（T2）獲得済みなら、限定推しを含めどの推しでも special 表示・切替可。
  // special.png が未配置の推し（将来の限定推し等）は IdolImage が main.png へフォールバックする。
  const activeVisual = user?.active_visual === "special" ? "special" : "main";
  const hasSpecialVisual = !!user?.rewards?.special_visual;

  if (!ready || !user) {
    return (
      <ScreenFrame>
        <div className="flex flex-1 items-center justify-center text-[var(--ink-soft)]">
          読み込み中…
        </div>
      </ScreenFrame>
    );
  }

  return (
    <ScreenFrame
      bgClassName="bg-gradient-to-b from-[#fff2f8] to-[#efe6ff]"
      noPadding
    >
      <Sparkles count={14} />

      {/* 上部バー: ランク＆ポイント */}
      <div className="relative flex items-start justify-between px-5 pt-5">
        <div className="rounded-2xl bg-white/70 px-3 py-1.5 text-sm font-extrabold text-[var(--pink-600)] shadow backdrop-blur">
          りなれす
        </div>
        <RankBadge rank={user.rank} points={user.points} />
      </div>

      {/* 特典プログレスバー（RankBadge 直下） */}
      <div className="relative px-5 pt-3">
        <RewardsProgressBar
          monthlyPoints={user.monthly_points ?? 0}
          nextReward={user.next_reward}
          rewards={user.rewards}
          nickname={user.nickname}
          themeColor={idol?.theme_color}
        />
      </div>

      {/* 吹き出し＋推しイラスト */}
      <div className="relative flex flex-col items-center px-5 pt-4">
        <div className="mb-4 w-full px-2">
          <SpeechBubble themeColor={theme}>{comment}</SpeechBubble>
        </div>
        {/* ラッパーにtransformを持たせるとmix-blend-modeが効かなくなるため、画像自体に付与する */}
        <IdolImage
          idolId={user.idol_id}
          name={idol?.name}
          size={230}
          height={330}
          visual={activeVisual}
          className="animate-floaty"
        />
        <p className="mt-1 text-sm font-bold text-[var(--ink)]">
          {idol?.name ?? "推し"}
        </p>

        {/* 特殊ビジュアル切替トグル（T2獲得者のみ表示） */}
        {hasSpecialVisual && (
          <div
            className="mt-2 inline-flex items-center rounded-full bg-white/70 p-1 shadow-sm"
            role="group"
            aria-label="ビジュアル切替"
          >
            {(
              [
                ["main", "いつもの"],
                ["special", "とくべつ"],
              ] as ["main" | "special", string][]
            ).map(([key, label]) => {
              const selected = activeVisual === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setVisual(key)}
                  disabled={visualSaving}
                  aria-pressed={selected}
                  className={`min-h-[32px] rounded-full px-3 py-1 text-[12px] font-bold transition-colors ${
                    selected
                      ? "bg-[var(--pink-400)] text-white shadow"
                      : "text-[var(--ink-soft)]"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* メニュー */}
      <div className="relative mt-auto px-5 pb-6 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <GameButton
            fullWidth
            themeColor={theme}
            onClick={() => router.push("/devices/new")}
          >
            📷 新規デバイス追加
          </GameButton>
          <GameButton
            fullWidth
            variant="accent"
            onClick={() => router.push("/ship")}
          >
            📦 りなれすに送る
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/history")}
          >
            📜 履歴
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/faq")}
          >
            💬 相談する
          </GameButton>
          <GameButton
            fullWidth
            variant="secondary"
            onClick={() => router.push("/oshi")}
          >
            💖 推しをかえる
          </GameButton>
        </div>
        <div className="mt-3">
          <GameButton
            fullWidth
            variant="ghost"
            onClick={() => setLogoutOpen(true)}
          >
            ログアウト
          </GameButton>
        </div>
      </div>

      {/* ログアウト確認 */}
      <GameDialog
        open={logoutOpen}
        title="ログアウト"
        confirmLabel="ログアウトする"
        cancelLabel="やめる"
        onConfirm={logout}
        onCancel={() => setLogoutOpen(false)}
      >
        またね！ ログアウトしても、
        <br />
        あなたのデータは残っているよ。
      </GameDialog>

      {/* 毎日ログインボーナス。login_bonus_available が true のときだけマウントする
          （false のときは一切マウントしない＝ホームの表示コストを増やさない）。
          ユーザー取得後にのみ描画されるため、ハイドレーション不整合は起きない。 */}
      {loginBonusOpen && (
        <LoginBonusOverlay
          user={user}
          claimKey={loginBonusKey}
          idolName={idol?.name}
          themeColor={theme}
          onFinish={handleLoginBonusFinish}
          onFail={handleLoginBonusFail}
        />
      )}

      {/* ログインボーナスで閾値を跨いだときの達成演出（history と共用・LB-7） */}
      <RewardDialog
        open={grantedRewards !== null}
        granted={grantedRewards ?? []}
        onClose={() => setGrantedRewards(null)}
      />
    </ScreenFrame>
  );
}
