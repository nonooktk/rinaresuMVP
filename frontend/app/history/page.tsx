"use client";

// 履歴（/history）GET /api/users/{id}/history
// タブ2つ: 「登録ログ」（デバイス一覧）と「送付履歴」（伝票ごと・受領状態を明示）
// 送付履歴では未受領伝票の「検収完了」、受領済み伝票の「投稿する」を提供する。
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import StatusBadge from "@/components/StatusBadge";
import GameDialog from "@/components/GameDialog";
import GameButton from "@/components/GameButton";
import { useToast } from "@/components/Toast";
import { api, mediaUrl } from "@/lib/api";
import { getStoredUser, storeUser } from "@/lib/session";
import type { Device, RewardGranted, Shipment } from "@/lib/types";

// 付与特典（複数可）を1つにまとめたトースト文面を作る（D-1 §3.1）。
function rewardsToastMessage(granted: RewardGranted[]): string {
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

type Tab = "devices" | "shipments";

// 日付を見やすく整形
function fmtDate(s?: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}

export default function HistoryPage() {
  const router = useRouter();
  const { show } = useToast();

  const [tab, setTab] = useState<Tab>("devices");
  const [devices, setDevices] = useState<Device[]>([]);
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [loading, setLoading] = useState(true);

  // 検収完了の確認ダイアログ対象の伝票
  const [confirmTarget, setConfirmTarget] = useState<Shipment | null>(null);
  // 検収処理中の伝票ID（ボタン二度押し防止）
  const [receivingId, setReceivingId] = useState<string | null>(null);

  // シェアダイアログ対象の伝票と、生成された文面
  const [shareTarget, setShareTarget] = useState<Shipment | null>(null);
  const [shareText, setShareText] = useState<string>("");
  const [shareLoading, setShareLoading] = useState(false);

  // 特典達成演出: 付与された特典一覧と、演出を閉じた後に開くシェア対象
  const [grantedRewards, setGrantedRewards] = useState<RewardGranted[] | null>(
    null
  );
  const [pendingShare, setPendingShare] = useState<Shipment | null>(null);

  useEffect(() => {
    const user = getStoredUser();
    if (!user) {
      router.replace("/");
      return;
    }
    let alive = true;
    (async () => {
      try {
        const hist = await api.getHistory(user.id);
        if (!alive) return;
        setDevices(hist.devices ?? []);
        setShipments(hist.shipments ?? []);
      } catch {
        if (alive) show("履歴を取得できませんでした");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [router, show]);

  // 伝票が受領済みかどうか
  const isReceived = (sp: Shipment) =>
    sp.status === "received" || !!sp.received_at;

  // 検収完了を確定する（確認ダイアログのOK）
  const confirmReceive = async () => {
    const sp = confirmTarget;
    setConfirmTarget(null);
    if (!sp) return;

    setReceivingId(sp.id);
    try {
      const result = await api.receiveShipment(sp.id);

      // 送付履歴の該当伝票を受領済み表示に更新
      setShipments((prev) =>
        prev.map((s) =>
          s.id === sp.id
            ? { ...s, status: "received", received_at: new Date().toISOString() }
            : s
        )
      );
      // 登録ログ側のデバイスも受領済みへ（同じ伝票配下のもの）
      setDevices((prev) =>
        prev.map((d) =>
          sp.devices?.some((sd) => sd.id === d.id)
            ? { ...d, status: "received" }
            : d
        )
      );

      // セッションのユーザーを最新化（ポイント・ランクを反映）
      const stored = getStoredUser();
      if (stored) {
        try {
          const latest = await api.getUser(stored.id);
          storeUser(latest);
          // ランクが上がった場合はお祝いトースト
          if (latest.rank > stored.rank) {
            show(
              `ランクアップ！ランク${latest.rank}になったよ🎉 (+${result.points_added}pt)`,
              "success"
            );
          } else {
            show(`${result.points_added}ptゲット！ありがとう✨`, "success");
          }
        } catch {
          // ユーザー再取得に失敗してもポイント付与自体は完了しているので通知だけ
          show(`${result.points_added}ptゲット！ありがとう✨`, "success");
        }
      }

      // 続けて投稿する導線用の受領済み伝票
      const receivedSp: Shipment = {
        ...sp,
        status: "received",
        received_at: new Date().toISOString(),
      };

      // 特典が付与されていたら達成演出（トースト→少し間をおいてダイアログ）を挟み、
      // ダイアログを閉じたあとにシェアダイアログを開く（D-1 §3.3）。
      const granted = result.rewards_granted ?? [];
      if (granted.length > 0) {
        show(`✨ ${rewardsToastMessage(granted)}`, "success");
        setPendingShare(receivedSp);
        setTimeout(() => setGrantedRewards(granted), 600);
      } else {
        // 特典なしなら従来どおりそのままシェアダイアログへ
        openShareDialog(receivedSp);
      }
    } catch (e) {
      const msg =
        e instanceof Error ? e.message : "検収の反映に失敗しました";
      show(msg);
    } finally {
      setReceivingId(null);
    }
  };

  // 達成演出ダイアログを閉じ、続けてシェアダイアログを開く
  const closeRewardDialog = () => {
    setGrantedRewards(null);
    if (pendingShare) {
      const sp = pendingShare;
      setPendingShare(null);
      openShareDialog(sp);
    }
  };

  // シェアダイアログを開いて文面を取得する
  const openShareDialog = async (sp: Shipment) => {
    setShareTarget(sp);
    setShareText("");
    setShareLoading(true);
    try {
      const res = await api.getShareText(sp.id);
      setShareText(res.text);
    } catch {
      show("投稿文の生成に失敗しました");
      setShareText("");
    } finally {
      setShareLoading(false);
    }
  };

  // 文面を作り直す（再取得）
  const regenerateShareText = async () => {
    if (!shareTarget) return;
    setShareLoading(true);
    try {
      const res = await api.getShareText(shareTarget.id);
      setShareText(res.text);
    } catch {
      show("投稿文の生成に失敗しました");
    } finally {
      setShareLoading(false);
    }
  };

  // Xの投稿画面を新規タブで開く
  const postToX = () => {
    if (!shareText) return;
    const url = `https://x.com/intent/post?text=${encodeURIComponent(
      shareText
    )}`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  // 文面をクリップボードにコピー
  const copyShareText = async () => {
    if (!shareText) return;
    try {
      await navigator.clipboard.writeText(shareText);
      show("文面をコピーしたよ✨", "success");
    } catch {
      show("コピーできませんでした");
    }
  };

  return (
    <ScreenFrame>
      <header className="relative mb-4 flex items-center">
        <button
          onClick={() => router.push("/home")}
          className="relative z-10 text-sm font-bold text-[var(--ink-soft)]"
        >
          ← ホーム
        </button>
        <h1 className="absolute left-1/2 -translate-x-1/2 text-lg font-extrabold text-[var(--pink-600)]">
          履歴
        </h1>
      </header>

      {/* タブ */}
      <div className="mb-4 flex rounded-full bg-[var(--pink-100)] p-1">
        {(
          [
            ["devices", "登録ログ"],
            ["shipments", "送付履歴"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-full py-2 text-sm font-bold transition-colors ${
              tab === key
                ? "bg-white text-[var(--pink-600)] shadow"
                : "text-[var(--pink-400)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-[var(--ink-soft)]">
          読み込み中…
        </div>
      ) : (
        <div className="flex flex-1 flex-col overflow-y-auto pb-2">
          {/* ===== 登録ログ ===== */}
          {tab === "devices" &&
            (devices.length === 0 ? (
              <p className="mt-10 text-center text-sm text-[var(--ink-soft)]">
                まだ登録したデバイスがありません
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {devices.map((d) => (
                  <li
                    key={d.id}
                    className="flex items-center gap-3 rounded-2xl border-2 border-[var(--pink-100)] bg-white p-3 shadow-sm"
                  >
                    <div className="h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-[var(--pink-50)]">
                      {d.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={mediaUrl(d.photo_url)}
                          alt={d.label}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center text-xl">
                          📱
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-bold text-[var(--ink)]">
                        {d.label}
                      </p>
                      <p className="text-xs text-[var(--ink-soft)]">
                        {fmtDate(d.created_at)}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <StatusBadge status={d.status} />
                      <span className="text-sm font-bold text-[var(--pink-600)]">
                        {d.points}pt
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ))}

          {/* ===== 送付履歴 ===== */}
          {tab === "shipments" &&
            (shipments.length === 0 ? (
              <p className="mt-10 text-center text-sm text-[var(--ink-soft)]">
                まだ送付履歴がありません
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {shipments.map((sp) => {
                  const received = isReceived(sp);
                  return (
                    <li
                      key={sp.id}
                      className="rounded-2xl border-2 border-[var(--pink-100)] bg-white p-4 shadow-sm"
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <span className="text-sm font-bold text-[var(--ink)]">
                          {fmtDate(sp.created_at)} 発行
                        </span>
                        {/* りなれすが受領したか否かを明示 */}
                        <span
                          className="rounded-full px-2.5 py-1 text-[11px] font-bold"
                          style={
                            received
                              ? { background: "#d7f5e3", color: "#28a468" }
                              : { background: "#fff3d6", color: "#c78a00" }
                          }
                        >
                          {received
                            ? "受領済み✓ ポイント付与"
                            : "りなれす確認中…"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-sm text-[var(--ink-soft)]">
                        <span>{sp.device_count}台</span>
                        <span className="font-bold text-[var(--pink-600)]">
                          合計 {sp.total_points}pt
                        </span>
                      </div>

                      {/* 未受領: 検収完了ボタン / 受領済み: 投稿するボタン */}
                      <div className="mt-3">
                        {received ? (
                          <GameButton
                            variant="secondary"
                            fullWidth
                            onClick={() => openShareDialog(sp)}
                          >
                            🕊️ 投稿する
                          </GameButton>
                        ) : (
                          <GameButton
                            fullWidth
                            disabled={receivingId === sp.id}
                            onClick={() => setConfirmTarget(sp)}
                          >
                            {receivingId === sp.id
                              ? "反映中…"
                              : "📦 検収完了"}
                          </GameButton>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ))}
        </div>
      )}

      <div className="mt-3">
        <button
          onClick={() => router.push("/home")}
          className="w-full rounded-3xl bg-white/70 py-3 text-sm font-bold text-[var(--ink-soft)] shadow-sm"
        >
          ホームへもどる
        </button>
      </div>

      {/* 検収完了 確認ダイアログ */}
      <GameDialog
        open={confirmTarget !== null}
        title="検収完了にする？"
        confirmLabel="届いたよ！"
        cancelLabel="まだ"
        onConfirm={confirmReceive}
        onCancel={() => setConfirmTarget(null)}
      >
        りなれすに端末が届いたことを確認したら押してね。
        <br />
        ポイントが反映されるよ✨
      </GameDialog>

      {/* 特典達成演出ダイアログ（rewards_granted があるとき） */}
      <GameDialog
        open={grantedRewards !== null && grantedRewards.length > 0}
        title="とくてん げっとだよ！"
        hideCancel
        confirmLabel="うれしい！"
        onConfirm={closeRewardDialog}
        onCancel={closeRewardDialog}
      >
        <div className="flex flex-col gap-3 text-left">
          {(grantedRewards ?? []).map((g, i) => {
            const line = rewardDialogLine(g);
            return (
              <div key={`${g.tier}-${g.threshold}-${i}`}>
                <p className="font-bold text-[var(--ink)]">
                  {line.icon} {g.label} をゲット！
                </p>
                <p className="text-[12px] text-[var(--ink-soft)]">
                  {line.note}
                </p>
              </div>
            );
          })}
        </div>
      </GameDialog>

      {/* シェア投稿ダイアログ */}
      <GameDialog
        open={shareTarget !== null}
        title="投稿する"
        hideCancel
        confirmLabel="とじる"
        onConfirm={() => setShareTarget(null)}
        onCancel={() => setShareTarget(null)}
      >
        <div className="flex flex-col gap-3 text-left">
          {/* 文面プレビュー */}
          <div className="rounded-2xl border-2 border-[var(--pink-100)] bg-[var(--pink-50)] p-3 text-sm leading-relaxed text-[var(--ink)]">
            {shareLoading ? (
              <span className="text-[var(--ink-soft)]">文面を作成中…</span>
            ) : shareText ? (
              shareText
            ) : (
              <span className="text-[var(--ink-soft)]">
                文面を取得できませんでした
              </span>
            )}
          </div>

          {/* アクション */}
          <div className="flex flex-col gap-2">
            <GameButton
              variant="ghost"
              fullWidth
              disabled={shareLoading}
              onClick={regenerateShareText}
            >
              🔁 文面を作り直す
            </GameButton>
            <div className="flex gap-2">
              <GameButton
                fullWidth
                disabled={shareLoading || !shareText}
                onClick={postToX}
              >
                Xに投稿
              </GameButton>
              <GameButton
                variant="secondary"
                fullWidth
                disabled={shareLoading || !shareText}
                onClick={copyShareText}
              >
                📋 コピー
              </GameButton>
            </div>
          </div>
        </div>
      </GameDialog>
    </ScreenFrame>
  );
}
