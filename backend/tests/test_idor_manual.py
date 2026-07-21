"""IDOR / 認可越境の手動ハーネス（rinaresu 用）。

【目的】りなれす API の認証・認可を、実 API と同じロジック（app.deps.get_current_user /
各ルーター）を叩いて検証する。

【方式Bへの移行後の期待（本ファイルは「攻撃を弾く」向きに反転済み）】
- 認証は「アプリ独自セッション通行証（署名付き JWT）」。`Authorization: Bearer <通行証>` を要求する。
- 旧 `X-User-Id` ヘッダーの信用は撤廃済み（F-1）。差し替えても通らない。
- ユーザー系 GET・伝票PDF は認証必須かつ本人スコープ（F-2 / F-3）。
  → 認証なし=401、他人のリソース=404（存在秘匿）、本人=200。

【隔離】実 dev DB（backend/data/rinaresu.db）を汚さないよう、テスト専用の一時 SQLite に
get_db を差し替える。startup の seed_all（実エンジン依存）は走らせないため
TestClient を context manager では使わない。

実行:
    cd backend && venv/bin/python -m pytest tests/test_idor_manual.py -v
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Device, Idol, Shipment, User
from app.services.session_token import issue_session_token

# --- 一時 DB を用意し、get_db を差し替える ------------------------------------
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
_engine = create_engine(
    f"sqlite:///{Path(_tmp.name).as_posix()}",
    connect_args={"check_same_thread": False},
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)

# 本人の伝票PDF取得(200)を検証するため、実在するダミー PDF ファイルを用意する
_pdf_tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
_pdf_tmp.write(b"%PDF-1.4\n%dummy slip for tests\n")
_pdf_tmp.close()
_PDF_PATH = _pdf_tmp.name


def _override_get_db():
    db = _TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
# startup を発火させない素の TestClient（startup=seed_all は実エンジンを触るため）
client = TestClient(app)


# --- 2 ユーザー（A/B）と A の資産を仕込む -------------------------------------
USER_A_ID = 1  # 被害者（元・なりすまし対象）
USER_B_ID = 2  # 攻撃者


@pytest.fixture(scope="module", autouse=True)
def seeded():
    Base.metadata.create_all(bind=_engine)
    db = _TestingSession()
    try:
        db.add(Idol(id="homura", name="金城ほむら", theme_color="#f2b705", catchphrase="x"))
        db.add(User(id=USER_A_ID, temp_id="PID-0001", google_sub="sub-A",
                    email="victim@example.com", nickname="被害者A", idol_id="homura",
                    points=120, rank=2))
        db.add(User(id=USER_B_ID, temp_id="PID-0002", google_sub="sub-B",
                    email="attacker@example.com", nickname="攻撃者B", idol_id="homura",
                    points=0, rank=1))
        db.add(Device(id=1, user_id=USER_A_ID, device_type_code="smartphone",
                      label="スマートフォン", points=10, status="shipped", shipment_id=1))
        # A の伝票（PDF 実ファイル付き）。owner の 200 と他人の 404 を切り分けるため。
        db.add(Shipment(id=1, user_id=USER_A_ID, status="issued", pdf_path=_PDF_PATH))
        db.commit()
    finally:
        db.close()
    yield


def _bearer(uid: int) -> dict:
    """有効なセッション通行証を Authorization: Bearer で返す。"""
    return {"Authorization": f"Bearer {issue_session_token(uid)}"}


# =============================================================================
# ① なりすまし（F-1）: X-User-Id 差し替えはもう通らない。通行証が必須。
# =============================================================================
def test_no_auth_is_rejected():
    """認証ヘッダー無しの保護 EP は 401（従来 200 でなりすませていた地点）。"""
    res = client.get("/api/devices")
    print("\n[F-1] GET /api/devices (no auth) ->", res.status_code)
    assert res.status_code == 401


def test_legacy_x_user_id_header_is_ignored():
    """旧 X-User-Id を付けても認証は通らない（信用撤廃済み）→ 401。"""
    res = client.get("/api/devices", headers={"X-User-Id": str(USER_A_ID)})
    print("\n[F-1] GET /api/devices with X-User-Id:1 (no Bearer) ->", res.status_code)
    assert res.status_code == 401


def test_valid_token_allows_own_access():
    """有効な自分の通行証でのみ保護 EP が通る → 200。"""
    res = client.get("/api/devices", headers=_bearer(USER_A_ID))
    print("\n[F-1] GET /api/devices with A's token ->", res.status_code)
    assert res.status_code == 200


def test_patch_me_requires_token():
    """PATCH /users/me は通行証必須。無しは 401、A の通行証で 200。"""
    res_no = client.patch("/api/users/me", json={"idol_id": "homura"})
    print("\n[F-1] PATCH /api/users/me (no auth) ->", res_no.status_code)
    assert res_no.status_code == 401

    res_ok = client.patch("/api/users/me", headers=_bearer(USER_A_ID), json={"idol_id": "homura"})
    print("[F-1] PATCH /api/users/me with A's token ->", res_ok.status_code)
    assert res_ok.status_code == 200


# =============================================================================
# ② ユーザー系 GET（F-2）: 認証必須＋本人スコープ。
# =============================================================================
def test_user_history_requires_auth():
    """GET /api/users/{id}/history は認証必須 → 認証なしは 401（従来 200 だった IDOR 地点）。"""
    res = client.get(f"/api/users/{USER_A_ID}/history")
    print("\n[F-2] GET /api/users/1/history (no auth) ->", res.status_code)
    assert res.status_code == 401


def test_user_history_other_user_is_hidden():
    """B の通行証で A の履歴は取れない → 404（存在秘匿）。"""
    res = client.get(f"/api/users/{USER_A_ID}/history", headers=_bearer(USER_B_ID))
    print("[F-2] GET /api/users/1/history as B ->", res.status_code)
    assert res.status_code == 404


def test_user_history_self_ok():
    """本人（A）は自分の履歴を取得できる → 200。"""
    res = client.get(f"/api/users/{USER_A_ID}/history", headers=_bearer(USER_A_ID))
    print("[F-2] GET /api/users/1/history as A ->", res.status_code)
    assert res.status_code == 200
    body = res.json()
    assert "devices" in body and "shipments" in body


def test_user_detail_requires_auth_and_is_self_only():
    """GET /api/users/{id}: 認証なし=401 / 他人=404 / 本人=200（email はここでのみ露出）。"""
    res_no = client.get(f"/api/users/{USER_A_ID}")
    print("\n[F-2] GET /api/users/1 (no auth) ->", res_no.status_code)
    assert res_no.status_code == 401

    res_other = client.get(f"/api/users/{USER_A_ID}", headers=_bearer(USER_B_ID))
    print("[F-2] GET /api/users/1 as B ->", res_other.status_code)
    assert res_other.status_code == 404

    res_self = client.get(f"/api/users/{USER_A_ID}", headers=_bearer(USER_A_ID))
    print("[F-2] GET /api/users/1 as A ->", res_self.status_code)
    assert res_self.status_code == 200
    assert res_self.json().get("email") == "victim@example.com"


def test_user_comment_is_self_only():
    """GET /api/users/{id}/comment: 認証なし=401 / 他人=404 / 本人=200。"""
    assert client.get(f"/api/users/{USER_A_ID}/comment").status_code == 401
    assert client.get(f"/api/users/{USER_A_ID}/comment", headers=_bearer(USER_B_ID)).status_code == 404
    assert client.get(f"/api/users/{USER_A_ID}/comment", headers=_bearer(USER_A_ID)).status_code == 200


def test_user_list_endpoint_is_removed():
    """旧 GET /api/users（全 PII 列挙）は撤廃済み。POST のみ残るため GET は 405。"""
    res = client.get("/api/users")
    print("\n[F-2] GET /api/users ->", res.status_code)
    assert res.status_code == 405


# =============================================================================
# ③ 伝票PDF（F-3）: 認証必須＋本人スコープ。
# =============================================================================
def test_pdf_requires_auth():
    """GET /api/shipments/{id}/pdf は認証必須 → 認証なしは 401。"""
    res = client.get("/api/shipments/1/pdf")
    print("\n[F-3] GET /api/shipments/1/pdf (no auth) ->", res.status_code)
    assert res.status_code == 401


def test_pdf_other_user_is_hidden():
    """B の通行証で A の伝票PDFは取れない → 404（存在秘匿）。"""
    res = client.get("/api/shipments/1/pdf", headers=_bearer(USER_B_ID))
    print("[F-3] GET /api/shipments/1/pdf as B ->", res.status_code)
    assert res.status_code == 404


def test_pdf_self_ok():
    """本人（A）は自分の伝票PDFを取得できる → 200（application/pdf）。"""
    res = client.get("/api/shipments/1/pdf", headers=_bearer(USER_A_ID))
    print("[F-3] GET /api/shipments/1/pdf as A ->", res.status_code)
    assert res.status_code == 200
    assert res.headers.get("content-type") == "application/pdf"


# =============================================================================
# ④ 対照: owner スコープの操作系は従来どおり他人を弾く（防御が維持されている）
# =============================================================================
def test_receive_others_shipment_is_blocked():
    """B が A の送付を受領しようとすると 404（存在秘匿）。"""
    res = client.post("/api/shipments/1/receive", headers=_bearer(USER_B_ID))
    print("\n[対照] POST /api/shipments/1/receive as B ->", res.status_code)
    assert res.status_code == 404


def test_share_text_others_shipment_is_blocked():
    """B が A の送付の share-text を取ろうとすると 404。"""
    res = client.get("/api/shipments/1/share-text", headers=_bearer(USER_B_ID))
    print("[対照] GET /api/shipments/1/share-text as B ->", res.status_code)
    assert res.status_code == 404


# =============================================================================
# ⑤ 不正・欠落・失効した通行証の扱い（すべて fail-closed）
# =============================================================================
@pytest.mark.parametrize("headers", [
    {},                                          # 認証なし
    {"Authorization": "Bearer not-a-jwt"},       # 壊れたトークン
    {"Authorization": "garbage"},                 # Bearer 形式でない
    {"X-User-Id": str(USER_A_ID)},                # 旧ヘッダーのみ（無効）
])
def test_invalid_credentials_rejected(headers):
    """保護 EP は、欠落/不正/旧ヘッダーのいずれも 401 で弾く。"""
    res = client.get("/api/devices", headers=headers)
    print(f"\n[資格チェック] GET /api/devices headers={headers} ->", res.status_code)
    assert res.status_code == 401


def test_token_for_nonexistent_user_rejected():
    """通行証は妥当でも該当ユーザーが存在しなければ 401。"""
    res = client.get("/api/devices", headers=_bearer(999999))
    print("\n[資格チェック] GET /api/devices with token for id=999999 ->", res.status_code)
    assert res.status_code == 401
