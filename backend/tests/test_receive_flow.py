"""受領→月間pt加算→特典付与→GET /users/{id} の一連を TestClient で検証する統合テスト。"""
from app.limited_idol import LIMITED_IDOL
from app.models import Device, Shipment
from app.services.monthly import current_period_jst


def _make_shipment(db, user_id: int, points: int, *, status: str = "issued") -> int:
    """指定ポイント相当のデバイス1台を積んだ未受領 shipment を作って id を返す。"""
    sh = Shipment(user_id=user_id, status=status)
    db.add(sh)
    db.flush()
    dev = Device(
        user_id=user_id,
        device_type_code="smartphone",
        label="スマートフォン",
        points=points,
        status="shipped",
        shipment_id=sh.id,
    )
    db.add(dev)
    db.commit()
    return sh.id


def test_receive_grants_single_threshold(client, db, make_user):
    user = make_user()
    sid = _make_shipment(db, user.id, 120)  # 0 → 120 で T1(100)
    res = client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    assert res.status_code == 200
    body = res.json()
    assert body["monthly_points"] == 120
    tiers = [g["tier"] for g in body["rewards_granted"]]
    assert tiers == ["T1"]
    assert body["rewards_granted"][0]["reward_type"] == "limited_idol"


def test_receive_grants_multiple_thresholds_at_once(client, db, make_user):
    user = make_user()
    # 単一受領で 0 → 600（T1・T2 同時付与）
    sid = _make_shipment(db, user.id, 600)
    res = client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    body = res.json()
    tiers = sorted(g["tier"] for g in body["rewards_granted"])
    assert tiers == ["T1", "T2"]
    assert body["monthly_points"] == 600


def test_double_receive_is_rejected(client, db, make_user):
    user = make_user()
    sid = _make_shipment(db, user.id, 120)
    first = client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    assert first.status_code == 200
    # 2回目は 400（受領済み）。特典の二重付与も起きない。
    second = client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    assert second.status_code == 400
    # GET で月間ptが二重加算されていないこと
    me = client.get(f"/api/users/{user.id}", headers=client.auth_headers(user.id)).json()
    assert me["monthly_points"] == 120
    assert me["rewards"]["tickets"] == 0


def test_get_user_detail_next_reward_and_status(client, db, make_user):
    user = make_user()
    sid = _make_shipment(db, user.id, 120)
    client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    me = client.get(f"/api/users/{user.id}", headers=client.auth_headers(user.id)).json()
    assert me["monthly_points"] == 120
    # 次特典は T2(500)・残り 380
    assert me["next_reward"] == {"tier": "T2", "threshold": 500, "remaining": 380}
    assert me["rewards"]["limited_idol_active"] is True
    assert me["rewards"]["special_visual"] is False
    assert me["monthly_period"] == current_period_jst()


def test_t3_tickets_accumulate(client, db, make_user):
    user = make_user()
    # 0 → 2000 で T1,T2,T3(1000),T3(2000) = 抽選券2枚
    sid = _make_shipment(db, user.id, 2000)
    body = client.post(
        f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id)
    ).json()
    tickets = [g for g in body["rewards_granted"] if g["reward_type"] == "handshake_ticket"]
    assert len(tickets) == 2
    me = client.get(f"/api/users/{user.id}", headers=client.auth_headers(user.id)).json()
    assert me["rewards"]["tickets"] == 2


def test_idor_other_user_detail_is_404(client, make_user):
    a = make_user()
    b = make_user()
    # b の通行証で a の詳細を要求 → 存在秘匿の 404
    res = client.get(f"/api/users/{a.id}", headers=client.auth_headers(b.id))
    assert res.status_code == 404


def test_special_visual_toggle_requires_t2(client, db, make_user):
    user = make_user()
    # T2 未獲得での special 切替 → 403
    res = client.patch(
        "/api/users/me",
        json={"active_visual": "special"},
        headers=client.auth_headers(user.id),
    )
    assert res.status_code == 403

    # T2 獲得（500pt 受領）後は切替成功、月をまたいでも恒久
    sid = _make_shipment(db, user.id, 500)
    client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    ok = client.patch(
        "/api/users/me",
        json={"active_visual": "special"},
        headers=client.auth_headers(user.id),
    )
    assert ok.status_code == 200
    assert ok.json()["active_visual"] == "special"


def test_limited_idol_selection_requires_t1(client, db, make_user):
    user = make_user()
    # T1 未獲得で限定推しを選ぶ → 403
    res = client.patch(
        "/api/users/me",
        json={"idol_id": LIMITED_IDOL["id"]},
        headers=client.auth_headers(user.id),
    )
    assert res.status_code == 403

    # T1 獲得（100pt）後は選択成功、prev_idol_id に元推しが退避される
    sid = _make_shipment(db, user.id, 120)
    client.post(f"/api/shipments/{sid}/receive", headers=client.auth_headers(user.id))
    ok = client.patch(
        "/api/users/me",
        json={"idol_id": LIMITED_IDOL["id"]},
        headers=client.auth_headers(user.id),
    )
    assert ok.status_code == 200
    assert ok.json()["idol_id"] == LIMITED_IDOL["id"]

    db.expire_all()
    refreshed = client.get(
        f"/api/users/{user.id}", headers=client.auth_headers(user.id)
    ).json()
    assert refreshed["idol_id"] == LIMITED_IDOL["id"]


def test_limited_idol_not_in_public_list_but_available_via_limited_endpoint(client):
    idols = client.get("/api/idols").json()
    ids = [i["id"] for i in idols]
    assert LIMITED_IDOL["id"] not in ids
    assert len(ids) == 6
    limited = client.get("/api/idols/limited").json()
    assert limited["id"] == LIMITED_IDOL["id"]
