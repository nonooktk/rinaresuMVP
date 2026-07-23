"""アイドル情報関連のエンドポイント。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.limited_idol import LIMITED_IDOL
from app.models import Idol
from app.schemas import IdolOut

router = APIRouter(prefix="/api/idols", tags=["idols"])


@router.get("", response_model=list[IdolOut])
def list_idols(db: Session = Depends(get_db)):
    """通常アイドル一覧を返す（期間限定推し is_limited=True は除外）。

    期間限定推し（T1特典）は通常の選択肢には出さず、T1獲得済みユーザーの
    /oshi にのみ登場させるため、ここでは除外する。獲得者向けの取得は
    GET /api/idols/limited を使う。
    """
    return db.query(Idol).filter(Idol.is_limited.is_(False)).all()


@router.get("/limited", response_model=IdolOut)
def get_limited_idol(db: Session = Depends(get_db)):
    """当月の期間限定推し（7人目）を返す。

    定義の真実の源は backend/app/limited_idol.py で、seed が idols テーブルへ
    upsert している。フロントは T1 獲得済みユーザーの /oshi に限定推しカードを
    出すときにこれを取得する（選択可否の最終判定は PATCH /users/me 側で行う）。
    """
    idol = db.get(Idol, LIMITED_IDOL["id"])
    if idol is None or not idol.is_limited:
        # seed 前など、限定推しがまだ idols に無い場合
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="期間限定推しが設定されていません",
        )
    return idol
