// アイドルのプレースホルダーSVGを生成するスクリプト。
// public/idols/{id}/main.svg に6人分を出力。
// 各アイドルのテーマカラーで、ちびキャラ風シルエット＋名前入り。
// 髪型・リボン・前髪・目の形で差別化する。
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outRoot = join(__dirname, "..", "public", "idols");

// 色を少し暗く/明るくする簡易関数
function shade(hex, amt) {
  const n = parseInt(hex.slice(1), 16);
  let r = (n >> 16) + amt;
  let g = ((n >> 8) & 0xff) + amt;
  let b = (n & 0xff) + amt;
  r = Math.max(0, Math.min(255, r));
  g = Math.max(0, Math.min(255, g));
  b = Math.max(0, Math.min(255, b));
  return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}

// 6人の定義（lib/idols.ts と一致）。hair でシルエットを差別化。
const IDOLS = [
  { id: "sakura", name: "咲良 モモ", color: "#ff87b2", hair: "twin", eye: "round" },
  { id: "mint", name: "美都 ミント", color: "#3ec7a8", hair: "bob", eye: "wink" },
  { id: "sora", name: "天原 ソラ", color: "#5b9dff", hair: "pony", eye: "round" },
  { id: "kanade", name: "奏 カナデ", color: "#a97bff", hair: "wavy", eye: "star" },
  { id: "hinata", name: "陽向 ヒナタ", color: "#ffb43e", hair: "short", eye: "round" },
  { id: "yuki", name: "白雪 ユキ", color: "#7fd4e6", hair: "long", eye: "calm" },
];

// 髪型パーツ（頭 cx=100, cy=112, 顔半径 ~46）
function hairBack(hair, dark) {
  switch (hair) {
    case "twin": // ツインテール
      return `
        <ellipse cx="52" cy="150" rx="20" ry="34" fill="${dark}"/>
        <ellipse cx="148" cy="150" rx="20" ry="34" fill="${dark}"/>`;
    case "pony": // サイドポニー
      return `<ellipse cx="150" cy="160" rx="18" ry="40" fill="${dark}" transform="rotate(12 150 160)"/>`;
    case "wavy": // 巻き髪ロング
      return `
        <path d="M54 120 q-16 40 4 70 q10 12 22 4 q-14 -30 -6 -66 Z" fill="${dark}"/>
        <path d="M146 120 q16 40 -4 70 q-10 12 -22 4 q14 -30 6 -66 Z" fill="${dark}"/>`;
    case "long": // ストレートロング
      return `
        <path d="M56 112 q-8 60 6 92 l20 0 q-6 -50 0 -92 Z" fill="${dark}"/>
        <path d="M144 112 q8 60 -6 92 l-20 0 q6 -50 0 -92 Z" fill="${dark}"/>`;
    default:
      return "";
  }
}

function hairFront(hair, base, dark) {
  // 前髪（顔の上部にかぶせる）
  const bang =
    hair === "short"
      ? `<path d="M60 100 q40 -46 80 0 q-8 -14 -40 -14 q-32 0 -40 14 Z" fill="${base}"/>`
      : hair === "bob"
      ? `<path d="M56 106 q44 -52 88 0 q0 -30 -44 -30 q-44 0 -44 30 Z" fill="${base}"/>`
      : `<path d="M58 104 q42 -50 84 0 q2 -34 -42 -34 q-44 0 -42 34 Z" fill="${base}"/>`;
  // 前髪の分け目ハイライト
  return `${bang}<path d="M100 74 q-14 12 -18 28" stroke="${dark}" stroke-width="2" fill="none" opacity="0.5"/>`;
}

