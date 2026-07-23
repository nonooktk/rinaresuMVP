"""ユーザー関連のエンドポイント。"""
import random
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, Idol, IdolComment, Shipment, User
from app.schemas import (
    AuthSessionOut,
    CommentOut,
    DeviceOut,
    NextReward,
    RewardsStatus,
    ShipmentHistoryOut,
    UserCreate,
    UserDetailOut,
    UserHistoryOut,
    UserOut,
    UserUpdate,
)
from app.deps import get_current_user
from app.services.google_auth import verify_google_credential
from app.services.monthly import apply_monthly_reset, current_period_jst, is_limited_idol
from app.services.rewards import next_reward, rewards_status
from app.services.session_token import issue_session_token

router = APIRouter(prefix="/api/users", tags=["users"])


def _build_user_detail(user: User, db: Session) -> UserDetailOut:
    """ユーザーの特典状況（次特典・保有状況）を含む詳細レスポンスを組み立てる。

    呼び出し前に apply_monthly_reset を通し、月間ptが当月に整合していることを前提とする。
    """
    period = current_period_jst()
    nr = next_reward(user.monthly_points)
    rs = rewards_status(user, db, period)
    return UserDetailOut(
        id=user.id,
        temp_id=user.temp_id,
        nickname=user.nickname,
        idol_id=user.idol_id,
        email=user.email,
        points=user.points,
        rank=user.rank,
        monthly_points=user.monthly_points,
        monthly_period=user.monthly_period,
        active_visual=user.active_visual,
        next_reward=NextReward(**nr) if nr else None,
        rewards=RewardsStatus(**rs),
    )


def _generate_temp_id(db: Session) -> str:
    """「PID-XXXX」形式の仮IDを重複しないよう自動生成する。"""
    while True:
        suffix = "".join(random.choices(string.digits, k=4))
        temp_id = f"PID-{suffix}"
        exists = db.query(User).filter(User.temp_id == temp_id).first()
        if not exists:
            return temp_id


# 【F-2 対応】旧 `GET /api/users`（list_users）は削除した。
# 仮ID選択式ログインの名残で、認証なしに全ユーザー（email 含む）を列挙でき、
# PII 一括収集の穴になっていた。現行フローでは用途が無いため撤廃する。


@router.post("", response_model=AuthSessionOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """
    新規ユーザーを作成する。

    Google IDトークン（credential）を検証して本人性を確認し、
    その sub / email を保存する。temp_id は従来どおり内部で自動採番する
    （省略・指定いずれも可。互換のため残す）。
    同じ Google アカウント（sub）での重複登録は 409 とする。

    登録完了はログイン確立とみなし、セッション通行証（token）も併せて返す。
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
    return AuthSessionOut(user=UserOut.model_validate(user), token=issue_session_token(user.id))


@router.patch("/me", response_model=UserDetailOut)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    ログイン中ユーザー（通行証で特定）の推し・特殊ビジュアル表示を変更する。

    - idol_id: 推し変更（points / rank は引き継ぐ）。
        * 期間限定推し（is_limited）を選ぶには T1（当月）獲得が必須。未獲得は 403。
          限定推し選択時、元の推しを prev_idol_id に退避し、月替わりで自動復帰させる。
        * 通常推しに戻すと prev_idol_id はクリア（限定推しからの手動復帰にも対応）。
    - active_visual: "main"/"special" の切替。special は T2（特殊ビジュアル）獲得者のみ。未獲得は 403。
    いずれのフィールドも任意（None は変更しない）。両方 None は 400。
    """
    if payload.idol_id is None and payload.active_visual is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="変更内容がありません",
        )

    # 参照・変更の前に遅延リセットを通す（限定推しの有効判定は当月ベースで行うため）
    apply_monthly_reset(current_user, db)
    period = current_period_jst()

    # ---- 推し変更 ----
    if payload.idol_id is not None:
        target = db.get(Idol, payload.idol_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不正なidol_idです",
            )

        currently_limited = is_limited_idol(current_user.idol_id, db)

        if target.is_limited:
            # 期間限定推しは T1（当月）獲得済みでなければ選べない
            rs = rewards_status(current_user, db, period)
            if not rs["limited_idol_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="期間限定推しはT1特典（今月100pt）を達成すると選べます",
                )
            # 元の推し（通常推し）を退避。既に限定推しなら prev はそのまま維持する。
            if not currently_limited:
                current_user.prev_idol_id = current_user.idol_id
            current_user.idol_id = target.id
        else:
            # 通常推しへ変更。限定推しからの手動復帰なら退避先をクリアする。
            if currently_limited:
                current_user.prev_idol_id = None
            current_user.idol_id = target.id

    # ---- 特殊ビジュアル切替 ----
    if payload.active_visual is not None:
        if payload.active_visual not in ("main", "special"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="active_visual は main / special のいずれかです",
            )
        if payload.active_visual == "special":
            rs = rewards_status(current_user, db, period)
            if not rs["special_visual"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="特殊ビジュアルはT2特典（500pt）を達成すると使えます",
                )
        current_user.active_visual = payload.active_visual

    db.commit()
    db.refresh(current_user)
    return _build_user_detail(current_user, db)


@router.get("/{user_id}", response_model=UserDetailOut)
def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """指定ユーザーの情報を返す（本人のみ。email 等の PII を含むため）。

    月間pt・次特典・特典保有状況・active_visual を含む詳細レスポンスを返す。
    参照時に遅延リセット（月替わり）を適用する。

    【F-2 対応】従来は無認証で任意ユーザーの email を露出していた。
    本人以外の user_id は存在を伏せて 404 とする（存在秘匿）。
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")

    # 参照前に遅延リセットを適用（月替わりなら 0 リセット＋限定推し自動復帰）
    if apply_monthly_reset(current_user, db):
        db.commit()
        db.refresh(current_user)

    return _build_user_detail(current_user, db)


@router.get("/{user_id}/comment", response_model=CommentOut)
def get_user_comment(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """推しアイドル×現ランクのコメントテンプレからランダムに1件選び、{nickname}を置換して返す。

    【F-2 対応】本人のみ（あだ名を含むため）。本人以外は 404（存在秘匿）。
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ユーザーが見つかりません")
    user = current_user

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
def get_user_history(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ユーザーのデバイス・送付履歴を返す（本人のみ）。

    【F-2 対応】従来は無認証で任意ユーザーの端末・送付履歴を露出していた（IDOR）。
    本人以外の user_id は存在を伏せて 404 とする（存在秘匿）。
    """
    if user_id != current_user.id:
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
