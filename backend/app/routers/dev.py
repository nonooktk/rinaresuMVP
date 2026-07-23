"""
開発用エンドポイント。

本来はりなれす側の受領処理（倉庫スキャン等）で呼ばれる想定のAPI。
MVPでは開発・検証用に手動で叩けるようにしている。
本番運用時は認証・権限チェックを追加するか、この router 自体を除外すること。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ReceiveResult
from app.services.receiving import lock_shipment_for_receive, receive_shipment_core

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/shipments/{shipment_id}/receive", response_model=ReceiveResult)
def receive_shipment(shipment_id: int, db: Session = Depends(get_db)):
    """
    開発用: 送付物の受領処理を行う。

    shipmentとその配下のdevicesをreceivedにし、
    ユーザーに合計ポイントを付与してランクを再計算する。
    受領処理の中核は services/receiving.py に共通化している（並行安全化済み）。
    """
    # 悲観ロックで取得（PG）。二重受領の排他は core の原子CASが担保。
    shipment = lock_shipment_for_receive(db, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="送付が見つかりません")

    return receive_shipment_core(shipment, db)
