"use client";

// デバイスをりなれすに送る（/ship）
// - GET /api/devices?status=registered で未送付一覧＋合計予定pt
// - 送る→確認ダイアログ→POST /api/shipments→PDFを新規タブ→完了ダイアログ→ホーム
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import GameButton from "@/components/GameButton";
import GameDialog from "@/components/GameDialog";
import { useToast } from "@/components/Toast";
import { api, mediaUrl } from "@/lib/api";
import { getStoredUser } from "@/lib/session";
import type { Device } from "@/lib/types";

export default function ShipPage() {
  const router = useRouter();
  const { show } = useToast();

  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [doneOpen, setDoneOpen] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!getStoredUser()) {
      router.replace("/");
      return;
    }
    let alive = true;
    (async () => {
      try {
        const list = await api.getDevices("registered");
        if (alive) setDevices(list);
      } catch {
        if (alive) show("デバイス一覧を取得できませんでした");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [router, show]);

  // 合計予定ポイント
  const totalPoints = useMemo(
    () => devices.reduce((sum, d) => sum + (d.points || 0), 0),
    [devices]
  );

  const doShip = async () => {
    setConfirmOpen(false);
    setSending(true);
    try {
      const shipment = await api.createShipment(devices.map((d) => d.id));
      // 伝票PDFは認証必須（F-3 対応）のため、Bearer 付きで取得して Blob を新規タブで開く。
      // 生 URL を直接 window.open すると Authorization を付けられず 404 になる。
      try {
        const blob = await api.fetchShipmentPdf(shipment.id);
        const objUrl = URL.createObjectURL(blob);
        window.open(objUrl, "_blank", "noopener,noreferrer");
        // メモリ解放（開いたタブが読み込む猶予を持たせてから revoke）
        setTimeout(() => URL.revokeObjectURL(objUrl), 60_000);
      } catch {
        // 送付自体は成立しているため、PDF が開けなくても完了扱いにし案内する
        show("伝票を発行しました。PDFは履歴から開けます");
      }
      setDoneOpen(true);
    } catch {
      show("送付の処理に失敗しました。時間をおいて試してね");
    } finally {
      setSending(false);
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
          りなれすに送る
        </h1>
      </header>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-[var(--ink-soft)]">
          読み込み中…
        </div>
      ) : devices.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <div className="text-5xl">📭</div>
          <p className="text-sm text-[var(--ink-soft)]">
            送れるデバイスがありません。
            <br />
            まずは新規デバイス追加から登録してね
          </p>
          <GameButton onClick={() => router.push("/devices/new")}>
            新規デバイス追加へ
          </GameButton>
        </div>
      ) : (
        <>
          {/* 合計 */}
          <div className="mb-3 flex items-center justify-between rounded-2xl bg-white/80 px-4 py-3 shadow-sm">
            <span className="text-sm font-bold text-[var(--ink)]">
              {devices.length}台 / 合計予定
            </span>
            <span className="text-lg font-extrabold text-[var(--pink-600)]">
              {totalPoints}pt
            </span>
          </div>

          {/* 一覧 */}
          <ul className="flex flex-1 flex-col gap-3 overflow-y-auto pb-2">
            {devices.map((d) => (
              <li
                key={d.id}
                className="flex items-center gap-3 rounded-2xl border-2 border-[var(--pink-100)] bg-white p-3 shadow-sm"
              >
                <div className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-[var(--pink-50)]">
                  {d.photo_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={mediaUrl(d.photo_url)}
                      alt={d.label}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-2xl">
                      📱
                    </div>
                  )}
                </div>
                <span className="flex-1 font-bold text-[var(--ink)]">
                  {d.label}
                </span>
                <span className="text-sm font-bold text-[var(--pink-600)]">
                  {d.points}pt
                </span>
              </li>
            ))}
          </ul>

          {/* 操作ボタン */}
          <div className="mt-3 flex gap-3">
            <GameButton
              variant="secondary"
              fullWidth
              onClick={() => router.push("/home")}
            >
              もどる
            </GameButton>
            <GameButton
              fullWidth
              disabled={sending}
              onClick={() => setConfirmOpen(true)}
            >
              {sending ? "処理中…" : "📦 送る"}
            </GameButton>
          </div>
        </>
      )}

      {/* 送付確認 */}
      <GameDialog
        open={confirmOpen}
        title="確認"
        confirmLabel="はい"
        cancelLabel="いいえ"
        onConfirm={doShip}
        onCancel={() => setConfirmOpen(false)}
      >
        pdfを出力します。よろしいですか？
      </GameDialog>

      {/* 完了 */}
      <GameDialog
        open={doneOpen}
        title="送付準備 完了！"
        hideCancel
        confirmLabel="ホームへもどる"
        onConfirm={() => router.push("/home")}
      >
        pdfを保存しました。伝票を印刷し、品物を送ってください。内容確認後、ポイントが付与されます
      </GameDialog>
    </ScreenFrame>
  );
}
