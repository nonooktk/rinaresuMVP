// アイドルのフォールバック定義。
// API（GET /api/idols）が使えない場合でも画面確認できるよう、既定の6人を用意する。
// id はバックエンドseedと共有する固定スラッグで、イラストパス /idols/{id}/main.png(svg) と対応する。
// 全6人とも支給イラスト（main.png・背景透過済み）配置済み。
import type { Idol } from "./types";

export const FALLBACK_IDOLS: Idol[] = [
  {
    id: "homura",
    name: "金城ほむら",
    theme_color: "#f2b705",
    catchphrase: "キラキラは金色！ほむらにおまかせ♪",
  },
  {
    id: "minori",
    name: "紅谷美野里",
    theme_color: "#e0524d",
    catchphrase: "ハートに一直線、美野里だよっ！",
  },
  {
    id: "shion",
    name: "奏多紫苑",
    theme_color: "#9d8ee0",
    catchphrase: "星降るステージ、一緒に見よ？",
  },
  {
    id: "miho",
    name: "蒼乃美帆",
    theme_color: "#4fc3dd",
    catchphrase: "透きとおる歌声、届けるよ！",
  },
  {
    id: "yukari",
    name: "桃宮ゆかり",
    theme_color: "#f06fae",
    catchphrase: "ゆかりんパワー、ちゅうにゅ〜♪",
  },
  {
    id: "ethan",
    name: "長岡イーサン",
    theme_color: "#b3273e",
    catchphrase: "その端末、俺に預けてみないか？",
  },
];
