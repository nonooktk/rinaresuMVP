"""
Pydanticスキーマ定義（APIリクエスト/レスポンス契約）。

フロントエンドと共有済みのJSON契約を厳守すること。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ---------- Idol ----------
class IdolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # スラッグID（例: sakura）。フロントのイラストパス /idols/{id}/main.svg と共有
    id: str
    name: str
    theme_color: str
    catchphrase: str


# ---------- User ----------
class UserCreate(BaseModel):
    # Google IDトークン（GIS の credential）。新規登録時は Google 認証必須。
    credential: str
    temp_id: str | None = None
    nickname: str
    idol_id: str


class UserUpdate(BaseModel):
    # 推し変更（idol_id のみ変更可。points / rank は引き継ぐため受け付けない）
    idol_id: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    temp_id: str
    nickname: str
    idol_id: str
    email: str | None = None
    points: int
    rank: int


# ---------- Auth（Google 認証） ----------
class GoogleAuthIn(BaseModel):
    # GIS のコールバックで受け取る IDトークン
    credential: str


class GoogleAuthOut(BaseModel):
    # 既存ユーザーかどうか
    registered: bool
    # 既存ユーザーの場合のみ返す（未登録時は None）
    user: UserOut | None = None
    # 既存ユーザーの確認用メール（未登録時は None、生値の露出は最小限に留める）
    email: str | None = None


class CommentOut(BaseModel):
    comment: str


# ---------- DeviceType ----------
class DeviceTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str
    weight_g: int
    points: int


# ---------- Device ----------
class DeviceCandidate(BaseModel):
    device_type: str
    label: str
    points: int
    confidence: float


class ClassifyResult(BaseModel):
    photo_id: str
    photo_url: str
    candidates: list[DeviceCandidate]


class DeviceCreate(BaseModel):
    device_type: str
    photo_id: str | None = None


class DeviceOut(BaseModel):
    id: int
    device_type: str
    label: str
    points: int
    photo_url: str | None = None
    status: str
    created_at: datetime


# ---------- Shipment ----------
class ShipmentCreate(BaseModel):
    device_ids: list[int]


class ShipmentCreateOut(BaseModel):
    id: int
    pdf_url: str
    total_points: int
    device_count: int


class ShipmentHistoryOut(BaseModel):
    id: int
    created_at: datetime
    status: str
    received_at: datetime | None
    device_count: int
    total_points: int
    devices: list[DeviceOut]


class UserHistoryOut(BaseModel):
    devices: list[DeviceOut]
    shipments: list[ShipmentHistoryOut]


# ---------- FAQ ----------
class FaqTopicOut(BaseModel):
    id: int
    category: str
    question: str


class FaqAskIn(BaseModel):
    question: str


class FaqAskOut(BaseModel):
    answer: str
    matched: bool


# ---------- Dev ----------
class ReceiveResult(BaseModel):
    points_added: int
    new_points: int
    new_rank: int
