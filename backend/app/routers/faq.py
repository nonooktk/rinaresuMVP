"""FAQボット関連のエンドポイント。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_optional_user
from app.models import FaqEntry, User
from app.schemas import FaqAskIn, FaqAskOut, FaqTopicOut
from app.services.faq_bot import answer_question

router = APIRouter(prefix="/api/faq", tags=["faq"])


@router.get("/topics", response_model=list[FaqTopicOut])
def list_faq_topics(db: Session = Depends(get_db)):
    """FAQトピック（カテゴリ・質問文）の一覧を返す。"""
    entries = db.query(FaqEntry).all()
    return [
        FaqTopicOut(id=e.id, category=e.category, question=e.question) for e in entries
    ]


@router.post("/ask", response_model=FaqAskOut)
def ask_faq(
    payload: FaqAskIn,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """
    質問文への FAQ 回答を返す。

    Azure OpenAI が使える場合は推しのペルソナ・あだ名を反映した自然な回答、
    未設定・失敗時は従来のキーワードマッチ（X-User-Id があれば{nickname}置換）。
    """
    answer, matched, generated_by = answer_question(
        payload.question, db, current_user
    )
    return FaqAskOut(answer=answer, matched=matched, generated_by=generated_by)
