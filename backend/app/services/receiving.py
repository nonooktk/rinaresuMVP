"""
受領（検収）処理の共通ロジック。

送付物の受領＝「shipment とその配下 devices を received にし、
合計ポイントをユーザーに付与してランクを再計算する」処理を、
開発用 API（routers/dev.py）とユーザー向け検収完了 API（routers/shipments.py）の
両方から共通利用できるよう関数として切り出したもの。

挙動は従来 dev.py にあった実装と同一（未受領→受領・ポイント加算・ランク再計算）。
"""
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Device, Shipment, User
from app.schemas import ReceiveResult
from app.services.points import calc_rank


def receive_shipment_core(shipment: Shipment, db: Session) -> ReceiveResult:
    """
    受領処理の中核。

    渡された shipment（未受領前提）を受領済みにし、配下 devices も received にする。
    合計ポイントをユーザーに付与してランクを再計算し、ReceiveResult を返す。

    - shipment が既に received の場合は 400
    - ユーザーが見つからない場合は 404
    呼び出し側で「shipment の取得」「本人チェック」を済ませてから渡すこと。
    """
    if shipment.status == "received":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="この送付は既に受領済みです",
        )

    devices = db.query(Device).filter(Device.shipment_id == shipment.id).all()
    points_added = sum(d.points for d in devices)

    for d in devices:
        d.status = "received"

    shipment.status = "received"
    shipment.received_at = datetime.utcnow()

    user = db.get(User, shipment.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません",
        )

    user.points += points_added
    user.rank = calc_rank(user.points)

    db.commit()

    return ReceiveResult(
        points_added=points_added,
        new_points=user.points,
        new_rank=user.rank,
    )
