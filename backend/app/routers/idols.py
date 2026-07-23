"""アイドル情報関連のエンドポイント。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.limited_idol import LIMITED_IDOL
from app.models import Idol, User
from app.schemas import IdolOut
from app.services.monthly import current_period_jst, sync_monthly
from app.services.rewards import rewards_status

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
def get_limited_idol(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当月の期間限定推し（7人目）を返す。

    【M-1 対応】限定推しは「獲得者だけが会える特典」として秘匿する方針。
    認証必須＋遅延リセット後の当月T1保有チェックを行い、**非保有者には 404**
    （存在秘匿・既存流儀に合わせる）を返す。フロント（/oshi）は 404 を正常系として
    扱い、限定枠を非表示にする。選択可否の最終判定は PATCH /users/me 側でも行う。

    定義の真実の源は backend/app/limited_idol.py で、seed が idols テーブルへ upsert している。
    """
    # 参照前に遅延リセット（月替わりなら当月T1が失効する）。period は一度だけ確定。
    period = current_period_jst()
    sync_monthly(current_user, db, period)

    rs = rewards_status(current_user, db, period)
    if not rs["limited_idol_active"]:
        # 非保有者には存在を伏せて 404（獲得者だけが会える特典）
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="期間限定推しが見つかりません",
        )

    idol = db.get(Idol, LIMITED_IDOL["id"])
    if idol is None or not idol.is_limited:
        # seed 前など、限定推しがまだ idols に無い場合
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="期間限定推しが見つかりません",
        )
    return idol
