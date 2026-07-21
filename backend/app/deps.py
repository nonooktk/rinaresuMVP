"""
認証関連の依存性を集約するモジュール。

本人特定は「アプリ独自セッション通行証（署名付き JWT）」で行う。
ログイン/登録の入口で Google 認証に成功したユーザーに通行証を発行し（services/session_token）、
以降の API 呼び出しは `Authorization: Bearer <通行証>` を必須とする。

【変更履歴】従来は `X-User-Id` ヘッダー（自己申告の整数ID）を検証なしで信用していたため、
ヘッダーの差し替えだけで任意ユーザーになりすませた（脆弱性 F-1）。→ X-User-Id の信用を撤廃し、
署名・有効期限を検証できる通行証に置き換えた。戻り値の型（User）は不変のため、
各ルーターの owner スコープ判定（user_id == current_user.id）はそのまま効く。
"""
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.session_token import SessionError, verify_session_token


def _extract_bearer(authorization: str | None) -> str | None:
    """`Authorization: Bearer <token>` からトークン本体を取り出す（無効な形式なら None）。"""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """
    セッション通行証（Authorization: Bearer）から本人を解決する。

    - 通行証が無い/形式不正/署名不正/失効 → 401
    - 通行証は妥当だが該当ユーザーが存在しない → 401
    """
    token = _extract_bearer(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です（Authorization: Bearer トークン）",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = verify_session_token(token)
    except SessionError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンが無効または失効しています",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンに対応するユーザーが見つかりません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    authorization: str | None = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> User | None:
    """
    通行証が任意のエンドポイント用（FAQ 質問等）。

    Bearer があれば検証してユーザーを返し、無ければ None（匿名）。
    トークンが不正な場合も、匿名として None を返す（このクラスの EP は認可判定に使わないため）。
    """
    token = _extract_bearer(authorization)
    if token is None:
        return None
    try:
        user_id = verify_session_token(token)
    except SessionError:
        return None
    return db.get(User, user_id)
