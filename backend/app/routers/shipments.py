"""送付（伝票発行）関連のエンドポイント。"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Device, Shipment, User
from app.schemas import (
    ReceiveResult,
    ShareTextOut,
    ShipmentCreate,
    ShipmentCreateOut,
)
from app.services.receiving import lock_shipment_for_receive, receive_shipment_core
from app.services.share_text import build_share_text
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


@router.post("/{shipment_id}/receive", response_model=ReceiveResult)
def receive_own_shipment(
    shipment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    自分の送付物の検収完了（受領）処理を行う。

    りなれすに端末が届いたことをユーザー自身が確認して押す想定のエンドポイント。
    受領処理の中核（devices/shipment を received に・ポイント加算・ランク再計算）は
    services/receiving.py に共通化しており、開発用 API と同じ挙動。

    - 他人の送付、または存在しない送付は 404（存在秘匿のため区別しない）
    - 受領済みは 400
    """
    # 受領対象を悲観ロックで取得（PGは行ロック。二重受領の排他は core の原子CASが担保）
    shipment = lock_shipment_for_receive(db, shipment_id)
    # 本人の送付でなければ、存在自体を伏せて 404 を返す
    if shipment is None or shipment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="送付が見つかりません",
        )

    return receive_shipment_core(shipment, db)


@router.get("/{shipment_id}/share-text", response_model=ShareTextOut)
def get_shipment_share_text(
    shipment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    受領済み送付物のシェア投稿文面を生成して返す。

    - 他人の送付、または存在しない送付は 404
    - 未受領（received 以外）の送付は 400（受領後の達成感を投稿する導線のため）
    - Azure OpenAI が使えれば AI 生成、失敗・未設定ならテンプレにフォールバック
    """
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or shipment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="送付が見つかりません",
        )
    if shipment.status != "received":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="受領済みの送付のみシェアできます",
        )

    text, generated_by = build_share_text(shipment, current_user, db)
    return ShareTextOut(text=text, generated_by=generated_by)


@router.get("/{shipment_id}/pdf")
def get_shipment_pdf(
    shipment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """送付伝票PDFファイルを返す（本人のみ）。

    【F-3 対応】従来は無認証で誰でも取得でき、連番 shipment_id で他人の伝票
    （仮ID・あだ名・端末一覧）を収集できた。receive/share-text と同じく owner スコープを課す。
    - 他人の送付、または存在しない送付は 404（存在秘匿）
    - 本人の送付だが PDF 未生成も 404
    """
    shipment = db.get(Shipment, shipment_id)
    if shipment is None or shipment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="送付が見つかりません")
    if not shipment.pdf_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDFが見つかりません")

    return FileResponse(
        shipment.pdf_path,
        media_type="application/pdf",
        filename=f"slip_{shipment_id}.pdf",
    )
