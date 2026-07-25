"""
毎日ログインボーナス（⭐️pt）の抽選・受領ロジック。

統括承認済みの確定仕様:
  - その日の初回ログイン（**JST 日付でその日初回のホーム表示**）で 1pt / 5pt / 10pt を
    均等ランダム付与する。
  - 付与先は **`users.monthly_points`（月間pt）のみ**。累計 `users.points` とランクは
    変えない（ランクは回収実績のみを表す現行思想を維持するため）。
  - 月間ptが動くため、T1(100)/T2(500)/T3(1000〜) を跨げば既存 `grant_rewards` で
    特典も付与される（この経路も実装・テスト対象）。
  - **抽選はサーバー側のみ**。リクエストから pt も user_id も受け取らない
    （通行証から本人を解決するため IDOR の余地が無い）。

設計上の踏襲点（前スプリントの知見）:
  - R-1 M-2: リクエスト冒頭で JST の値（period / bonus_date）を一度だけ確定し、
    リセット・付与・特典判定・レスポンス構築へ同じ値を渡す（月末・日付境界の不整合防止）。
  - R-1 B-1 / QA B2-1: 履歴 INSERT は `db.begin_nested()` の savepoint で隔離し、
    pt の加算は条件付き単一 UPDATE（原子加算）で行う。
"""
import random
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import LoginBonus, User
from app.services.monthly import (
    JST,
    atomic_add_monthly_points,
    atomic_monthly_reset,
    current_period_jst,
)
from app.services.rewards import grant_rewards, next_reward

# ---------- 抽選の重み（モジュール定数・後から調整可能） ----------
# 付与pt候補。統括確定仕様の既定は 1 / 5 / 10 の**均等**ランダム。
BONUS_POINT_CHOICES: tuple[int, ...] = (1, 5, 10)
# 各候補の重み（BONUS_POINT_CHOICES と同じ並び・同じ長さ）。
# 将来 1pt の比率を上げる等の調整はここだけを書き換えれば済む（再実装不要）。
BONUS_POINT_WEIGHTS: tuple[int, ...] = (1, 1, 1)


def current_date_jst(now: datetime | None = None) -> str:
    """現在（または now）の JST 日付を "YYYY-MM-DD" 形式で返す。

    既存 `services/monthly.py::current_period_jst()` と**同じ zoneinfo 方式**にそろえる。
    now を渡す場合、tz-aware なら JST に変換、naive なら JST とみなす（テスト用）。
    """
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is not None:
        now = now.astimezone(JST)
    return now.strftime("%Y-%m-%d")


def current_keys_jst(now: datetime | None = None) -> tuple[str, str]:
    """リクエスト冒頭で JST の (period, bonus_date) を**一度だけ**確定して返す。

    【R-1 M-2 対応】`current_period_jst()` と `current_date_jst()` を別々に呼ぶと、
    月末 23:59:59.999… をまたいだ瞬間に「先月の period ＋ 今月の bonus_date」という
    組み合わせが生まれ得る。同一の `now` から両方を導出することでこれを封じる。
    """
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is not None:
        now = now.astimezone(JST)
    return current_period_jst(now), current_date_jst(now)


def draw_bonus_points() -> int:
    """付与pt を抽選する（**サーバー側のみ**。クライアントの申告値は一切使わない）。"""
    return random.choices(BONUS_POINT_CHOICES, weights=BONUS_POINT_WEIGHTS, k=1)[0]


def is_available(db: Session, user_id: int, bonus_date: str) -> bool:
    """その日（JST）のログインボーナスが未受領なら True を返す。

    `GET /api/users/{id}` の `login_bonus_available` の判定に使う（本人スコープ内で
    呼ばれるため、他人の受領状況は漏れない）。
    """
    exists = (
        db.query(LoginBonus)
        .filter(LoginBonus.user_id == user_id, LoginBonus.bonus_date == bonus_date)
        .first()
    )
    return exists is None


def claim(user: User, db: Session, period: str, bonus_date: str) -> dict:
    """当日ぶんのログインボーナスを受け取る（冪等・並行安全）。

    処理順序は統括確定仕様どおり厳守する:
      1. `atomic_monthly_reset` で**月替わりを先に通す**
         （月初の claim が先月ぶんに乗ってしまうのを防ぐ）
      2. `login_bonuses` へ INSERT（savepoint 隔離）。
         `IntegrityError`＝UNIQUE(user_id, bonus_date) 衝突＝「本日受領済み」として
         savepoint だけロールバックし `granted=False` を返す（エラーにはしない）
      3. `atomic_add_monthly_points` で**月間ptのみ**原子加算
      4. 加算後の値を読み直して `grant_rewards` で特典判定

    **累計pt加算・ランク再計算は行わない**（統括確定仕様）。

    戻り値: {"granted","points","monthly_points","next_reward","rewards_granted"}
    """
    user_id = user.id

    # ---- 1. 月替わりの遅延リセットを先に通す ----
    # 「翌月1日の初回ログイン」が先月の月間ptに加算されないよう、必ず加算より前に行う。
    atomic_monthly_reset(db, user_id, period)

    # ---- 2. 受領履歴を INSERT（savepoint で隔離） ----
    points = draw_bonus_points()
    try:
        # 【B-1 方式】savepoint 内で INSERT する。UNIQUE 衝突（同日2回目・並行 claim の
        # 敗者）が起きても、ここで作った savepoint だけがロールバックされ、
        # 手順1の月替わりリセットなど外側の変更は無傷のまま残る。
        with db.begin_nested():
            db.add(
                LoginBonus(user_id=user_id, bonus_date=bonus_date, points=points)
            )
            db.flush()
    except IntegrityError:
        # 本日は受領済み。ptは足さずに現状の月間ptだけ返す（200＋granted=false）。
        db.refresh(user)
        current_mp = user.monthly_points
        db.commit()
        return {
            "granted": False,
            "points": 0,
            "monthly_points": current_mp,
            "next_reward": next_reward(current_mp),
            "rewards_granted": [],
        }

    # ---- 3. 月間ptのみ原子加算（累計pt・ランクには触れない） ----
    atomic_add_monthly_points(db, user_id, points)

    # ---- 4. 加算後の最新値を読み直して特典判定 ----
    # 並行受領（別フローの検収完了など）と混ざっても取りこぼさないよう、
    # 受領処理と同じく「加算後の値から逆算した区間」で閾値を判定する。
    db.refresh(user)
    new_mp = user.monthly_points
    old_mp = new_mp - points
    granted_rewards = grant_rewards(user, old_mp, new_mp, period, db)

    db.commit()

    return {
        "granted": True,
        "points": points,
        "monthly_points": new_mp,
        "next_reward": next_reward(new_mp),
        "rewards_granted": granted_rewards,
    }
