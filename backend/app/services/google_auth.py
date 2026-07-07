"""
Google IDトークン（GIS の credential）検証を集約するサービス。

ログイン/新規登録の入口だけ Google 認証する方式のため、
フロントから受け取った credential（IDトークン）をここで検証し、
sub / email を取り出す。auth ルーターと users ルーターの双方から共通利用する。

検証失敗時は ValueError を投げるので、呼び出し側で 401 に変換すること。
"""
import os

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

# 秘匿値ではないため既定値としてクライアントIDを埋め込む。
# 本番等では環境変数 GOOGLE_CLIENT_ID で上書きできる。
DEFAULT_GOOGLE_CLIENT_ID = (
    "39205794623-c6r088k3pchlajvbt2kvtse8daec7iqk.apps.googleusercontent.com"
)


def get_client_id() -> str:
    """検証に用いる Google クライアントID（aud）を返す。"""
    return os.environ.get("GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID)


class GoogleIdentity:
    """検証済みの Google アカウント情報。"""

    def __init__(self, sub: str, email: str | None):
        self.sub = sub
        self.email = email


def verify_google_credential(credential: str) -> GoogleIdentity:
    """
    GIS から受け取った credential（IDトークン）を検証し、
    Google アカウントの sub / email を返す。

    検証に失敗した場合（署名不正・aud不一致・期限切れ・sub欠落など）は
    ValueError を送出する。
    """
    if not credential:
        raise ValueError("credential が空です")

    try:
        # aud（クライアントID）と署名・有効期限を Google 側で検証する
        info = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            get_client_id(),
        )
    except Exception as exc:  # noqa: BLE001 — ライブラリは多様な例外を投げるため一括で扱う
        raise ValueError("Google IDトークンの検証に失敗しました") from exc

    sub = info.get("sub")
    if not sub:
        raise ValueError("IDトークンに sub が含まれていません")

    return GoogleIdentity(sub=sub, email=info.get("email"))
