// 縦型スマホ枠。全画面を max-width 430px で中央配置し、100dvh レイアウトにする。
import type { ReactNode } from "react";

interface ScreenFrameProps {
  children: ReactNode;
  // 画面内背景（グラデーション等）を上書きしたい場合
  bgClassName?: string;
  // paddingを消したい画面用
  noPadding?: boolean;
}

export default function ScreenFrame({
  children,
  bgClassName,
  noPadding = false,
}: ScreenFrameProps) {
  return (
    <div className="flex min-h-[100dvh] w-full justify-center">
      <div
        className={`relative flex min-h-[100dvh] w-full max-w-[430px] flex-col overflow-hidden shadow-2xl ${
          bgClassName ?? "bg-[var(--frame-bg)]"
        }`}
      >
        <div
          className={`relative flex flex-1 flex-col ${
            noPadding ? "" : "px-5 py-6"
          }`}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
