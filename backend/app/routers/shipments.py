"""送付（伝票発行）関連のエンドポイント。"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Device, Shipment, User
from app.schemas import ShipmentCreate, ShipmentCreateOut
from app.services.slip_pdf import generate_slip_pdf

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


@router.post("", response_model=ShipmentCreateOut, status_code=status.HTTP_201_CREATED)
def create_shipment(
    payload: ShipmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """対象デバイスを送付済みにし、伝票PDFを発行する。"""
    if not payload.device_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="device_idsが空です",
        )

    devices = (
        db.query(Device)
        .filter(
            Device.id.in_(payload.device_ids),
            Device.user_id == current_user.id,
            Device.status == "registered",
        )
        .all()
    )
    if len(devices) != len(set(payload.device_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登録済み(registered)でない、または存在しないデバイスIDが含まれています",
        )

    shipment = Shipment(user_id=current_user.id, status="issued")
    db.add(shipment)
    db.flush()  # shipment.idを確定させる

    for d in devices:
        d.status = "shipped"
        d.shipment_id = shipment.id

    device_dicts = [
        {"id": d.id, "device_type": d.device_type_code, "label": d.label, "points": d.points}
        for d in devices
    ]
    total_points = sum(d["points"] for d in device_dicts)

    pdf_path = generate_slip_pdf(
        shipment_id=shipment.id,
        user_id=current_user.id,
        temp_id=current_user.temp_id,
        nickname=current_user.nickname,
        devices=device_dicts,
    )
    shipment.pdf_path = pdf_path

    db.commit()
    db.refresh(shipment)

    return ShipmentCreateOut(
        id=shipment.id,
        pdf_url=f"/api/shipments/{shipment.id}/pdf",
        total_points=total_points,
        device_count=len(devices),
    )


@router.get("/{shipment_id}/pdf")
def get_shipment_pdf(shipment_id: int, db: Session = Depends(get_db)):
    """送付伝票PDFファイルを返す。"""
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or not shipment.pdf_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDFが見つかりません")

    return FileResponse(
        shipment.pdf_path,
        media_type="application/pdf",
        filename=f"slip_{shipment_id}.pdf",
    )
