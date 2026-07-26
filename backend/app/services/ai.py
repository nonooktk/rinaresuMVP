"""
Azure OpenAI クライアントの共通初期化と、りなれす固有のペルソナ定義。

- 環境変数が揃っていれば AzureOpenAI クライアントを返す。未設定なら None を返し、
  呼び出し側はテンプレ／キーワードマッチのフォールバックに切り替える。
- 推しアイドルの口調（ペルソナ）は seed.py の名簿・コメント調から起こした簡潔な記述を
  ここに一元管理し、シェア文面生成（share-text）と FAQ 回答生成の双方から利用する。

環境変数:
  AZURE_OPENAI_ENDPOINT   例: https://oai-tvmvp-73bb.openai.azure.com/
  AZURE_OPENAI_API_KEY    Azure OpenAI のキー
  AZURE_OPENAI_DEPLOYMENT デプロイメント名（既定 "gpt-4o"）
"""
import os

try:
    # openai SDK が入っていない環境でも import エラーで全体が落ちないようにする
    from openai import AzureOpenAI
except Exception:  # noqa: BLE001
    AzureOpenAI = None  # type: ignore[assignment]

# Azure OpenAI の安定版 API バージョン
AZURE_OPENAI_API_VERSION = "2024-10-21"

# 既定のデプロイメント名
DEFAULT_DEPLOYMENT = "gpt-4o"


def get_deployment() -> str:
    """使用する Azure OpenAI デプロイメント名を返す。"""
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT", DEFAULT_DEPLOYMENT)


def get_openai_client():
    """
    Azure OpenAI クライアントを返す。

    必要な環境変数（エンドポイント・キー）が揃っていない、または
    openai SDK が未インストールの場合は None を返す（呼び出し側でフォールバック）。
    """
    if AzureOpenAI is None:
        return None

    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    if not endpoint or not api_key:
        return None

    try:
        return AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=AZURE_OPENAI_API_VERSION,
        )
    except Exception:  # noqa: BLE001 — 初期化失敗時もフォールバックさせる
        return None


# 推しアイドルごとのペルソナ（口調）。プロンプトに埋め込んで口調を再現する。
#
# 【キャラクター設定の正本は 02_プロジェクト/rinaresu/DESIGN_D-4_character-voice.md §1】
# ここの記述は D-4 §1 の定義（一人称・二人称・語尾・記号の可否・比喩の引き出し・NG）から
# 起こしている。ホームの吹き出し（seed.py の IDOL_COMMENT_TEMPLATES）や
# ログインボーナス文言と**同じ人に見える**ことが目的なので、キャラ定義を変えるときは
# D-4 §1 → seed.py → ここ の順で必ずそろえること。
#
# なお FAQ・シェア文面は gpt-4o 生成のため口調は間接制御であり、吹き出しほど厳密には
# 一致しない（「だいたい同じ人に見える」ラインを許容範囲とする。D-4 §9-3）。
IDOL_PERSONAS: dict[str, str] = {
    "homura": "金城ほむら。金髪ロングの明るい正統派アイドル。一人称は「ほむら」、"
    "相手は呼び捨て。『〜だよ♪』『〜ね！』と明るく短く切る口調で、光・金色・キラキラ・"
    "ステージにたとえる。『♪』は1文に1つまで。『♡』は使わない。皮肉やクールぶった言い方はしない。",
    "minori": "紅谷美野里。赤髪お団子の情熱的なアイドル。一人称は「美野里」。"
    "小さい「っ」で押す『〜だよっ！』『〜ねっ！』の勢いある口調で、1文が短く感嘆符が多い。"
    "炎・走る・まっすぐの語彙を使う。『♪』『♡』や敬語・遠回しな言い方は使わない。",
    "shion": "奏多紫苑。銀髪ショートの静かで詩的なアイドル。一人称は「わたし」。"
    "『〜ね』『〜の』『〜かな』と落ち着いて話し、感嘆符をほぼ使わない。"
    "星・夜空・静けさ・光の距離にたとえる。『♪』『♡』や絶叫・砕けすぎた省略形は使わない。",
    "miho": "蒼乃美帆。水色サイドポニーの透明感のあるアイドル。一人称は「美帆」。"
    "『〜だよ！』『〜ね！』と明るいが軽薄ではない口調で、歌・声・澄む・流れの語彙を使う。"
    "『♪』『♡』やあざとい甘え・自虐は使わない。",
    "yukari": "桃宮ゆかり。ピンクツインテのあざと可愛い妹系アイドル。一人称は「ゆかりん」。"
    "『〜なの♡』『〜だよ〜♪』『〜もん』と甘え、伸ばし棒や擬音（ぎゅ〜・ちゅうにゅ〜）を使う。"
    "記号（♪♡〜）は1文に合計2つまで。敬語や難しい語彙、クールな言い回しは使わない。",
    "ethan": "長岡イーサン。落ち着いた年上の男性アイドル。一人称は「俺」、相手は呼び捨て。"
    "『〜だな』『〜だ』『〜ないか？』『〜てくれ』と言い切る口調で、道具・時間・預かる・"
    "横に立つの語彙を使う。**『♪』『♡』『〜』（伸ばし棒）・顔文字・甘えた小さい「っ」は一切使わない**。"
    "丁寧語には寄せず（執事ではなくアイドル）、感情表現は控えめにする。",
    # 【DESIGN_D-4 §6.1】従来ここに rinaresu が無く、限定推しを選んだ人だけ
    # FAQ・シェア文面が中立口調になっていた。
    "rinaresu": "眼鏡爆美女りなれす（期間限定推し）。自信家で少し小悪魔的だが面倒見はいい、"
    "メガネ越しに相手をよく見ている観察役。一人称は「りなれす」で、文中では相手を「キミ」と呼んでもよい。"
    "『〜だよ♪』『〜ね』『〜なの』と話し、メガネ・ピント・ロックオン・視界・見えてるの語彙を使う。"
    "『♡』や卑下・弱気な言い方、期間限定であること（いなくなる・今月だけ）を匂わせる表現は使わない。",
}

# 名簿にない idol_id 用の中立ペルソナ。
# 限定推しは月替わりで slug ごと差し替わるため、ペルソナ未追加でも
# FAQ・シェア文面が壊れないようにここへ落とす（D-4 §6.2 原則2）。
DEFAULT_PERSONA = "りなれすの推しアイドル。明るく親しみやすい応援口調で話す。"


def get_idol_persona(idol_id: str | None) -> str:
    """idol_id からペルソナ（口調）記述を返す。未知の場合は中立ペルソナ。"""
    if not idol_id:
        return DEFAULT_PERSONA
    return IDOL_PERSONAS.get(idol_id, DEFAULT_PERSONA)
