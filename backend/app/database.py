"""
DB接続設定を集約するモジュール。

環境変数 DATABASE_URL が設定されていればそれを使用し、
未設定の場合は既定値として SQLite (data/rinaresu.db) を使用する。
将来 PostgreSQL 等に切り替える場合は DATABASE_URL を変更するだけでよい。
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# backend/ 直下の data ディレクトリを既定のSQLite置き場とする
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ローカル開発用に backend/.env を読み込む（存在しなければ何もしない）。
# 既に設定済みの環境変数は上書きしない（override=False）ため、本番の実 env が常に優先される。
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=False)
except ImportError:
    # python-dotenv 未導入でも動作させる（環境変数を直接使う運用にフォールバック）
    pass

DEFAULT_SQLITE_URL = f"sqlite:///{(DATA_DIR / 'rinaresu.db').as_posix()}"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)

# SQLiteの場合のみ、マルチスレッド対応のconnect_argsを付与する
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemyモデルの共通ベースクラス。"""
    pass


def get_db():
    """FastAPIの依存性注入用DBセッションジェネレータ。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
