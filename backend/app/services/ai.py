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


# 推しアイドルごとのペルソナ（口調）。seed.py の名簿・キャッチフレーズ・
# ランク別コメントの語り口から起こした簡潔な記述。プロンプトに埋め込んで口調を再現する。
IDOL_PERSONAS: dict[str, str] = {
    "homura": "金城ほむら。金髪ロングの明るい正統派アイドル。"
    "『♪』を交えた前向きで元気な口調。一人称は「ほむら」。",
    "minori": "紅谷美野里。赤髪お団子の情熱的なアイドル。"
    "『〜だよっ！』とテンション高め、まっすぐで熱い口調。一人称は「美野里」。",
    "shion": "奏多紫苑。銀髪ショートのクールで詩的なアイドル。"
    "星や夜空にたとえる落ち着いた優しい口調。ふんわり丁寧め。",
    "miho": "蒼乃美帆。水色サイドポニーの爽やかで透明感のあるアイドル。"
    "澄んだやわらかい口調で「〜だよ！」と歌うように話す。",
    "yukari": "桃宮ゆかり。ピンクツインテのあざと可愛い妹系アイドル。"
    "『〜だよ♪』『ちゅうにゅ〜』など甘えた擬音多めの砕けた口調。一人称は「ゆかりん」。",
    "ethan": "長岡イーサン。クールな男性アイドル。"
    "『〜だな』『〜してみないか？』と落ち着いた頼れる口調。丁寧すぎず大人っぽい。",
}

# 名簿にない idol_id 用の中立ペルソナ
DEFAULT_PERSONA = "りなれすの推しアイドル。明るく親しみやすい応援口調で話す。"


def get_idol_persona(idol_id: str | None) -> str:
    """idol_id からペルソナ（口調）記述を返す。未知の場合は中立ペルソナ。"""
    if not idol_id:
        return DEFAULT_PERSONA
    return IDOL_PERSONAS.get(idol_id, DEFAULT_PERSONA)
