"use client";

// 履歴（/history）GET /api/users/{id}/history
// タブ2つ: 「登録ログ」（デバイス一覧）と「送付履歴」（伝票ごと・受領状態を明示）
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import StatusBadge from "@/components/StatusBadge";
import { useToast } from "@/components/Toast";
import { api, mediaUrl } from "@/lib/api";
import { getStoredUser } from "@/lib/session";
import type { Device, Shipment } from "@/lib/types";

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
    </ScreenFrame>
  );
}
