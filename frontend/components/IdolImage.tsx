"use client";

// アイドル画像表示。パス規約は /idols/{idol_id}/main.png（支給イラスト）を最優先し、
// 無ければ /idols/{idol_id}/main.svg（プレースホルダー）、それも無ければ頭文字表示。
// イラスト差し替えはファイル配置だけで反映されるよう、必ずこのコンポーネント経由で参照する。
import { useState } from "react";

interface IdolImageProps {
  idolId: string;
  name?: string;
  /** 表示幅(px)。variant="face" では正円の直径 */
  size?: number;
  /** variant="full" 時の高さ(px)。省略時は size と同じ */
  height?: number;
  /** full: 全身表示（既定） / face: 顔まわりを正円でクロップ（アバター用） */
  variant?: "full" | "face";
  className?: string;
}

export default function IdolImage({
  idolId,
  name,
  size = 96,
  height,
  variant = "full",
  className = "",
}: IdolImageProps) {
  // 0: main.png → 1: main.svg → 2: 頭文字プレースホルダー
  const [stage, setStage] = useState<0 | 1 | 2>(0);
  const src =
    stage === 0 ? `/idols/${idolId}/main.png` : `/idols/${idolId}/main.svg`;
  const alt = name ? `${name}のイラスト` : "アイドル";
  const onError = () => setStage((s) => (s >= 1 ? 2 : 1));
  const isPng = stage === 0;

  if (stage === 2) {
    // フォールバック（丸い枠に頭文字）
    return (
      <div
        className={`flex items-center justify-center rounded-full bg-[var(--pink-100)] text-[var(--pink-500)] ${className}`}
        style={{ width: size, height: size }}
      >
        <span className="text-2xl font-extrabold">
          {name?.slice(0, 1) ?? "?"}
        </span>
      </div>
    );
  }

  if (variant === "face") {
    // 全身立ち絵から顔まわりを正円でクロップ（PNGのみ拡大。SVGちびキャラはそのまま）
    return (
      <div
        className={`shrink-0 overflow-hidden rounded-full bg-white ${className}`}
        style={{ width: size, height: size }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={src}
          alt={alt}
          width={size}
          height={size}
          onError={onError}
          style={
            isPng
              ? {
                  // 全身立ち絵(縦2:3・顔は上部中央)から顔部分へズーム
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  objectPosition: "50% 4%",
                  transform: "scale(3.4)",
                  transformOrigin: "50% 16%",
                }
              : { width: "100%", height: "100%", objectFit: "contain" }
          }
        />
      </div>
    );
  }

  const h = height ?? size;
  return (
    // 通常の <img>。支給イラストは背景透過済みPNG（scripts参照）を前提とする。
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      width={size}
      height={h}
      className={className}
      onError={onError}
      style={{ width: size, height: h, objectFit: "contain" }}
    />
  );
}
