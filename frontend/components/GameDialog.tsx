"use client";

// ゲーム風ダイアログ（角丸カード・リボン風ヘッダー・オーバーレイ）
import type { ReactNode } from "react";
import GameButton from "./GameButton";
import Sparkles from "./Sparkles";

interface GameDialogProps {
  open: boolean;
  title?: string;
  children?: ReactNode;
  // ボタン群（省略時は confirm/cancel を自動表示）
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  onCancel?: () => void;
  // confirmのみ（cancelを出さない）
  hideCancel?: boolean;
  themeColor?: string;
}

export default function GameDialog({
  open,
  title,
  children,
  confirmLabel = "OK",
  cancelLabel = "やめる",
  onConfirm,
  onCancel,
  hideCancel = false,
  themeColor,
}: GameDialogProps) {
  if (!open) return null;

  const ribbon = themeColor ?? "var(--pink-400)";

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-6"
      // オーバーレイ
      style={{ background: "rgba(90,58,74,0.45)" }}
      onClick={onCancel}
    >
      <div
        className="animate-dialog-in relative w-full max-w-[360px] overflow-hidden rounded-3xl bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <Sparkles count={8} />
        {/* リボン風ヘッダー */}
        {title && (
          <div
            className="relative px-6 py-4 text-center text-lg font-extrabold text-white"
            style={{
              background: `linear-gradient(135deg, ${ribbon}, ${ribbon}cc)`,
            }}
          >
            {title}
          </div>
        )}
        {/* 本文 */}
        <div className="relative px-6 py-5 text-center text-[15px] leading-relaxed text-[var(--ink)]">
          {children}
        </div>
        {/* ボタン */}
        <div className="relative flex gap-3 px-6 pb-6">
          {!hideCancel && (
            <GameButton
              variant="secondary"
              fullWidth
              onClick={onCancel}
              type="button"
            >
              {cancelLabel}
            </GameButton>
          )}
          <GameButton
            fullWidth
            onClick={onConfirm}
            themeColor={themeColor}
            type="button"
          >
            {confirmLabel}
          </GameButton>
        </div>
      </div>
    </div>
  );
}
