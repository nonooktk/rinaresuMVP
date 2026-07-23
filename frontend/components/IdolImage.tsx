"use client";

// アイドル画像表示。パス規約は /idols/{idol_id}/main.png（支給イラスト）を最優先し、
// 無ければ /idols/{idol_id}/main.svg（プレースホルダー）、それも無ければ頭文字表示。
// イラスト差し替えはファイル配置だけで反映されるよう、必ずこのコンポーネント経由で参照する。
//
// 特殊ビジュアル（T2特典）: visual="special" のとき /idols/{id}/special.png を最優先し、
// 無ければ main.png → main.svg → 頭文字 の順にフォールバックする。
// 運営は special.png を同パスに置くだけで差し替えできる。
import { useEffect, useState } from "react";

interface IdolImageProps {
  idolId: string;
  name?: string;
  /** 表示幅(px)。variant="face" では正円の直径 */
  size?: number;
  /** variant="full" 時の高さ(px)。省略時は size と同じ */
  height?: number;
  /** full: 全身表示（既定） / face: 顔まわりを正円でクロップ（アバター用） */
  variant?: "full" | "face";
  /** main: 通常イラスト（既定） / special: 特殊ビジュアル（special.png 優先） */
  visual?: "main" | "special";
  className?: string;
}

export default function IdolImage({
  idolId,
  name,
  size = 96,
  height,
  variant = "full",
  visual = "main",
  className = "",
}: IdolImageProps) {
  // visual="special": 0: special.png → 1: main.png → 2: main.svg → 3: 頭文字
  // visual="main":               1: main.png → 2: main.svg → 3: 頭文字（0 は使わない）
  const initialStage = visual === "special" ? 0 : 1;
  const [stage, setStage] = useState<0 | 1 | 2 | 3>(initialStage);

  // idolId / visual が変わったら読み込みステージをリセットする（推し変更・切替に追従）
  useEffect(() => {
    setStage(visual === "special" ? 0 : 1);
  }, [idolId, visual]);

  const src =
    stage === 0
      ? `/idols/${idolId}/special.png`
      : stage === 1
      ? `/idols/${idolId}/main.png`
      : `/idols/${idolId}/main.svg`;
  const alt = name ? `${name}のイラスト` : "アイドル";
  const onError = () => setStage((s) => (s >= 2 ? 3 : ((s + 1) as 1 | 2 | 3)));
  // png（special.png / main.png）は透過前提のクロップ調整を効かせる
  const isPng = stage === 0 || stage === 1;

  if (stage === 3) {
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
