"""デバイス種別・デバイス登録関連のエンドポイント。"""
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import BASE_DIR, get_db
from app.deps import get_current_user
from app.models import Device, DeviceType, User
from app.schemas import (
    ClassifyResult,
    DeviceCreate,
    DeviceOut,
    DeviceTypeOut,
)
from app.services.classifier import classifier

router = APIRouter(prefix="/api", tags=["devices"])

PHOTOS_DIR = BASE_DIR / "data" / "photos"
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/device-types", response_model=list[DeviceTypeOut])
def list_device_types(db: Session = Depends(get_db)):
    """手動入力用のデバイス種別マスタ一覧を返す。"""
    return db.query(DeviceType).all()


@router.post("/devices/classify", response_model=ClassifyResult)
async def classify_device(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    アップロードされた写真からデバイス種別候補を判定する。

    写真は data/photos/ に保存し、/photos/... で配信する。
    """
    file_bytes = await file.read()

    # 拡張子を保持しつつ一意なファイル名を生成する
    original_name = file.filename or "unknown"
    ext = Path(original_name).suffix or ".jpg"
    photo_id = uuid.uuid4().hex
    saved_filename = f"{photo_id}{ext}"
    saved_path = PHOTOS_DIR / saved_filename

    with open(saved_path, "wb") as f:
        f.write(file_bytes)

    candidates, generated_by = classifier.classify_with_source(
        file_bytes, original_name, db
    )

    return ClassifyResult(
        photo_id=saved_filename,
        photo_url=f"/photos/{saved_filename}",
        candidates=[
            {
                "device_type": c["device_type"],
                "label": c["label"],
                "points": c["points"],
                "confidence": c["confidence"],
            }
            for c in candidates
        ],
        generated_by=generated_by,
    )


@router.post("/devices", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """デバイスを登録する。points/labelはdevice_typesマスタから確定させる。"""
    device_type = db.get(DeviceType, payload.device_type)
    if device_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不正なdevice_typeです",
        )

    photo_path = payload.photo_id if payload.photo_id else None
    if photo_path:
        # classifyが発行した「uuid16進32桁+拡張子」形式のみ許可（パストラバーサル対策）
        if not re.fullmatch(r"[0-9a-f]{32}\.[A-Za-z0-9]{1,8}", photo_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="photo_idの形式が不正です",
            )
        # 写真が実際に保存されているか確認する
        if not (PHOTOS_DIR / photo_path).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定されたphoto_idの写真が見つかりません",
            )

    device = Device(
        user_id=current_user.id,
        device_type_code=device_type.code,
        label=device_type.label,
        points=device_type.points,
        photo_path=photo_path,
        status="registered",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    photo_url = f"/photos/{device.photo_path}" if device.photo_path else None
    return DeviceOut(
        id=device.id,
        device_type=device.device_type_code,
        label=device.label,
        points=device.points,
        photo_url=photo_url,
        status=device.status,
        created_at=device.created_at,
    )


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(
    status: str | None = "registered",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ログインユーザーのデバイス一覧をステータスで絞り込んで返す（既定: registered）。"""
    query = db.query(Device).filter(Device.user_id == current_user.id)
    if status:
        query = query.filter(Device.status == status)
    devices = query.all()

    result = []
    for d in devices:
        photo_url = f"/photos/{d.photo_path}" if d.photo_path else None
        result.append(
            DeviceOut(
                id=d.id,
                device_type=d.device_type_code,
                label=d.label,
                points=d.points,
                photo_url=photo_url,
                status=d.status,
                created_at=d.created_at,
            )
        )
    return result
