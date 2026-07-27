"""
OpenAI 公式 API クライアントの初期化と、りなれすの個別ペルソナ設定。

環境変数が揃っていれば OpenAI クライアントを返す。未設定なら None を返し、
呼び出し元はテンプレートキーワードのフォールバックに切り替える。
"""
import os

try:
    from openai import OpenAI
except Exception:  # noqa: BLE001
    OpenAI = None  # type: ignore[assignment]


def get_openai_client():
    """
    OpenAI クライアントを返す。

    必要な環境変数（OPENAI_API_KEY）が揃っていなければ None を返す。
    呼び出し元はフォールバック処理に切り替える。
    """
    if OpenAI is None:
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        return OpenAI(api_key=api_key)
    except Exception:  # noqa: BLE001 — 初期化失敗時もフォールバックさせる
        return None


def get_deployment() -> str:
    """使用するモデル名を返す。デフォルトは gpt-4o-mini。"""
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# ペルソナ定義（6地域別）
IDOL_PERSONAS: dict[str, str] = {
    "riji": "リジ・チョー（東京）。明るくノリのいい都会派の陽キャ男子。トレンドと'映え'に敏感で、エコを'おしゃれでイケてる'ものとして推す。テンション高めの盛り上げ役だが、一方で急に冷静な分析を挟むギャップがあり、根は面倒見がいい。",
    
    "taka": "タカ・チャーン（栃木）。見た目は勇ましい鷹だが、中身は慎重で心配性の熟考型。丁寧に考えてから話す聞き上手で、相手を気づかう優しさが持ち味。栃木のいちごや日光の自然を愛する。",
    
    "kurosuke": "くろすけん（静岡）。寡黙で実直な回収係。多くを語らず'はい'と淡々こなす職人肌で、縁の下の力持ち。富士山とお茶を愛する。信頼感・安心感の担当で、地味だが確実。",
    
    "miirin": "みーりん（大阪）。明るくて世話好きな関西の陽キャ姉さん。呼び込み・盛り上げ担当でテンポよくツッコミも入る。人懐っこく親しみやすいムードメーカーで、回収を'めっちゃお得やん！'と前向きに勧める。",
    
    "hiroji": "ひろじぃ・ネクスト（京都）。京都の長老然とした物知り。ゆったり間を取って話し、含蓄と小ネタを挟む。中身は最新テックにも精通するギャップ持ちで、伝統と未来をつなぐ案内役。",
    
    "teraoman": "テラオーマン（長野）。熱血で頼れる力持ちヒーロー。重い家電も回収BOXも'よいしょ'と担ぐ働き者。まっすぐで面倒見がよく、ユーザーを励ます応援団長。長野の山とりんごを背負う。",
}

DEFAULT_PERSONA = "りなれすの推し。元気に自分らしく、親切な返信で話す。"


def get_idol_persona(idol_id: str | None) -> str:
    """idol_id からペルソナ（性格・説明）を返す。未定義の場合はデフォルトペルソナ。"""
    if not idol_id:
        return DEFAULT_PERSONA
    return IDOL_PERSONAS.get(idol_id, DEFAULT_PERSONA)