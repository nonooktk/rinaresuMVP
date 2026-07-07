"use client";

// ゲーム風グラデーションボタン（角丸大・影・押下アニメーション）
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "accent";

interface GameButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: Variant;
  fullWidth?: boolean;
  // 推しのテーマカラーで塗りたい場合に指定
  themeColor?: string;
}

const base =
  "relative inline-flex items-center justify-center gap-2 rounded-3xl px-6 py-3.5 text-base font-bold transition-transform duration-100 active:scale-[0.94] disabled:opacity-50 disabled:active:scale-100 select-none";

export default function GameButton({
  children,
  variant = "primary",
  fullWidth = false,
  themeColor,
  className = "",
  style,
  ...rest
}: GameButtonProps) {
  // テーマカラー指定があれば最優先で使う
  const themedStyle = themeColor
    ? {
        background: `linear-gradient(135deg, ${themeColor}, ${themeColor}cc)`,
        color: "#fff",
        boxShadow: `0 6px 0 0 ${themeColor}66, 0 10px 18px -6px ${themeColor}99`,
        ...style,
      }
    : style;

  const variantClass =
    !themeColor && variant === "primary"
      ? "text-white [background:linear-gradient(135deg,#ff87b2,#f43f84)] [box-shadow:0_6px_0_0_#f43f8455,0_10px_18px_-6px_#f43f8499]"
      : !themeColor && variant === "accent"
      ? "text-white [background:linear-gradient(135deg,#9a8dff,#7c6cff)] [box-shadow:0_6px_0_0_#7c6cff55,0_10px_18px_-6px_#7c6cff99]"
      : !themeColor && variant === "secondary"
      ? "text-[var(--pink-600)] bg-white [box-shadow:0_5px_0_0_#ffc2d9,0_8px_14px_-6px_#ffc2d9]"
      : !themeColor && variant === "ghost"
      ? "text-[var(--ink-soft)] bg-white/70 border border-[var(--pink-200)]"
      : "";

  return (
    <button
      className={`${base} ${variantClass} ${
        fullWidth ? "w-full" : ""
      } ${className}`}
      style={themedStyle}
      {...rest}
    >
      {children}
    </button>
  );
}
