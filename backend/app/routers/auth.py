"""
Google 認証（ログイン入口）関連のエンドポイント。

ログイン/新規登録の入口だけ Google 認証する方式。
フロントの GIS コールバックが取得した credential（IDトークン）を検証し、
その sub に紐づくユーザーが既に存在するかどうかを返す。

- 既存ユーザー: registered=true, user=UserOut を返す（フロントはそのままログイン）
- 未登録: registered=false を返す（フロントは credential を保持して /register へ）

いずれの場合も sub の生値はレスポンスに含めない（安全のため）。
未登録ユーザーの本人性は、フロントが保持した credential を
新規登録（POST /api/users）で再送し、サーバー側で再検証することで担保する。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import GoogleAuthIn, GoogleAuthOut, UserOut
from app.services.google_auth import verify_google_credential
from app.services.monthly import current_period_jst, sync_monthly
from app.services.session_token import issue_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/google", response_model=GoogleAuthOut)
def google_auth(payload: GoogleAuthIn, db: Session = Depends(get_db)):
    """Google IDトークンを検証し、既存ユーザーかどうかを返す。"""
    try:
        identity = verify_google_credential(payload.credential)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 認証に失敗しました",
        )

    user = db.query(User).filter(User.google_sub == identity.sub).first()
    if user is not None:
        # 【H-1 対応】月間ptを返す経路のため、応答前に遅延リセットを適用・commit する。
        # 月替わり後の初回ログインで localStorage に先月の月間pt/限定推し状態を保存させない。
        sync_monthly(user, db, current_period_jst())
        # 既存ユーザー: セッション通行証を発行してそのままログインさせる
        return GoogleAuthOut(
            registered=True,
            user=UserOut.model_validate(user),
            email=user.email,
            token=issue_session_token(user.id),
        )

    # 未登録: sub は返さず、フロントが保持している credential で登録に進ませる
    return GoogleAuthOut(registered=False, user=None, email=None)
