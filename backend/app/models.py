"""
SQLAlchemyモデル定義。

りなれすMVPで扱う主要エンティティ（アイドル、ユーザー、デバイス種別、
デバイス、送付、アイドルコメント、FAQ）をここに集約する。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Idol(Base):
    """推しアイドル情報。

    idはスラッグ文字列（例: sakura）。フロントエンドのイラストパス規約
    /idols/{id}/main.svg と共有しており、イラスト差し替え運用を容易にする。
    """
    __tablename__ = "idols"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    theme_color: Mapped[str] = mapped_column(String(7), nullable=False)  # 例: #FFB6C1
    catchphrase: Mapped[str] = mapped_column(String(200), nullable=False)
    # 期間限定推し（7人目・T1特典）かどうか。True の限定推しは通常一覧
    # （GET /api/idols）には出さず、T1獲得済みユーザーの /oshi にのみ登場させる。
    # 限定推しの定義は backend/app/limited_idol.py に集約し、seed が upsert する。
    is_limited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="idol")
    comments: Mapped[list["IdolComment"]] = relationship(back_populates="idol")


class User(Base):
    """アプリ利用ユーザー（本人確認前提のためニックネーム+仮IDで管理）。"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    temp_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    # Google アカウントの一意識別子（IDトークンの sub クレーム）。
    # ログイン時のみ Google 認証する方式のため、ユーザーの本人性はこの値で判定する。
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    # Google アカウントのメールアドレス（表示・確認用。認証キーには使わない）
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    idol_id: Mapped[str] = mapped_column(ForeignKey("idols.id"), nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ---------- pt特典プログラム（月間pt＋3段階特典） ----------
    # 累計 points（上）とは別軸の「月間pt」。ランク判定には使わない。
    # 遅延リセット方式: 参照・加算のたびに現在のJST年月と monthly_period を比較し、
    # 不一致なら 0 リセットして monthly_period を更新する（cron不要）。
    monthly_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 月間ptの集計対象月（"YYYY-MM"・JST基準）。None は未初期化（初回加算/参照時に確定）。
    monthly_period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # ホームのイラスト表示モード。"main"=通常 / "special"=特殊ビジュアル（T2獲得者のみ切替可）。
    active_visual: Mapped[str] = mapped_column(String(10), default="main", nullable=False)
    # 期間限定推し（T1）を選択中に、元の推しへ月替わりで自動復帰するための退避先。
    # idol_id と同じスラッグ文字列。限定推し選択時のみセットし、復帰・通常推し選択で None に戻す。
    prev_idol_id: Mapped[str | None] = mapped_column(String(30), nullable=True)

    idol: Mapped["Idol"] = relationship(back_populates="users")
    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="user")
    rewards: Mapped[list["UserReward"]] = relationship(back_populates="user")


class DeviceType(Base):
    """デバイス種別マスタ（手動入力・分類候補提示の両方で利用）。"""
    __tablename__ = "device_types"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)  # 例: smartphone
    label: Mapped[str] = mapped_column(String(50), nullable=False)   # 例: スマートフォン
    weight_g: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)


class Device(Base):
    """ユーザーが登録した回収対象デバイス。"""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    device_type_code: Mapped[str] = mapped_column(ForeignKey("device_types.code"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # registered: 登録済み未送付 / shipped: 送付済み / received: りなれす受領済み
    status: Mapped[str] = mapped_column(String(20), default="registered", nullable=False)
    shipment_id: Mapped[int | None] = mapped_column(ForeignKey("shipments.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="devices")
    shipment: Mapped["Shipment | None"] = relationship(back_populates="devices")


class Shipment(Base):
    """回収キット送付（伝票発行）情報。"""
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # issued: 伝票発行済み（未着荷） / received: りなれす受領済み
    status: Mapped[str] = mapped_column(String(20), default="issued", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="shipments")
    devices: Mapped[list["Device"]] = relationship(back_populates="shipment")


class IdolComment(Base):
    """アイドル×ランク別のコメントテンプレート。"""
    __tablename__ = "idol_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idol_id: Mapped[str] = mapped_column(ForeignKey("idols.id"), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1〜3
    template: Mapped[str] = mapped_column(String(300), nullable=False)  # {nickname} プレースホルダー入り

    idol: Mapped["Idol"] = relationship(back_populates="comments")


class FaqEntry(Base):
    """FAQボット用の質問回答エントリ。"""
    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)  # shipping/points/data_erase
    question: Mapped[str] = mapped_column(String(200), nullable=False)
    keywords: Mapped[str] = mapped_column(String(300), nullable=False)  # カンマ区切り
    answer: Mapped[str] = mapped_column(String(500), nullable=False)  # {nickname} プレースホルダー可


class UserReward(Base):
    """pt特典プログラムの付与履歴（1レコード＝1回の特典獲得）。

    受領処理で月間ptが閾値を跨いだときに作成する。
    - tier: "T1" / "T2" / "T3"
    - threshold: 跨いだ閾値（100 / 500 / 1000,2000,3000...）
    - period: 獲得した月（"YYYY-MM"・JST）。月が替われば同一閾値でも再獲得できる。
    - reward_type: "limited_idol"（T1）/ "special_visual"（T2）/ "handshake_ticket"（T3）

    保有状況の算出方式（専用カウンタ列を持たず、このテーブルの集計で表す）:
      - 特殊ビジュアル（恒久）: reward_type="special_visual" のレコードが1件でもあれば獲得済み
      - 期間限定推し（当月のみ）: reward_type="limited_idol" かつ period=当月 のレコードがあれば有効
      - 抽選券（恒久・積み上げ）: reward_type="handshake_ticket" のレコード件数＝保有枚数

    同一 period 内での同一 threshold の重複付与を DB レベルでも防ぐため、
    UNIQUE(user_id, threshold, period) の保険をかける（跨ぎ判定でも防いでいる）。
    """
    __tablename__ = "user_rewards"
    __table_args__ = (
        UniqueConstraint("user_id", "threshold", "period", name="uq_user_reward_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(4), nullable=False)  # T1 / T2 / T3
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"（JST）
    reward_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="rewards")
