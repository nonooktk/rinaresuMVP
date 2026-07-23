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
from app.schemas import ReceiveResult, RewardGranted
from app.services.monthly import apply_monthly_reset, current_period_jst
from app.services.points import calc_rank
from app.services.rewards import grant_rewards


def receive_shipment_core(shipment: Shipment, db: Session) -> ReceiveResult:
    """
    受領処理の中核。

    渡された shipment（未受領前提）を受領済みにし、配下 devices も received にする。
    合計ポイントをユーザーに付与してランクを再計算し、ReceiveResult を返す。

    さらに pt特典プログラムとして、受領時点のJST月に月間ptを加算し、
    旧→新の月間ptが跨いだ閾値ぶんの特典（T1/T2/T3）を付与する（複数同時付与あり）。

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

    # 累計ポイント（ランク判定はこちら。従来どおり挙動を変えない）
    user.points += points_added
    user.rank = calc_rank(user.points)

    # ---- 月間pt（特典判定軸）----
    # 受領時点のJST月を基準にする。参照・加算の前に遅延リセットを通し、
    # 月替わりなら 0 リセット＋期間更新＋限定推しの自動復帰を済ませる。
    period = current_period_jst()
    apply_monthly_reset(user, db, period)
    old_mp = user.monthly_points
    user.monthly_points = old_mp + points_added

    # 旧→新の月間ptで跨いだ閾値ぶんを付与（同一 period・同一 threshold は重複付与しない）
    granted = grant_rewards(user, old_mp, user.monthly_points, period, db)

    db.commit()

    return ReceiveResult(
        points_added=points_added,
        new_points=user.points,
        new_rank=user.rank,
        monthly_points=user.monthly_points,
        rewards_granted=[RewardGranted(**g) for g in granted],
    )
