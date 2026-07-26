// アイドルのフォールバック定義。
// API（GET /api/idols）が使えない場合でも画面確認できるよう、既定の6人を用意する。
// id はバックエンドseedと共有する固定スラッグで、イラストパス /idols/{id}/main.png(svg) と対応する。
// 全6人とも支給イラスト（main.png・背景透過済み）配置済み。
import type { Idol } from "./types";

export const FALLBACK_IDOLS: Idol[] = [
  {
    id: "riji",
    name: "リジ・チョー",
    theme_color: "#E84393",
    catchphrase: "エコ、チョー映えるっす。",
  },
  {
    id: "taka",
    name: "タカ・チャーン",
    theme_color: "#F2B705",
    catchphrase: "これって、いい一歩だと思うんですけど。",
  },
  {
    id: "kurosuke",
    name: "くろすけん",
    theme_color: "#4E8D5B",
    catchphrase: "はい。着実に、回収します。",
  },
  {
    id: "miirin",
    name: "みーりん",
    theme_color: "#F2762E",
    catchphrase: "めっちゃ集まってるやん、おおきに！",
  },
  {
    id: "hiroji",
    name: "ひろじぃ・ネクスト",
    theme_color: "#7A5CB0",
    catchphrase: "えー、まぁ…その一台、未来の資源じゃよ。",
  },
  {
    id: "teraoman",
    name: "テラオーマン",
    theme_color: "#2D7DD2",
    catchphrase: "よいしょ！その一台、オレが受け取るぜ！",
  },
];
