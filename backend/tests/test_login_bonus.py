"""毎日ログインボーナス（LB-1〜LB-5）の検証。

DoD（LB-6）の8観点をカバーする:
  ① 同日2回目は不付与（granted=false・ptが増えない）
  ② JST 日跨ぎで再付与される
  ③ 実スレッド10並行 claim で成功1件のみ（履歴1行・加算も1回分）
  ④ 付与値が 1・5・10 のいずれか
  ⑤ 累計 points とランクが変わらない
  ⑥ 月間ptが100を跨いだら T1 が付与される（user_rewards にレコード）
  ⑦ 月替わり直後の claim が新しい period に加算される
  ⑧ 未認証は 401

並行テストは既存 tests/test_concurrency.py の実スレッド方式を流用している。
"""
import threading
from datetime import datetime, timezone

from app.models import LoginBonus, User, UserReward
from app.services.login_bonus import (
    BONUS_POINT_CHOICES,
    awarded_points_of_day,
    claim,
    current_date_jst,
    current_keys_jst,
    is_available,
)
from app.services.monthly import current_period_jst


def _fire_concurrent(fn, n: int) -> list:
    """barrier で n スレッドを同時発火し、各戻り値を集める（test_concurrency.py と同方式）。"""
    results: list = [None] * n
    barrier = threading.Barrier(n)

    def worker(i: int):
        barrier.wait()
        results[i] = fn(i)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# ---------------------------------------------------------------- JST 日付


def test_current_date_jst_boundary():
    """JST の日付境界（UTC+9）で日付が切り替わること。"""
    # UTC 14:59:59 = JST 当日 23:59:59
    assert (
        current_date_jst(datetime(2026, 7, 25, 14, 59, 59, tzinfo=timezone.utc))
        == "2026-07-25"
    )
    # UTC 15:00:00 = JST 翌日 00:00:00
    assert (
        current_date_jst(datetime(2026, 7, 25, 15, 0, 0, tzinfo=timezone.utc))
        == "2026-07-26"
    )


def test_current_keys_jst_is_consistent_across_month_boundary():
    """period と bonus_date が同一時刻から導出され、月末境界でも食い違わないこと（R-1 M-2）。"""
    # UTC 2026-07-31 15:00 = JST 2026-08-01 00:00
    period, bonus_date = current_keys_jst(
        datetime(2026, 7, 31, 15, 0, 0, tzinfo=timezone.utc)
    )
    assert period == "2026-08"
    assert bonus_date == "2026-08-01"
    assert bonus_date.startswith(period)


# ---------------------------------------------------------------- ①②④⑤⑦


def test_claim_twice_same_day_grants_only_once(db, make_user):
    """① 同日2回目は不付与。月間ptも増えない。"""
    user = make_user()
    period = current_period_jst()

    first = claim(user, db, period, "2026-07-25")
    assert first["granted"] is True
    assert first["points"] in BONUS_POINT_CHOICES
    assert first["monthly_points"] == first["points"]

    second = claim(user, db, period, "2026-07-25")
    assert second["granted"] is False
    # 【M-1 対応】points は「その日に付与された pt」を返す（0 ではない）。
    # 付与そのものは1回きりで、月間ptは増えない。
    assert second["points"] == first["points"]
    # 2回目でも月間ptは1回分のまま
    assert second["monthly_points"] == first["points"]

    db.refresh(user)
    assert user.monthly_points == first["points"]
    assert db.query(LoginBonus).filter(LoginBonus.user_id == user.id).count() == 1


def test_claim_next_jst_day_grants_again(db, make_user):
    """② JST 日跨ぎ（bonus_date が変わる）で再付与される。"""
    user = make_user()
    period = current_period_jst()

    day1 = claim(user, db, period, "2026-07-25")
    day2 = claim(user, db, period, "2026-07-26")

    assert day1["granted"] is True
    assert day2["granted"] is True

    db.refresh(user)
    assert user.monthly_points == day1["points"] + day2["points"]
    assert db.query(LoginBonus).filter(LoginBonus.user_id == user.id).count() == 2


