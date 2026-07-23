"""
月間ptの遅延リセット（月替わり処理）ロジック。

cron を使わず、「月間ptを参照・加算するたびに現在のJST年月と monthly_period を
比較し、不一致なら 0 リセット＋期間更新する」方式（遅延リセット）。
月間ptに触れるすべての箇所（GET /users/{id}・受領処理・PATCH /users/me）で
この apply_monthly_reset() を通すことで、月替わりの取りこぼしを防ぐ。

期間限定推し（T1）の自動復帰もここで行う: 月が替わったとき、限定推しを選択中
（prev_idol_id が保持されている）なら元の推しへ戻し、prev_idol_id をクリアする。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import Idol, User

# JST（Asia/Tokyo）。月の境界判定は常にこのタイムゾーンで行う。
JST = ZoneInfo("Asia/Tokyo")


def current_period_jst(now: datetime | None = None) -> str:
    """現在（またはnow）のJST年月を "YYYY-MM" 形式で返す。

    now を渡す場合、tz-aware なら JST に変換、naive なら JST とみなす（テスト用）。
    """
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is not None:
        now = now.astimezone(JST)
    return now.strftime("%Y-%m")


def is_limited_idol(idol_id: str | None, db: Session) -> bool:
    """指定スラッグが期間限定推し（is_limited=True）かどうかを返す。"""
    if not idol_id:
        return False
    idol = db.get(Idol, idol_id)
    return bool(idol and idol.is_limited)


def apply_monthly_reset(user: User, db: Session, period: str | None = None) -> bool:
    """月間ptの遅延リセットを適用する。状態を変更したら True を返す（呼び出し側で commit）。

    - user.monthly_period が現在のJST月と一致していれば何もしない（False）。
    - 不一致（月替わり）または未初期化なら:
        * monthly_points を 0 にリセット
        * monthly_period を現在月に更新
        * 期間限定推しを選択中（prev_idol_id 保持）なら元の推しへ自動復帰し prev_idol_id をクリア
    ここでは commit しない（GET/受領/PATCH の各呼び出し側でまとめて commit する）。
    """
    current = period or current_period_jst()

    if user.monthly_period == current:
        return False

    changed = False

    # 未初期化（None）は「今月から集計を始める」だけで、リセット扱いにはしない
    # （monthly_points は既定 0 のため実害は無いが、限定推しの復帰判定は行う）。
    if user.monthly_period is not None:
        # 実際に月が替わった → 月間ptを 0 に戻す
        if user.monthly_points != 0:
            user.monthly_points = 0
            changed = True

    if user.monthly_period != current:
        user.monthly_period = current
        changed = True

    # 期間限定推しの自動復帰: prev_idol_id が保持されている＝限定推しを選択中。
    # 月が替わった（この関数に入った）タイミングで元の推しへ戻す。
    if user.prev_idol_id is not None:
        user.idol_id = user.prev_idol_id
        user.prev_idol_id = None
        changed = True

    return changed