function eyes(eye) {
  if (eye === "wink") {
    return `
      <path d="M78 112 q6 -8 14 0" stroke="#5a3a4a" stroke-width="3.5" fill="none" stroke-linecap="round"/>
      <circle cx="120" cy="112" r="6.5" fill="#5a3a4a"/>
      <circle cx="122" cy="110" r="2" fill="#fff"/>`;
  }
  if (eye === "star") {
    return `
      <text x="85" y="118" font-size="15" text-anchor="middle" fill="#5a3a4a">★</text>
      <text x="115" y="118" font-size="15" text-anchor="middle" fill="#5a3a4a">★</text>`;
  }
  if (eye === "calm") {
    return `
      <path d="M78 113 q7 6 14 0" stroke="#5a3a4a" stroke-width="3.2" fill="none" stroke-linecap="round"/>
      <path d="M108 113 q7 6 14 0" stroke="#5a3a4a" stroke-width="3.2" fill="none" stroke-linecap="round"/>`;
  }
  // round（きらきら大きめ）
  return `
    <circle cx="85" cy="112" r="7" fill="#5a3a4a"/>
    <circle cx="87" cy="109" r="2.4" fill="#fff"/>
    <circle cx="115" cy="112" r="7" fill="#5a3a4a"/>
    <circle cx="117" cy="109" r="2.4" fill="#fff"/>`;
}

function svgFor(idol) {
  const base = idol.color;
  const dark = shade(base, -45);
  const light = shade(base, 60);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 240" width="200" height="240" role="img" aria-label="${idol.name}">
  <defs>
    <radialGradient id="bg" cx="50%" cy="38%" r="75%">
      <stop offset="0%" stop-color="${light}"/>
      <stop offset="100%" stop-color="${base}"/>
    </radialGradient>
  </defs>
  <!-- 背景の丸 -->
  <circle cx="100" cy="110" r="96" fill="url(#bg)" opacity="0.35"/>
  <!-- キラキラ -->
  <text x="34" y="52" font-size="16" fill="#fff" opacity="0.85">✦</text>
  <text x="164" y="70" font-size="12" fill="#fff" opacity="0.8">✧</text>
  <text x="150" y="188" font-size="14" fill="#fff" opacity="0.8">✦</text>
  <!-- 後ろ髪 -->
  ${hairBack(idol.hair, dark)}
  <!-- からだ（服） -->
  <path d="M64 196 q36 -34 72 0 l0 24 l-72 0 Z" fill="${base}"/>
  <path d="M64 196 q36 -34 72 0 l0 10 q-36 -20 -72 0 Z" fill="${light}"/>
  <!-- 首 -->
  <rect x="92" y="150" width="16" height="18" rx="6" fill="#ffe0d0"/>
  <!-- 顔 -->
  <circle cx="100" cy="112" r="46" fill="#ffe8dc"/>
  <!-- ほっぺ -->
  <circle cx="74" cy="126" r="7" fill="${base}" opacity="0.5"/>
  <circle cx="126" cy="126" r="7" fill="${base}" opacity="0.5"/>
  <!-- 目 -->
  ${eyes(idol.eye)}
  <!-- 口 -->
  <path d="M94 132 q6 6 12 0" stroke="#d46a86" stroke-width="2.6" fill="none" stroke-linecap="round"/>
  <!-- 前髪 -->
  ${hairFront(idol.hair, base, dark)}
  <!-- リボン -->
  <g transform="translate(100 70)">
    <path d="M0 0 l-18 -10 l0 20 Z" fill="${dark}"/>
    <path d="M0 0 l18 -10 l0 20 Z" fill="${dark}"/>
    <circle cx="0" cy="0" r="6" fill="${light}"/>
  </g>
  <!-- 名前プレート -->
  <g transform="translate(100 224)">
    <rect x="-70" y="-15" width="140" height="26" rx="13" fill="#fff" opacity="0.95"/>
    <text x="0" y="4" font-size="15" font-weight="700" text-anchor="middle"
      fill="${dark}" font-family="'M PLUS Rounded 1c','Hiragino Maru Gothic ProN',sans-serif">${idol.name}</text>
  </g>
</svg>`;
}

for (const idol of IDOLS) {
  const dir = join(outRoot, idol.id);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "main.svg"), svgFor(idol), "utf8");
  console.log("generated", idol.id);
}
console.log("done");