def test_granted_points_are_always_1_5_or_10(db, make_user):
    """④ 付与値は必ず 1 / 5 / 10 のいずれか（サーバー側抽選）。"""
    user = make_user()
    period = current_period_jst()

    total = 0
    for day in range(1, 31):
        result = claim(user, db, period, f"2026-07-{day:02d}")
        assert result["granted"] is True
        assert result["points"] in (1, 5, 10), f"想定外の付与pt: {result['points']}"
        total += result["points"]

    db.refresh(user)
    assert user.monthly_points == total


def test_claim_does_not_change_total_points_or_rank(db, make_user):
    """⑤ 累計 points とランクは変わらない（月間ptのみ加算）。"""
    user = make_user(points=42, rank=2)
    period = current_period_jst()

    result = claim(user, db, period, "2026-07-25")
    assert result["granted"] is True

    db.refresh(user)
    assert user.points == 42, "累計ptが変化している（月間ptのみ加算のはず）"
    assert user.rank == 2, "ランクが変化している（再計算しないはず）"
    assert user.monthly_points == result["points"]


def test_claim_after_month_rollover_counts_into_new_period(db, make_user):
    """⑦ 月替わり直後の claim は新しい period に加算される（先月ぶんに乗らない）。"""
    # 先月以前の期間で 300pt を持っている状態を作る
    user = make_user(monthly_points=300, monthly_period="2000-01")
    period = current_period_jst()

    result = claim(user, db, period, "2026-07-25")
    assert result["granted"] is True

    db.refresh(user)
    assert user.monthly_period == period
    # 300 に足されるのではなく、0 リセット後の付与ぶんのみ
    assert user.monthly_points == result["points"]
    assert result["monthly_points"] == result["points"]


# ---------------------------------------------------------------- ⑥ 特典跨ぎ


def test_claim_crossing_100_grants_t1(db, make_user):
    """⑥ 月間ptが100を跨いだら T1（期間限定推し）が付与される。"""
    period = current_period_jst()
    # 99pt からならどの抽選値（1/5/10）でも必ず 100 を跨ぐ
    user = make_user(monthly_points=99, monthly_period=period)

    result = claim(user, db, period, "2026-07-25")
    assert result["granted"] is True
    assert result["monthly_points"] >= 100

    tiers = [g["tier"] for g in result["rewards_granted"]]
    assert "T1" in tiers, f"T1 が付与されていない: {result['rewards_granted']}"

    reward = (
        db.query(UserReward)
        .filter(
            UserReward.user_id == user.id,
            UserReward.threshold == 100,
            UserReward.period == period,
        )
        .first()
    )
    assert reward is not None
    assert reward.reward_type == "limited_idol"


# ---------------------------------------------------------------- API


def test_claim_requires_authentication(client):
    """⑧ 未認証は 401（pt という価値を付与する API のため必須）。"""
    res = client.post("/api/login-bonus/claim")
    assert res.status_code == 401


def test_claim_api_first_and_second_call(client, db, make_user):
    """API: 初回 200/granted=true、同日2回目 200/granted=false（エラーにしない）。"""
    user = make_user()
    hdr = client.auth_headers(user.id)

    first = client.post("/api/login-bonus/claim", headers=hdr)
    assert first.status_code == 200
    body1 = first.json()
    assert body1["granted"] is True
    assert body1["points"] in (1, 5, 10)
    assert body1["monthly_points"] == body1["points"]
    assert body1["next_reward"]["threshold"] == 100

    second = client.post("/api/login-bonus/claim", headers=hdr)
    assert second.status_code == 200
    body2 = second.json()
    assert body2["granted"] is False
    # 【M-1 対応】その日に付与された pt を返す（再送での復元に使う）。月間ptは増えない。
    assert body2["points"] == body1["points"]
    assert body2["monthly_points"] == body1["points"]


