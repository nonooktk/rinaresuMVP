// 吹き出し（推しのコメント表示用）。下向きのしっぽ付き。
import type { ReactNode } from "react";

interface SpeechBubbleProps {
  children: ReactNode;
  themeColor?: string;
  // しっぽの向き
  tail?: "down" | "up" | "none";
}

export default function SpeechBubble({
  children,
  themeColor = "var(--pink-400)",
  tail = "down",
}: SpeechBubbleProps) {
  return (
    <div className="relative inline-block max-w-full">
      <div
        className="relative rounded-3xl border-2 bg-white px-5 py-3 text-center text-[15px] font-medium leading-snug text-[var(--ink)] shadow-md"
        style={{ borderColor: themeColor }}
      >
        {children}
        {/* しっぽ */}
        {tail !== "none" && (
          <span
            className="absolute left-1/2 h-3 w-3 -translate-x-1/2 rotate-45 border-2 bg-white"
            style={{
              borderColor: themeColor,
              ...(tail === "down"
                ? {
                    bottom: -8,
                    borderTop: "none",
                    borderLeft: "none",
                  }
                : {
                    top: -8,
                    borderBottom: "none",
                    borderRight: "none",
                  }),
            }}
          />
        )}
      </div>
    </div>
  );
}
