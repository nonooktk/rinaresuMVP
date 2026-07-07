"""
FAQボットサービス。

現状はキーワードマッチによる簡易実装。
後日 Azure OpenAI + RAG 構成に差し替え可能なよう、
関数インターフェース answer_question() を公開している点がポイント。
"""
from sqlalchemy.orm import Session

from app.models import FaqEntry, User

# マッチしなかった場合の誘導文（{nickname}置換対応）
FALLBACK_ANSWER = (
    "ごめんね、その質問はまだ答えられないの…。"
    "『送付方法』『ポイント』『データ消去』について聞いてみてね！"
)


def answer_question(question: str, db: Session, user: User | None) -> tuple[str, bool]:
    """
    質問文からFAQエントリをキーワードマッチで検索し、回答を返す。

    複数のFAQが該当する場合は最多一致（マッチしたキーワード数が最大）のものを採用する。
    戻り値: (answer, matched)
    """
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
