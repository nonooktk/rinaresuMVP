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

from sqlalchemy import and_, case, exists, or_, select, update
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
        # 【B2-3 対応】復帰先アイドルの存在を検証する。無効な slug（将来アイドルを
        # seed から外した等）なら現在の推しを維持し、退避先だけクリアして安全側に倒す。
        if db.get(Idol, user.prev_idol_id) is not None:
            user.idol_id = user.prev_idol_id
        user.prev_idol_id = None
        changed = True

    return changed


def atomic_monthly_reset(db: Session, user_id: int, period: str) -> None:
    """月替わりの遅延リセットを**単一の原子的 UPDATE** で行う（受領処理の並行安全化）。

    【B2-1 対応】受領処理は並行実行され得るため、Python 側の read-modify-write
    （apply_monthly_reset の属性代入）だと月境界でリセットが競合する。ここでは
    「period が当月でない場合のみ 0 リセット＋period更新＋限定推し自動復帰」を
    WHERE 句で条件化した 1 本の UPDATE にすることで、同一ユーザーの並行受領でも
    再ゼロ化などの不整合を防ぐ（当月に一致していれば 0 行更新＝no-op）。

    【B2-3 対応】復帰先 idol は EXISTS で存在検証し、無効なら現推しを維持する。
    """
    # prev_idol_id が実在するときだけ prev へ復帰。無ければ現 idol_id を維持。
    revert_idol = case(
        (
            and_(
                User.prev_idol_id.isnot(None),
                exists(select(Idol.id).where(Idol.id == User.prev_idol_id)),
            ),
            User.prev_idol_id,
        ),
        else_=User.idol_id,
    )
    db.execute(
        update(User)
        .where(
            User.id == user_id,
            or_(User.monthly_period.is_(None), User.monthly_period != period),
        )
        .values(
            monthly_points=0,
            monthly_period=period,
            idol_id=revert_idol,
            prev_idol_id=None,
        )
    )


def atomic_add_points(db: Session, user_id: int, points_added: int) -> None:
    """累計pt・月間ptを**原子的 UPDATE** で加算する（ロストアップデート防止）。

    【B2-1 対応】`user.points += x` のアプリ側 read-modify-write は行ロックが無く、
    並行受領で全リクエストが同じ値を読んで潰し合う（QA 実証: 10並行で 500→50）。
    `SET points = points + :x` の単一 SQL に置き換えることで、SQLite（書込ロック下で
    原子実行）・PostgreSQL（行更新の原子性）ともにロストアップデートを排除する。
    """
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            points=User.points + points_added,
            monthly_points=User.monthly_points + points_added,
        )
    )


def sync_monthly(user: User, db: Session, period: str) -> bool:
    """遅延リセットを適用し、変更があれば commit する（GET/認証/参照系の共通口）。

    【M-2/H-1 対応】呼び出し側でリクエスト冒頭に `period = current_period_jst()` を
    一度だけ確定し、この関数と後続の特典判定・レスポンス構築へ**同じ period** を渡すことで、
    JST月末境界での「リセット対象月」と「T1判定月」の不整合を防ぐ。
    受領処理（receiving.py）は末尾で一括 commit するため、ここではなく
    apply_monthly_reset を直接呼ぶ（この関数は単独 commit する参照系専用）。
    """
    changed = apply_monthly_reset(user, db, period)
    if changed:
        db.commit()
        db.refresh(user)
    return changed
