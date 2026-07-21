"""
アプリ独自のセッション通行証（署名付き JWT）を発行・検証するサービス。

【背景】従来は API の本人特定を `X-User-Id` ヘッダー（自己申告の整数ID）に頼っており、
検証が無いため任意ユーザーへのなりすましが可能だった（脆弱性 F-1）。
本モジュールで HS256 署名付きトークンを発行し、`deps.get_current_user` がこれを
毎リクエスト検証することで、資格情報を偽造不能にする。

【方式】ログイン/登録の入口で Google 認証に成功したユーザーに対し発行する。
ペイロードは `sub`（=user id の文字列）と `exp`（既定 7 日）。
署名鍵は環境変数 `SESSION_SECRET` から読む（ハードコード禁止）。

【鍵の扱い（fail-closed）】
- `SESSION_SECRET` が設定されていればそれを使う。
- 未設定のとき:
    - ローカル開発（SQLite の DATABASE_URL）でのみ dev 専用の明示デフォルト鍵にフォールバックする。
    - 本番（非 SQLite = PostgreSQL 等）では既知の弱鍵での署名を許さず、発行/検証を明示的に失敗させる。
  → 本番で秘匿鍵の設定漏れがあっても「弱い既知鍵で通ってしまう」事故を防ぐ。
"""
from __future__ import annotations

import os
import time

import jwt

from app.database import DATABASE_URL

# JWT 署名アルゴリズム（対称鍵 HMAC-SHA256）
_ALGORITHM = "HS256"
# トークンの既定有効期間（7 日）
DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60

# ローカル開発（SQLite）専用の弱鍵。本番では絶対に使わない（下記 _get_secret 参照）。
_DEV_ONLY_SECRET = "dev-only-insecure-session-secret-change-me"


class SessionConfigError(RuntimeError):
    """署名鍵の設定不備（本番で SESSION_SECRET 未設定など）。発行時は 5xx 相当。"""


class SessionError(Exception):
    """通行証の検証失敗（欠如・改ざん・失効・不正な sub）。検証時は 401 相当。"""


def _get_secret() -> str:
    """署名/検証に用いる秘密鍵を返す。設定不備なら SessionConfigError。"""
    secret = os.environ.get("SESSION_SECRET")
    if secret:
        return secret

    # 未設定時のフォールバック方針
    if DATABASE_URL.startswith("sqlite"):
        # ローカル開発のみ dev 専用鍵を許可する
        return _DEV_ONLY_SECRET

    # 本番（非 SQLite）で未設定 → 既知の弱鍵での署名を拒否し fail-closed
    raise SessionConfigError(
        "SESSION_SECRET が未設定です。本番環境では必須です（Container App の env に設定してください）。"
    )


def issue_session_token(user_id: int, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """user_id に対するセッション通行証（JWT）を発行する。

    設定不備（本番で鍵未設定）の場合は SessionConfigError を送出する。
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),  # JWT 仕様に合わせ sub は文字列
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def verify_session_token(token: str) -> int:
    """通行証を検証し、含まれる user id（int）を返す。

    署名不正・失効・欠落・sub 不正など、あらゆる検証失敗は SessionError に集約する
    （呼び出し側は 401 に変換する）。→ 検証は常に fail-closed。
    """
    if not token:
        raise SessionError("トークンが空です")

    try:
        secret = _get_secret()
    except SessionConfigError as exc:
        # 本番で鍵未設定 → 検証も通さない（なりすまし防止のため 401 扱い）
        raise SessionError("署名鍵が利用できません") from exc

    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:  # 署名不正・期限切れ・形式不正などを一括で弾く
        raise SessionError("トークンの検証に失敗しました") from exc

    sub = payload.get("sub")
    if sub is None:
        raise SessionError("トークンに sub がありません")
    try:
        return int(sub)
    except (TypeError, ValueError) as exc:
        raise SessionError("トークンの sub が不正です") from exc
