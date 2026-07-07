"""
SQLAlchemyモデル定義。

りなれすMVPで扱う主要エンティティ（アイドル、ユーザー、デバイス種別、
デバイス、送付、アイドルコメント、FAQ）をここに集約する。
"""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
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

    idol: Mapped["Idol"] = relationship(back_populates="users")
    devices: Mapped[list["Device"]] = relationship(back_populates="user")
    shipments: Mapped[list["Shipment"]] = relationship(back_populates="user")


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
