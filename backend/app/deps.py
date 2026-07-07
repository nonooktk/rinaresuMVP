"""
認証関連の依存性を集約するモジュール。

現状はMVPのため X-User-Id ヘッダーで簡易的にユーザーを特定している。
後日、本番運用では Microsoft Entra ID 等によるトークン認証に差し替える想定。
その際も本モジュール（get_current_user）を差し替えるだけで
各ルーターの実装に影響が出ないよう、認証ロジックをここに集約している。
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


def get_current_user(
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    """
    X-User-Id ヘッダーからユーザーを取得する。

    TODO: 後日 Microsoft Entra ID 認証に差し替える。
    その際はここでBearerトークンを検証し、紐づくユーザーを解決する形に変更する。
    """
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id ヘッダーが必要です",
        )

    user = db.get(User, x_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="指定されたユーザーが見つかりません",
        )
    return user


def get_optional_user(
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User | None:
    """X-User-Idが任意のエンドポイント用（FAQ質問等）。"""
    if x_user_id is None:
        return None
    return db.get(User, x_user_id)
