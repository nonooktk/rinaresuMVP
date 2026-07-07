"use client";

// キラキラ装飾（星・スパークルを散りばめる）。装飾用途なので描画のみ。
// SSRとのハイドレーションミスマッチを避けるため、マウント後にのみ描画する。
import { useEffect, useState } from "react";

interface SparklesProps {
  count?: number;
  className?: string;
}

interface Star {
  left: string;
  top: string;
  size: number;
  delay: string;
  char: string;
  gold: boolean;
}

export default function Sparkles({ count = 14, className = "" }: SparklesProps) {
  const [stars, setStars] = useState<Star[]>([]);

  useEffect(() => {
    // クライアントでのみ生成（精度差によるハイドレーション警告を回避）
    setStars(
      Array.from({ length: count }, (_, i) => ({
        left: `${(Math.random() * 100).toFixed(1)}%`,
        top: `${(Math.random() * 100).toFixed(1)}%`,
        size: Math.round(6 + Math.random() * 14),
        delay: `${(Math.random() * 2).toFixed(2)}s`,
        char: Math.random() > 0.5 ? "✦" : "✧",
        gold: i % 3 === 0,
      })),
    );
  }, [count]);

  return (
    <div
      className={`pointer-events-none absolute inset-0 overflow-hidden ${className}`}
      aria-hidden
    >
      {stars.map((s, i) => (
        <span
          key={i}
          className="animate-twinkle absolute select-none"
          style={{
            left: s.left,
            top: s.top,
            fontSize: s.size,
            animationDelay: s.delay,
            color: s.gold ? "#ffd24c" : "#ffffff",
            textShadow: "0 0 6px rgba(255,255,255,0.8)",
          }}
        >
          {s.char}
        </span>
      ))}
    </div>
  );
}
