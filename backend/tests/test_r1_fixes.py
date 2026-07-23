"""R-1 レビュー指摘（B-1/H-1/H-2/M-1）の回帰防止テスト（L-1）。"""
from types import SimpleNamespace

from app.limited_idol import LIMITED_IDOL
from app.models import Device, Idol, Shipment, User, UserReward
from app.services.monthly import current_period_jst
from app.services.rewards import grant_rewards


def _make_shipment(db, user_id: int, points: int) -> int:
    sh = Shipment(user_id=user_id, status="issued")
    db.add(sh)
    db.flush()
    db.add(
        Device(
            user_id=user_id,
            device_type_code="smartphone",
            label="スマートフォン",
            points=points,
            status="shipped",
            shipment_id=sh.id,
        )
    )
    db.commit()
    return sh.id


# =============================================================================
# B-1: 報酬 INSERT の UNIQUE 衝突が受領本体を巻き戻さない（savepoint 隔離）
# =============================================================================
def test_grant_rewards_duplicate_does_not_break_session(db, make_user):
    """同一(period,threshold)が既存でも grant_rewards はスキップし、セッションは無傷。"""
    user = make_user()
    period = current_period_jst()
    # 先に T1(100) を投入・commit（並行付与で先行したレコードを模す）
    db.add(
        UserReward(
            user_id=user.id, tier="T1", threshold=100,
            period=period, reward_type="limited_idol",
        )
    )
    db.commit()

    user.monthly_points = 0
    granted = grant_rewards(user, 0, 200, period, db)
    # 100 は既存のためスキップ。200 までに他の閾値は無い → 付与ゼロ
    assert granted == []
    # セッションは生きており後続の変更を commit できる（＝全体ロールバックしていない）
    user.points += 10
    db.commit()
    assert db.get(User, user.id).points == user.points


def test_receive_succeeds_even_if_reward_preexists(client, db, make_user):
    """事前に同月T1が存在しても、受領本体（pt加算・shipment受領化）は成功する。"""
    user = make_user()
    period = current_period_jst()
    db.add(
        UserReward(
            user_id=user.id, tier="T1", threshold=100,
            period=period, reward_type="limited_idol",
        )
    )
    db.commit()

    sid = _make_shipment(db, user.id, 120)
    res = client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    assert res.status_code == 200
    body = res.json()
    # 受領本体は成立（累計pt・月間pt加算）
    assert body["new_points"] == 120
    assert body["monthly_points"] == 120
    # T1 は重複のため再付与されない
    assert body["rewards_granted"] == []
    # shipment は受領済みへ
    sh = db.get(Shipment, sid)
    db.refresh(sh)
    assert sh.status == "received"


# =============================================================================
# H-1: 既存ユーザーの Google 再ログインで遅延リセットが適用される
# =============================================================================
def test_google_relogin_applies_monthly_reset(client, db, make_user, monkeypatch):
    """先月の月間ptを持つユーザーが再ログインすると 0 リセット済みで返る。"""
    user = make_user(google_sub="relogin-sub", monthly_points=300, monthly_period="2000-01")

    # Google 検証をスタブ化（実トークン検証はしない）
    fake_identity = SimpleNamespace(sub="relogin-sub", email="relogin@example.com")
    monkeypatch.setattr(
        "app.routers.auth.verify_google_credential", lambda credential: fake_identity
    )

    res = client.post("/api/auth/google", json={"credential": "dummy"})
    assert res.status_code == 200
    body = res.json()
    assert body["registered"] is True
    # 応答時点で当月にリセット済み（先月の 300 を持ち越さない）
    assert body["user"]["monthly_points"] == 0
    assert body["user"]["monthly_period"] == current_period_jst()
    # DB にも反映されている
    db.refresh(user)
    assert user.monthly_points == 0


# =============================================================================
# H-2: 過去の限定推し slug は選択不可（現在の LIMITED_IDOL のみ許可）
# =============================================================================
def test_past_limited_slug_selection_is_rejected(client, db, make_user):
    """過去運用の限定推し（別slug・is_limited=True）は T1保有でも 403。"""
    # 過去の限定推し行を用意（現在の LIMITED_IDOL とは別 slug）
    db.add(
        Idol(
            id="past_limited", name="先月の限定推し",
            theme_color="#123456", catchphrase="先月かぎり", is_limited=True,
        )
    )
    db.commit()

    user = make_user()
    # T1（当月）を獲得させる
    sid = _make_shipment(db, user.id, 120)
    client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))

    # 現在の限定推しは選べる
    ok = client.patch(
        "/api/users/me",
        json={"idol_id": LIMITED_IDOL["id"]},
        headers=client.auth_headers(user.id),
    )
    assert ok.status_code == 200

    # 過去の限定推し slug は 403（T1 を持っていても選べない）
    ng = client.patch(
        "/api/users/me",
        json={"idol_id": "past_limited"},
        headers=client.auth_headers(user.id),
    )
    assert ng.status_code == 403


# =============================================================================
# M-1: GET /api/idols/limited は認証必須＋当月T1保有者のみ（非保有は 404）
# =============================================================================
def test_limited_endpoint_requires_auth(client):
    """未認証は 401（秘匿特典のため）。"""
    res = client.get("/api/idols/limited")
    assert res.status_code == 401


def test_limited_endpoint_hidden_from_non_holder(client, make_user):
    """T1 非保有ユーザーには 404（存在秘匿）。"""
    user = make_user()
    res = client.get("/api/idols/limited", headers=client.auth_headers(user.id))
    assert res.status_code == 404


def test_limited_endpoint_visible_to_holder(client, db, make_user):
    """T1 当月保有ユーザーには 200 で限定推しを返す。"""
    user = make_user()
    sid = _make_shipment(db, user.id, 120)
    client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    res = client.get("/api/idols/limited", headers=client.auth_headers(user.id))
    assert res.status_code == 200
    assert res.json()["id"] == LIMITED_IDOL["id"]
