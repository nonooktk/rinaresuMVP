"""
FastAPIエントリポイント。

CORSの許可オリジンは環境変数 CORS_ORIGINS（カンマ区切り）から読み、
未設定時は既定でフロントエンド(http://localhost:3000)を許可する。
/photos で写真ファイルを静的配信する。
起動時にテーブル作成とseed投入を行う。

開発用ルーター(/api/dev)は環境変数 ENABLE_DEV_API が "0" のとき無効化する
（未設定時は有効。ローカル動作は従来どおり）。
"""
import os

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI

from app.database import BASE_DIR, Base, SessionLocal, engine
from app.routers import auth, devices, dev, faq, idols, shipments, users
from app.seed import seed_all

app = FastAPI(title="りなれす API", description="都市鉱山回収促進アプリ りなれす バックエンドAPI")

# ---------- CORS設定 ----------
# 環境変数 CORS_ORIGINS をカンマ区切りで受け取り、未設定なら localhost:3000 を既定とする
cors_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 静的ファイル配信 ----------
PHOTOS_DIR = BASE_DIR / "data" / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")

# ---------- ルーター登録 ----------
app.include_router(auth.router)
app.include_router(idols.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(shipments.router)
app.include_router(faq.router)

# 開発用ルーターは ENABLE_DEV_API が "0" の場合は登録しない（本番での無効化用）
if os.environ.get("ENABLE_DEV_API", "1") != "0":
    app.include_router(dev.router)


@app.on_event("startup")
def on_startup():
    """起動時にテーブル作成とseedデータ投入を行う。"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()


@app.get("/")
def root():
    """疎通確認用のルートエンドポイント。"""
    return {"message": "りなれす API is running"}
