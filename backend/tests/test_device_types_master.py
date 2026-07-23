"""
device_types マスタ（21種・リチウム含有量ベース pt）の upsert 検証。

- 新規DB: seed で 21 種そろい、案B の代表 pt が入る。
- 既存DB（旧6種の状態を再現）: upsert で 21 種化し、既存行の pt が新方式へ更新される
  （例: smartphone 17→12）。既存 code は insert ではなく update される（重複しない）。
- 冪等性: 複数回 seed しても 21 種のまま・pt も変わらない。

conftest の autouse fixture が各テスト前に DB を drop→再作成→seed するため、
各テストは「21 種が seed 済み」の状態から始まる。
"""
from app.models import DeviceType
from app.seed import DEVICE_TYPES, _seed_device_types

# 旧マスタ（6種・重量ベース pt）。既存DB再現用。
_OLD_DEVICE_TYPES = [
    {"code": "smartphone", "label": "スマートフォン", "weight_g": 170, "points": 17},
    {"code": "feature_phone", "label": "ガラケー", "weight_g": 100, "points": 10},
    {"code": "tablet", "label": "タブレット", "weight_g": 450, "points": 45},
    {"code": "camera", "label": "デジタルカメラ", "weight_g": 300, "points": 30},
    {"code": "portable_game", "label": "携帯ゲーム機", "weight_g": 250, "points": 25},
    {"code": "other", "label": "その他小型家電", "weight_g": 100, "points": 10},
]

# 旧6コード（互換維持が必須）
_LEGACY_CODES = {
    "smartphone",
    "feature_phone",
    "tablet",
    "camera",
    "portable_game",
    "other",
}


def _reset_to_old_six(db) -> None:
    """device_types を旧6種だけの状態にする（既存DB再現）。"""
    db.query(DeviceType).delete()
    for dt in _OLD_DEVICE_TYPES:
        db.add(DeviceType(**dt))
    db.commit()


def test_new_db_has_21_types(db):
    """新規DB（conftest seed 済み）は 21 種そろう。"""
    types = db.query(DeviceType).all()
    assert len(types) == 21
    # DEVICE_TYPES と DB が一致する（code 集合）
    assert {t.code for t in types} == {dt["code"] for dt in DEVICE_TYPES}


def test_new_db_representative_points(db):
    """案B の代表 pt がマスタに入っている。"""
    pt = {t.code: t.points for t in db.query(DeviceType).all()}
    assert pt["smartphone"] == 12
    assert pt["feature_phone"] == 4
    assert pt["tablet"] == 22
    assert pt["camera"] == 4
    assert pt["portable_game"] == 13
    assert pt["other"] == 5
    # 新カテゴリの代表値（小型=最低1pt / 高Li機器=高pt）
    assert pt["wireless_earbuds"] == 1
    assert pt["mobile_battery"] == 31
    assert pt["laptop"] == 42
    assert pt["power_tool"] == 60


def test_legacy_codes_preserved(db):
    """旧6コードは code がすべて維持される（外部キー互換）。"""
    codes = {t.code for t in db.query(DeviceType).all()}
    assert _LEGACY_CODES.issubset(codes)


def test_min_one_point_no_zero(db):
    """最低1pt保証: pt が 0 のカテゴリは無い。"""
    assert all(t.points >= 1 for t in db.query(DeviceType).all())


def test_upsert_from_old_six_db(db):
    """既存DB（旧6種）→ upsert で 21 種化し、既存行 pt が新方式へ更新される。"""
    _reset_to_old_six(db)
    assert db.query(DeviceType).count() == 6
    assert db.get(DeviceType, "smartphone").points == 17  # 旧値

    # upsert 実行
    _seed_device_types(db)
    db.commit()

    types = db.query(DeviceType).all()
    # 6（更新）+ 15（新規）= 21。既存 code が insert されて重複していないこと
    assert len(types) == 21
    assert {t.code for t in types} == {dt["code"] for dt in DEVICE_TYPES}

    # 既存行が update されている（17→12）
    assert db.get(DeviceType, "smartphone").points == 12
    assert db.get(DeviceType, "feature_phone").points == 4
    assert db.get(DeviceType, "tablet").points == 22
    # other は label も刷新される
    other = db.get(DeviceType, "other")
    assert other.points == 5
    assert other.label == "その他小型充電式機器"
    # 新カテゴリが insert されている
    assert db.get(DeviceType, "power_tool") is not None
    assert db.get(DeviceType, "power_tool").points == 60


def test_upsert_is_idempotent(db):
    """複数回 upsert しても 21 種のまま・pt も安定（重複 insert しない）。"""
    _seed_device_types(db)
    db.commit()
    _seed_device_types(db)
    db.commit()

    types = db.query(DeviceType).all()
    assert len(types) == 21
    # code の重複が無い（PK 制約でも担保されるが集合で確認）
    codes = [t.code for t in types]
    assert len(codes) == len(set(codes))
    assert db.get(DeviceType, "smartphone").points == 12
