// デバイス／伝票の状態バッジ
interface StatusBadgeProps {
  status: string;
}

// 状態コード → 表示ラベル・色
const MAP: Record<string, { label: string; bg: string; fg: string }> = {
  registered: { label: "登録済み", bg: "#ffe0ec", fg: "#f43f84" },
  shipped: { label: "送付済み", bg: "#e2e0ff", fg: "#7c6cff" },
  received: { label: "受領済み✓", bg: "#d7f5e3", fg: "#28a468" },
  pending: { label: "りなれす確認中…", bg: "#fff3d6", fg: "#c78a00" },
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const s = MAP[status] ?? { label: status, bg: "#eee", fg: "#666" };
  return (
    <span
      className="inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-bold"
      style={{ background: s.bg, color: s.fg }}
    >
      {s.label}
    </span>
  );
}
