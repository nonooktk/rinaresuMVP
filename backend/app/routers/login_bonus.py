"""毎日ログインボーナスのエンドポイント。

`POST /api/login-bonus/claim` の1本のみ。

セキュリティ方針（pt という価値を付与する API のため厳格にする）:
  - **認証必須**（`Authorization: Bearer <セッション通行証>`）。未認証は 401。
  - 対象は**通行証から解決した本人のみ**。リクエストで `user_id` を受け取らないため
    IDOR（他人への付与・他人の受領状況の観測）の余地がそもそも無い。
  - 付与pt は**サーバー側で抽選**する。リクエストから pt を受け取る口は作らない。
"""
from fastapi import APIRouter, Depends

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import LoginBonusClaimOut, NextReward, RewardGranted
from app.services.login_bonus import claim, current_keys_jst
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/login-bonus", tags=["login-bonus"])


@router.post("/claim", response_model=LoginBonusClaimOut)
def claim_login_bonus(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当日（JST）ぶんのログインボーナスを受け取る。

    - 初回: 200 / `granted=true` ＋ 付与pt・付与後の月間pt・次特典・跨いだ特典
    - 同日2回目以降: 200 / `granted=false`（**エラーにはしない**）
    - 未認証: 401
    """
    # 【R-1 M-2 対応】リクエスト冒頭で JST の period / bonus_date を一度だけ確定し、
    # 月替わりリセット・履歴 INSERT・特典判定へ同じ値を渡す。
    period, bonus_date = current_keys_jst()

    result = claim(current_user, db, period, bonus_date)

    nr = result["next_reward"]
    return LoginBonusClaimOut(
        granted=result["granted"],
        points=result["points"],
        monthly_points=result["monthly_points"],
        next_reward=NextReward(**nr) if nr else None,
        rewards_granted=[RewardGranted(**g) for g in result["rewards_granted"]],
    )
