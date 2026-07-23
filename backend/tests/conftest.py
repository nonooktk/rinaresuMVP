"""
pytest 共通フィクスチャ。

pt特典プログラム（月間pt・遅延リセット・閾値判定・特典付与）の検証用。
テストごとに独立した一時 SQLite DB を使う。app.database は import 時に
DATABASE_URL を読むため、conftest の冒頭で環境変数を設定してから app を import する。
"""
import os
import tempfile

import pytest

# app を import する前にテスト用の一時 SQLite を指定する
_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="rinaresu_test_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
# 開発用 API は使わない
os.environ.setdefault("ENABLE_DEV_API", "1")

from app.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.migrate import run_migrations  # noqa: E402
from app.models import Idol, User  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.services.session_token import issue_session_token  # noqa: E402


def _init_db() -> None:
    """テーブル作成→マイグレーション→seed（本番起動と同順）。"""
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _reset_db():
    """各テストの前に DB を初期化（全テーブル drop→再作成→seed）。"""
    Base.metadata.drop_all(bind=engine)
    _init_db()
    yield


@pytest.fixture()
def db():
    """テスト内で使う DB セッション。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_user(db):
    """テストユーザーを直接 INSERT して返すファクトリ。"""
    counter = {"n": 0}

    def _make(idol_id: str = "homura", **kwargs) -> User:
        counter["n"] += 1
        n = counter["n"]
        user = User(
            temp_id=kwargs.pop("temp_id", f"PID-T{n:03d}"),
            google_sub=kwargs.pop("google_sub", f"test-sub-{n}"),
            email=kwargs.pop("email", f"user{n}@example.com"),
            nickname=kwargs.pop("nickname", f"テスト{n}"),
            idol_id=idol_id,
            **kwargs,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture()
def client():
    """認証トークンを付けられる TestClient。auth_headers ヘルパー付き。

    注意: 同ディレクトリの test_idor_manual.py が import 時に
    app.dependency_overrides[get_db] を自前の DB へ差し替える（グローバル汚染）。
    本フィクスチャでは get_db を conftest の DB（SessionLocal）へ明示的に上書きし、
    テスト終了時に元の override を復元することで、実行順に依存せず独立させる。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    def _get_db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _get_db_override

    test_client = TestClient(app)

    def auth_headers(user_id: int) -> dict:
        return {"Authorization": f"Bearer {issue_session_token(user_id)}"}

    test_client.auth_headers = auth_headers  # type: ignore[attr-defined]

    try:
        yield test_client
    finally:
        if previous is not None:
            app.dependency_overrides[get_db] = previous
        else:
            app.dependency_overrides.pop(get_db, None)
