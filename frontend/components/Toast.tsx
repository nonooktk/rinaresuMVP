"use client";

// ゲーム風トースト。API失敗時などに画面上部へ表示して、UIが壊れないようにする。
import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";

type ToastKind = "error" | "success" | "info";

interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

interface ToastContextValue {
  show: (message: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// トースト表示用フック
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Provider外で呼ばれた場合でも落ちないようにフォールバック
    return { show: () => {} };
  }
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const show = useCallback((message: string, kind: ToastKind = "error") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev, { id, message, kind }]);
    // 3.5秒で自動消去
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3500);
  }, []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {/* トースト表示エリア（スマホ枠に合わせて中央上部） */}
      <div className="pointer-events-none fixed left-1/2 top-4 z-[100] w-full max-w-[400px] -translate-x-1/2 px-4">
        <div className="flex flex-col items-center gap-2">
          {toasts.map((t) => (
            <div
              key={t.id}
              className="animate-toast-in w-full rounded-2xl px-4 py-3 text-center text-sm font-bold text-white shadow-lg"
              style={{
                background:
                  t.kind === "error"
                    ? "linear-gradient(135deg,#ff7a9c,#f43f84)"
                    : t.kind === "success"
                    ? "linear-gradient(135deg,#7ed0a0,#41b880)"
                    : "linear-gradient(135deg,#8aa8ff,#7c6cff)",
              }}
            >
              {t.kind === "error" && "⚠ "}
              {t.kind === "success" && "✨ "}
              {t.message}
            </div>
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}