def test_user_detail_exposes_login_bonus_available(client, db, make_user):
    """LB-5: GET /api/users/{id} の login_bonus_available が受領前後で切り替わる。"""
    user = make_user()
    hdr = client.auth_headers(user.id)

    before = client.get(f"/api/users/{user.id}", headers=hdr)
    assert before.status_code == 200
    assert before.json()["login_bonus_available"] is True

    assert client.post("/api/login-bonus/claim", headers=hdr).status_code == 200

    after = client.get(f"/api/users/{user.id}", headers=hdr)
    assert after.status_code == 200
    assert after.json()["login_bonus_available"] is False

    # 既存フィールドが消えていないこと（後方互換の追加のみ）
    body = after.json()
    for key in ("id", "nickname", "idol_id", "points", "rank", "monthly_points", "rewards"):
        assert key in body


def test_login_bonus_available_is_scoped_to_owner(client, make_user):
    """他人の受領状況は観測できない（既存の本人スコープ 404 を維持）。"""
    owner = make_user()
    other = make_user()
    res = client.get(f"/api/users/{owner.id}", headers=client.auth_headers(other.id))
    assert res.status_code == 404


# ---------------------------------------------------------------- ③ 並行


def test_concurrent_claim_grants_only_once(client, db, make_user):
    """③ 実スレッド10並行 claim → 成功（granted=true）は1件のみ・履歴も1行。

    【R-3 M-2・PostgreSQL でも成立する根拠】本テストは SQLite でのみ実行している
    （ローカル/CI に PostgreSQL 環境が無いため。同条件は前スプリントの QA_Q-2 も同様）。
    多重付与を止めているのは方言依存の仕組みではなく、①`UNIQUE(user_id, bonus_date)` の
    一意制約 ②`db.begin_nested()` の SAVEPOINT ③`SET monthly_points = monthly_points + :v`
    の単一 UPDATE の3点で、いずれも標準 SQL の機能。PostgreSQL では同一キーへの並行 INSERT が
    先行トランザクションの commit までブロックされたうえで unique_violation となり、SAVEPOINT が
    あればアボートしたトランザクションを復帰できる（PostgreSQL では SAVEPOINT が必須で、
    実装はそれを満たしている）。pt 加算も行ロックで直列化される。よって本テストが
    SQLite で green であれば PostgreSQL でも同じ結論になる。後任は同じ検証を繰り返さなくてよい。
    """
    N = 10
    user = make_user()
    hdr = client.auth_headers(user.id)

    responses = _fire_concurrent(
        lambda i: client.post("/api/login-bonus/claim", headers=hdr),
        N,
    )

    codes = [r.status_code for r in responses]
    assert codes.count(200) == N, f"200が{codes.count(200)}件（期待{N}）: {codes}"

    bodies = [r.json() for r in responses]
    granted = [b for b in bodies if b["granted"]]
    assert len(granted) == 1, f"granted=true が{len(granted)}件（期待1）"

    awarded = granted[0]["points"]
    assert awarded in (1, 5, 10)

    # 履歴は1行だけ・月間ptの加算も1回分
    db.rollback()
    assert db.query(LoginBonus).filter(LoginBonus.user_id == user.id).count() == 1
    u = db.get(User, user.id)
    db.refresh(u)
    assert u.monthly_points == awarded, f"monthly_points={u.monthly_points}（期待{awarded}）＝多重付与"
    assert u.points == 0, "累計ptが加算されている（月間ptのみのはず）"


# ------------------------------------------------- QA_Q-6 M-1（再送での復元）


def test_resend_returns_awarded_points_of_the_day(db, make_user):
    """M-1: 本日受領済みの応答でも「その日に付与された pt」が返る（再送で復元できる）。

    タイムアウトしたクライアントが再送したとき、0 が返ると「いくら入ったのか」を
    復元できず、結果画面も特典解放の告知も出せなくなる（＝M-1 の本体）。
    """
    user = make_user()
    period = current_period_jst()

    first = claim(user, db, period, "2026-07-25")
    assert first["granted"] is True
    awarded = first["points"]
    assert awarded in (1, 5, 10)

    resent = claim(user, db, period, "2026-07-25")
    assert resent["granted"] is False, "再送で二重付与されている"
    assert resent["points"] == awarded, "再送で当日の付与pt が復元できない（M-1 再発）"
    assert resent["monthly_points"] == first["monthly_points"]

    db.refresh(user)
    assert user.monthly_points == awarded
    assert db.query(LoginBonus).filter(LoginBonus.user_id == user.id).count() == 1


