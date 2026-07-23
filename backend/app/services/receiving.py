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
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Device, Shipment, User
from app.schemas import ReceiveResult, RewardGranted
from app.services.monthly import (
    atomic_add_points,
    atomic_monthly_reset,
    current_period_jst,
)
from app.services.points import calc_rank
from app.services.rewards import grant_rewards


def lock_shipment_for_receive(db: Session, shipment_id: int) -> Shipment | None:
    """受領対象 shipment を取得する（PostgreSQL では行を悲観ロック）。

    【B2-1 対応】QA 指摘の「shipment を with_for_update で悲観ロック」を PostgreSQL で
    満たす。SQLite では with_for_update は実ロックにならず、SELECT の読取ロック保持後の
    書込がデッドロック（SQLITE_BUSY）を招くため付けない（SQLite の二重受領排他は
    receive_shipment_core の原子的 CAS が担保する）。両DBで安全になる。
    """
    query = db.query(Shipment).filter(Shipment.id == shipment_id)
    if db.get_bind().dialect.name != "sqlite":
        query = query.with_for_update()
    return query.first()


def receive_shipment_core(shipment: Shipment, db: Session) -> ReceiveResult:
    """
    受領処理の中核。

    渡された shipment を受領済みにし、配下 devices も received にする。
    合計ポイントをユーザーに付与してランクを再計算し、ReceiveResult を返す。
    さらに pt特典プログラムとして、受領時点のJST月に月間ptを加算し、
    旧→新の月間ptが跨いだ閾値ぶんの特典（T1/T2/T3）を付与する（複数同時付与あり）。

    - shipment が既に received の場合は 400
    - ユーザーが見つからない場合は 404
    呼び出し側で「shipment の取得」「本人チェック」を済ませてから渡すこと。

    【B2-1 対応・並行安全化】
    受領は並行実行され得る（同一伝票の二重POST／同一ユーザーの別伝票同時受領）。
    従来は shipment.status 判定と user.points の read-modify-write に排他が無く、
    (a) 二重受領が全件 200 になり「二重受領=400」が破れ、(b) ポイントがロストアップデート
    していた（QA 実証: 10並行で 500pt→50pt）。ここを以下で原子化する:
      1. shipment を原子的 CAS（UPDATE ... WHERE status!='received'）で受領確定。
         rowcount==0 なら他リクエストが先に受領済み → 400（両DBで確実に排他）。
         PostgreSQL では加えて事前 SELECT を with_for_update で悲観ロック（下記 core 呼び出し前）。
      2. 月間リセットは atomic_monthly_reset（条件付き単一 UPDATE）。
      3. 累計pt・月間ptは atomic_add_points（SET x = x + :v の原子加算）。
      4. 加算後の値を読み直して rank 再計算・特典判定に使う。
    """
    # 1. 原子的 CAS で受領を確定（DBレベルで二重受領を排他）
    now = datetime.utcnow()
    claimed = db.execute(
        update(Shipment)
        .where(Shipment.id == shipment.id, Shipment.status != "received")
        .values(status="received", received_at=now)
    )
    if claimed.rowcount == 0:
        # 既に受領済み（並行の別リクエストが先に確定した場合も含む）
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="この送付は既に受領済みです",
        )

    user_id = shipment.user_id

    # 2. 配下 devices を received に、合計ポイントを集計
    devices = db.query(Device).filter(Device.shipment_id == shipment.id).all()
    points_added = sum(d.points for d in devices)
    for d in devices:
        d.status = "received"

    # 3. 月間リセット（受領時点のJST月）→ 累計pt・月間ptを原子加算
    period = current_period_jst()
    atomic_monthly_reset(db, user_id, period)
    atomic_add_points(db, user_id, points_added)

    # 4. 加算後の最新値を読み直し、rank 再計算・特典判定
    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ユーザーが見つかりません",
        )
    # core UPDATE（reset/add）の結果を ORM オブジェクトへ反映
    db.refresh(user)

    user.rank = calc_rank(user.points)
    new_mp = user.monthly_points
    old_mp = new_mp - points_added  # この受領が跨いだ区間 = 加算前→加算後

    # 旧→新の月間ptで跨いだ閾値ぶんを付与（savepoint 隔離で並行付与も安全）
    granted = grant_rewards(user, old_mp, new_mp, period, db)

    db.commit()

    return ReceiveResult(
        points_added=points_added,
        new_points=user.points,
        new_rank=user.rank,
        monthly_points=user.monthly_points,
        rewards_granted=[RewardGranted(**g) for g in granted],
    )
