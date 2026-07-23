"""月間ptの遅延リセット・期間限定推し自動復帰の純ロジックテスト。"""
from app.limited_idol import LIMITED_IDOL
from app.services.monthly import (
    apply_monthly_reset,
    current_period_jst,
    is_limited_idol,
)


def test_current_period_format():
    p = current_period_jst()
    assert len(p) == 7 and p[4] == "-"


def test_no_reset_within_same_month(db, make_user):
    period = current_period_jst()
    user = make_user(monthly_points=120, monthly_period=period)
    changed = apply_monthly_reset(user, db, period)
    assert changed is False
    assert user.monthly_points == 120
    assert user.monthly_period == period


def test_reset_on_month_change(db, make_user):
    # 先月に 300pt 貯めていたユーザーが当月アクセス → 0 リセット＋期間更新
    user = make_user(monthly_points=300, monthly_period="2000-01")
    current = current_period_jst()
    changed = apply_monthly_reset(user, db, current)
    assert changed is True
    assert user.monthly_points == 0
    assert user.monthly_period == current


def test_uninitialized_period_is_not_a_reset(db, make_user):
    # monthly_period=None（新規）→ 当月に初期化するだけ。points 0 は維持。
    user = make_user(monthly_points=0, monthly_period=None)
    current = current_period_jst()
    changed = apply_monthly_reset(user, db, current)
    assert changed is True  # period を設定するため変更あり
    assert user.monthly_points == 0
    assert user.monthly_period == current


def test_is_limited_idol_flag(db):
    assert is_limited_idol(LIMITED_IDOL["id"], db) is True
    assert is_limited_idol("homura", db) is False
    assert is_limited_idol(None, db) is False


def test_auto_revert_limited_idol_on_month_change(db, make_user):
    # 限定推しを選択中（prev_idol_id に元推しを退避）で月替わり → 元推しへ自動復帰
    user = make_user(
        idol_id=LIMITED_IDOL["id"],
        prev_idol_id="minori",
        monthly_points=150,
        monthly_period="2000-01",
    )
    current = current_period_jst()
    changed = apply_monthly_reset(user, db, current)
    assert changed is True
    assert user.idol_id == "minori"       # 元推しへ復帰
    assert user.prev_idol_id is None      # 退避先クリア
    assert user.monthly_points == 0       # 月間ptもリセット


def test_no_revert_for_normal_idol(db, make_user):
    # 通常推し（prev なし）は月替わりでも推しは変わらない
    user = make_user(idol_id="homura", monthly_points=80, monthly_period="2000-01")
    current = current_period_jst()
    apply_monthly_reset(user, db, current)
    assert user.idol_id == "homura"
