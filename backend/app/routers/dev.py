"""
開発用エンドポイント。

本来はりなれす側の受領処理（倉庫スキャン等）で呼ばれる想定のAPI。
MVPでは開発・検証用に手動で叩けるようにしている。
本番運用時は認証・権限チェックを追加するか、この router 自体を除外すること。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Shipment, User
from app.services.points import calc_rank
from app.schemas import ReceiveResult

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/shipments/{shipment_id}/receive", response_model=ReceiveResult)
def receive_shipment(shipment_id: int, db: Session = Depends(get_db)):
    """
    開発用: 送付物の受領処理を行う。

    shipmentとその配下のdevicesをreceivedにし、
    ユーザーに合計ポイントを付与してランクを再計算する。
    """
    shipment = db.get(Shipment, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="送付が見つかりません")
    if shipment.status == "received":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="この送付は既に受領済みです",
        )

    devices = db.query(Device).filter(Device.shipment_id == shipment_id).all()
    points_added = sum(d.points for d in devices)

    for d in devices:
        d.status = "received"

    shipment.status = "received"
    shipment.received_at = datetime.utcnow()

    user = db.get(User, shipment.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")

    user.points += points_added
    user.rank = calc_rank(user.points)

    db.commit()

    return ReceiveResult(
        points_added=points_added,
        new_points=user.points,
        new_rank=user.rank,
    )
