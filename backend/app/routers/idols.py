"""アイドル情報関連のエンドポイント。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Idol
from app.schemas import IdolOut

router = APIRouter(prefix="/api/idols", tags=["idols"])


@router.get("", response_model=list[IdolOut])
def list_idols(db: Session = Depends(get_db)):
    """全アイドル一覧を返す。"""
    return db.query(Idol).all()
