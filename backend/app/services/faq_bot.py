"""
FAQボットサービス。

Azure OpenAI（gpt-4o）が使える場合は、りなれすの概要・FAQ全件・推しのペルソナを
システムプロンプトに埋め込んで自然な回答を生成する。
未設定・失敗時は従来どおりのキーワードマッチにフォールバックする（挙動不変）。
"""
from sqlalchemy.orm import Session

from app.models import DeviceType, FaqEntry, User
from app.services.ai import get_deployment, get_idol_persona, get_openai_client

# マッチしなかった場合の誘導文（{nickname}置換対応）
FALLBACK_ANSWER = (
    "ごめんね、その質問はまだ答えられないの…。"
    "『送付方法』『ポイント』『データ消去』について聞いてみてね！"
)

# りなれすの概要・使い方の要点（CLAUDE.md より抜粋してプロンプトに埋め込む）
APP_OVERVIEW = (
    "りなれすは、家庭に眠るジャンク端末（都市鉱山）を『推しアイドル×ポイント』で"
    "楽しく回収促進するスマホ向けアプリです。\n"
    "基本の流れ:\n"
    "1. 端末を写真に撮ると種類を判定してログに登録できる。\n"
    "2. 登録した端末で送付伝票PDFを発行し、印刷して着払いでりなれすへ郵送する。\n"
    "3. りなれすが受領・確認するとポイントが付与される（目安は10gにつき1ポイント）。\n"
    "4. ポイントに応じてランク（1〜3）が上がり、推しアイドルからのコメントが特別になる。\n"
    "データはりなれすの提携業者が専用ソフトで完全消去し、消去証明も発行されるので安全。\n"
    "送料は着払いでユーザー負担なし。伝票はコンビニのマルチコピー機でPDF印刷できる。"
)


def _build_faq_reference(db: Session) -> str:
    """seed の FAQ 全件を「Q: … / A: …」形式の参照テキストにまとめる。"""
    entries = db.query(FaqEntry).all()
    lines = []
    for e in entries:
        # answer 内の {nickname} は口調に紛れないよう素の参照として残す
        lines.append(f"Q: {e.question}\nA: {e.answer}")
    return "\n\n".join(lines)


def _build_device_type_reference(db: Session) -> str:
    """device_types マスタを「品目名（◯pt）」形式の参照テキストにまとめる。

    回収対象を AI が創作しない（マスタにない品目を答えない）ようにするための根拠情報。
    """
    types = db.query(DeviceType).all()
    return "・".join(f"{t.label}（{t.points}pt）" for t in types)


def _keyword_match(question: str, db: Session, user: User | None) -> tuple[str, bool]:
    """従来のキーワードマッチによる回答（フォールバック）。"""
    entries = db.query(FaqEntry).all()

    best_entry: FaqEntry | None = None
    best_match_count = 0

    for entry in entries:
        keywords = [kw.strip() for kw in entry.keywords.split(",") if kw.strip()]
        match_count = sum(1 for kw in keywords if kw in question)
        if match_count > best_match_count:
            best_match_count = match_count
            best_entry = entry

    nickname = user.nickname if user is not None else "あなた"

    if best_entry is None or best_match_count == 0:
        return FALLBACK_ANSWER, False

    answer = best_entry.answer.replace("{nickname}", nickname)
    return answer, True


def _answer_with_openai(
    client, question: str, db: Session, user: User | None
) -> str | None:
    """OpenAI で FAQ 回答を生成する。失敗時は None。"""
    if user is not None:
        persona = get_idol_persona(user.idol_id)
        nickname = user.nickname
        persona_note = (
            f"あなたは相談者の推しアイドルとして回答します。人物像・口調: {persona}\n"
            f"相談者のあだ名は「{nickname}」。親しみを込めて呼びかけながら答えてください。"
        )
    else:
        persona_note = (
            "推しアイドルはまだ選ばれていないので、中立で丁寧なやさしい口調で回答してください。"
        )

    faq_reference = _build_faq_reference(db)

    device_reference = _build_device_type_reference(db)

    system_prompt = (
        "あなたは都市鉱山回収促進アプリ『りなれす』のFAQサポート担当です。\n"
        f"{persona_note}\n\n"
        f"【アプリの概要と使い方】\n{APP_OVERVIEW}\n\n"
        f"【回収対象の端末（この一覧がすべて。ここにない品目を対象と答えない）】\n{device_reference}\n\n"
        f"【公式FAQ（この内容を根拠に答えること）】\n{faq_reference}\n\n"
        "【回答ルール】\n"
        "- 必ず日本語で、200文字程度までのやさしい表現で答える。\n"
        "- 上記のFAQ・概要に基づいて正確に答える。分からないことは断定せず、"
        "『送付方法・ポイント・データ消去について聞いてね』と案内する。\n"
        "- 回収対象を答えるときは上記一覧の品目名だけを挙げる。一覧にない端末を聞かれたら"
        "『その他小型家電』として送れる可能性がある旨を控えめに案内する。\n"
        "- 端末回収・ポイント・データ消去に無関係な質問には深入りせず、やんわり本題に戻す。\n"
        "- 前置きや繰り返しは避け、回答本文だけを出力する。"
    )

    try:
        resp = client.chat.completions.create(
            model=get_deployment(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        content = resp.choices[0].message.content
        return content.strip() if content else None
    except Exception:  # noqa: BLE001 — 失敗時はキーワードマッチにフォールバック
        return None


def answer_question(
    question: str, db: Session, user: User | None
) -> tuple[str, bool, str]:
    """
    質問文に対する FAQ 回答を返す。

    Azure OpenAI が使える場合は gpt-4o で生成、未設定・失敗時はキーワードマッチ。
    戻り値: (answer, matched, generated_by)
      generated_by は "ai" または "keyword"。
      matched は AI 回答時は常に True（回答を返せたため）、
      キーワードマッチ時は従来どおり一致有無を表す。
    """
    client = get_openai_client()
    if client is not None:
        answer = _answer_with_openai(client, question, db, user)
        if answer:
            return answer, True, "ai"

    # フォールバック（未設定・失敗時）: 従来のキーワードマッチ（挙動不変）
    answer, matched = _keyword_match(question, db, user)
    return answer, matched, "keyword"
