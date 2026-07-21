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
    # 既存ユーザーのみ発行するセッション通行証（未登録時は None）。
    # 以降の API 呼び出しは Authorization: Bearer でこれを送る。
    token: str | None = None


class AuthSessionOut(BaseModel):
    # 新規登録完了時のレスポンス（登録＝ログイン確立とみなし通行証を返す）
    user: UserOut
    token: str


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
    # 判定手段（"ai": gpt-4o Vision / "mock": フォールバック）。
    # フロントは無視して良い後方互換フィールド。
    generated_by: str = "mock"


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
    # 回答の生成方法（"ai" or "keyword"）。フロントは無視して良い後方互換フィールド。
    generated_by: str = "keyword"


# ---------- Share（シェア投稿文面） ----------
class ShareTextOut(BaseModel):
    text: str
    # "ai"（Azure OpenAI 生成）または "template"（フォールバック）
    generated_by: str


# ---------- Dev / 受領 ----------
class ReceiveResult(BaseModel):
    points_added: int
    new_points: int
    new_rank: int
