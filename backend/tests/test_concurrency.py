"""B2-1 回帰防止: 並行受領でのポイント整合・二重受領排他（QA Q-2 実証ケース）。

実スレッドで受領POSTを同時発火し、
  ①別shipment N並行 → 累計pt/月間ptの合計が各受領の総和と一致（ロストアップデート無し）
  ②同一shipment N並行 → 成功1件・残り400（二重受領=400が並行でも守られる）
を検証する。TestClient の sync エンドポイントは threadpool で実行されるため、
DB 層は実際に並行アクセスされる。
"""
import threading

from app.models import Device, Shipment, User


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


def _fire_concurrent(fn, n: int) -> list:
    """barrier で n スレッドを同時発火し、各戻り値を集める。"""
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


def test_concurrent_receive_different_shipments_no_lost_update(client, db, make_user):
    """50pt×10個の別shipmentを10並行受領 → 合計 500pt（欠損なし）。"""
    N = 10
    user = make_user()
    sids = [_make_shipment(db, user.id, 50) for _ in range(N)]
    hdr = client.auth_headers(user.id)

    codes = _fire_concurrent(
        lambda i: client.post(f"/api/shipments/{sids[i]}/receive", headers=hdr).status_code,
        N,
    )
    # 全件成功
    assert codes.count(200) == N, f"200が{codes.count(200)}件（期待{N}）: {codes}"

    # 永続DBの最終値を確認（別セッション断面をクリアして読み直す）
    db.rollback()
    u = db.get(User, user.id)
    db.refresh(u)
    assert u.points == 50 * N, f"points={u.points}（期待{50*N}）＝ロストアップデート"
    assert u.monthly_points == 50 * N, f"monthly_points={u.monthly_points}（期待{50*N}）"
    # 全shipmentが received
    received = (
        db.query(Shipment)
        .filter(Shipment.user_id == user.id, Shipment.status == "received")
        .count()
    )
    assert received == N


def test_concurrent_receive_same_shipment_single_success(client, db, make_user):
    """同一shipment(120pt)を10並行受領 → 成功1件・残り400、pt二重加算なし。"""
    N = 10
    user = make_user()
    sid = _make_shipment(db, user.id, 120)
    hdr = client.auth_headers(user.id)

    codes = _fire_concurrent(
        lambda i: client.post(f"/api/shipments/{sid}/receive", headers=hdr).status_code,
        N,
    )
    # 成功はちょうど1件、残りは全て 400（二重受領の排他）
    assert codes.count(200) == 1, f"200が{codes.count(200)}件（期待1）: {codes}"
    assert codes.count(400) == N - 1, f"400が{codes.count(400)}件（期待{N-1}）: {codes}"

    # ポイントは1回分（120）のみ。over-credit していない。
    db.rollback()
    u = db.get(User, user.id)
    db.refresh(u)
    assert u.points == 120, f"points={u.points}（期待120）＝二重加算"
    assert u.monthly_points == 120