def test_claim_is_idempotent_on_repeated_resend(client, db, make_user):
    """M-1: API を何度再送しても付与は1回きりで、毎回同じ付与pt が返る（冪等性の保証）。"""
    user = make_user()
    hdr = client.auth_headers(user.id)

    first = client.post("/api/login-bonus/claim", headers=hdr).json()
    assert first["granted"] is True
    awarded = first["points"]

    for i in range(5):
        body = client.post("/api/login-bonus/claim", headers=hdr).json()
        assert body["granted"] is False, f"{i + 2}回目で二重付与されている"
        assert body["points"] == awarded, f"{i + 2}回目の points が {body['points']}（期待{awarded}）"
        assert body["monthly_points"] == awarded

    db.rollback()
    assert db.query(LoginBonus).filter(LoginBonus.user_id == user.id).count() == 1
    u = db.get(User, user.id)
    db.refresh(u)
    assert u.monthly_points == awarded
    assert u.points == 0, "累計ptが動いている"


def test_resend_after_timeout_can_recover_reward_unlock(client, db, make_user):
    """M-1 再現ケース: 1回目がタイムアウト扱いでも、再送＋rewards 差分で特典解放を復元できる。

    再送レスポンス自体に `rewards_granted` は載らない（付与は1回目で済んでいるため）。
    フロントは「オーバーレイを開く前の rewards」と「claim 後に再取得した rewards」の
    差分で解放を検知する。ここではその材料（付与pt・月間pt・rewards の遷移）が
    サーバーから確実に取れることを保証する。
    """
    period = current_period_jst()
    user = make_user(monthly_points=99, monthly_period=period)
    hdr = client.auth_headers(user.id)

    # オーバーレイを開く直前のスナップショット（フロントが保持する値に相当）
    before = client.get(f"/api/users/{user.id}", headers=hdr).json()
    assert before["rewards"]["limited_idol_active"] is False
    assert before["login_bonus_available"] is True

    # 1回目（クライアントから見ればタイムアウトしてレスポンスを取り逃した想定）
    lost = client.post("/api/login-bonus/claim", headers=hdr).json()
    assert lost["granted"] is True
    awarded = lost["points"]
    assert [g["tier"] for g in lost["rewards_granted"]] == ["T1"]

    # 再送（フロントが復元のために1回だけ投げ直す）
    resent = client.post("/api/login-bonus/claim", headers=hdr).json()
    assert resent["granted"] is False
    assert resent["points"] == awarded, "再送で付与pt が復元できない"
    assert resent["monthly_points"] == 99 + awarded
    assert resent["rewards_granted"] == [], "再送で特典が二重付与されている"

    # 差分検知の材料: rewards が false → true へ遷移していること
    after = client.get(f"/api/users/{user.id}", headers=hdr).json()
    assert after["rewards"]["limited_idol_active"] is True
    assert after["monthly_points"] == 99 + awarded
    assert after["login_bonus_available"] is False

    # 特典レコードは1件だけ
    db.rollback()
    assert (
        db.query(UserReward)
        .filter(UserReward.user_id == user.id, UserReward.threshold == 100)
        .count()
        == 1
    )


def test_awarded_points_of_day_helper(db, make_user):
    """`awarded_points_of_day`: 未受領は 0、受領後はその日の付与額、別日は 0。"""
    user = make_user()
    period = current_period_jst()

    assert awarded_points_of_day(db, user.id, "2026-07-25") == 0
    result = claim(user, db, period, "2026-07-25")
    assert awarded_points_of_day(db, user.id, "2026-07-25") == result["points"]
    assert awarded_points_of_day(db, user.id, "2026-07-26") == 0


def test_is_available_helper(db, make_user):
    """is_available: 未受領なら True、受領後は False。"""
    user = make_user()
    period = current_period_jst()

    assert is_available(db, user.id, "2026-07-25") is True
    claim(user, db, period, "2026-07-25")
    assert is_available(db, user.id, "2026-07-25") is False
    # 別の日はまだ受け取れる
    assert is_available(db, user.id, "2026-07-26") is True
