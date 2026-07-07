"""ユーザー関連のエンドポイント。"""
import random
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Idol, IdolComment, Shipment, User
from app.schemas import (
    CommentOut,
    DeviceOut,
    ShipmentHistoryOut,
    UserCreate,
    UserHistoryOut,
    UserOut,
    UserUpdate,
)
from app.deps import get_current_user
from app.services.google_auth import verify_google_credential

router = APIRouter(prefix="/api/users", tags=["users"])


def _generate_temp_id(db: Session) -> str:
    """「PID-XXXX」形式の仮IDを重複しないよう自動生成する。"""
    while True:
        suffix = "".join(random.choices(string.digits, k=4))
        temp_id = f"PID-{suffix}"
        exists = db.query(User).filter(User.temp_id == temp_id).first()
        if not exists:
            return temp_id


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    """ログイン選択用のユーザー一覧を返す。"""
    return db.query(User).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """
    新規ユーザーを作成する。

    Google IDトークン（credential）を検証して本人性を確認し、
    その sub / email を保存する。temp_id は従来どおり内部で自動採番する
    （省略・指定いずれも可。互換のため残す）。
    同じ Google アカウント（sub）での重複登録は 409 とする。
    """
    # まず Google 認証を検証（失敗なら 401）
    try:
        identity = verify_google_credential(payload.credential)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google 認証に失敗しました。ログインからやり直してください",
        )

    # 同じ Google アカウントで既に登録済みなら 409
    if db.query(User).filter(User.google_sub == identity.sub).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="このGoogleアカウントは既に登録されています",
        )

    # SQLiteは既定でFK制約を強制しないため、アイドルの存在を明示的に確認する
    if db.get(Idol, payload.idol_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不正なidol_idです",
        )
    if payload.temp_id:
        existing = db.query(User).filter(User.temp_id == payload.temp_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="この仮IDは既に使用されています",
            )
        temp_id = payload.temp_id
    else:
        temp_id = _generate_temp_id(db)

    user = User(
        temp_id=temp_id,
        google_sub=identity.sub,
        email=identity.email,
        nickname=payload.nickname,
        idol_id=payload.idol_id,
        points=0,
        rank=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/me", response_model=UserOut)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ログイン中ユーザー（X-User-Id ヘッダーで特定）の推しを変更する。

    idol_id のみ変更でき、points / rank は引き継ぐ（一切変更しない）。
    SQLiteは既定でFK制約を強制しないため、アイドルの存在を明示的に確認する。
    """
    if db.get(Idol, payload.idol_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不正なidol_idです",
        )

    current_user.idol_id = payload.idol_id
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """指定ユーザーの情報を返す。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")
    return user


@router.get("/{user_id}/comment", response_model=CommentOut)
def get_user_comment(user_id: int, db: Session = Depends(get_db)):
    """推しアイドル×現ランクのコメントテンプレからランダムに1件選び、{nickname}を置換して返す。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")

    candidates = (
        db.query(IdolComment)
        .filter(IdolComment.idol_id == user.idol_id, IdolComment.rank == user.rank)
        .all()
    )
    if not candidates:
        # 万一該当ランクのコメントがない場合のフォールバック
        comment_text = f"{user.nickname}、いつもありがとう！"
    else:
        template = random.choice(candidates).template
        comment_text = template.replace("{nickname}", user.nickname)

    return CommentOut(comment=comment_text)


def _device_to_out(device: Device) -> DeviceOut:
    """DeviceモデルをDeviceOutスキーマに変換する（写真URL組み立て含む）。"""
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


@router.get("/{user_id}/history", response_model=UserHistoryOut)
def get_user_history(user_id: int, db: Session = Depends(get_db)):
    """ユーザーのデバイス・送付履歴を返す。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")

    devices = db.query(Device).filter(Device.user_id == user_id).all()
    shipments = (
        db.query(Shipment)
        .filter(Shipment.user_id == user_id)
        .order_by(Shipment.created_at.desc())
        .all()
    )

    shipment_outs = []
    for sh in shipments:
        sh_devices = db.query(Device).filter(Device.shipment_id == sh.id).all()
        total_points = sum(d.points for d in sh_devices)
        shipment_outs.append(
            ShipmentHistoryOut(
                id=sh.id,
                created_at=sh.created_at,
                status=sh.status,
                received_at=sh.received_at,
                device_count=len(sh_devices),
                total_points=total_points,
                devices=[_device_to_out(d) for d in sh_devices],
            )
        )

    return UserHistoryOut(
        devices=[_device_to_out(d) for d in devices],
        shipments=shipment_outs,
    )
