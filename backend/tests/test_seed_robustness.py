"""seed の堅牢性（QA_Q-8 M-1/m-1/m-2/m-3・REVIEW_R-4 M-1）の検証。

観点:
  ① 運営が limited_idol.py を書き間違えても **起動は必ず成功**し DEFAULT に落ちる（Q-8 M-1）
  ② タイポが **無言で無視されない**（警告ログが出る・新規/既存 slug の両パスで同じ挙動）
  ③ comments が空配列・不正ランク・非文字列でも **中立9文に落ちる**（Q-8 m-1・m-2）
  ④ 過去 slug の限定推しにも中立9文＋DEFAULT が行き渡る（Q-8 m-3）
  ⑤ 複数プロセスが同時に seed_all しても **落ちず・冪等**（R-4 M-1）
"""
import logging
import threading

import pytest

from app.database import SessionLocal
from app.limited_idol import LIMITED_IDOL
from app.models import Idol, IdolComment, IdolLoginLine
from app.seed import (
    DEFAULT_LOGIN_LINES,
    NEUTRAL_COMMENT_TEMPLATES,
    _normalize_comments,
    _normalize_login_lines,
    seed_all,
)

LINE_FIELDS = tuple(DEFAULT_LOGIN_LINES)
NEUTRAL_SET = {t for ts in NEUTRAL_COMMENT_TEMPLATES.values() for t in ts}


def _comments_of(db, slug: str) -> set[str]:
    return {
        c.template for c in db.query(IdolComment).filter(IdolComment.idol_id == slug).all()
    }


# ---------------------------------------------------------------- ① 起動が落ちない


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"greet1": "{nickname}、やあ"}, id="キー欠落（1つだけ書いた）"),
        pytest.param(
            {
                "greet_1": "{nickname}、やあ",  # タイポ
                "greet2": "テストの気持ち",
                "envelope": "はい、これ",
                "result1": "{points}ptだよ",
                "result2": "また明日",
                "already": "もう渡したよ",
            },
            id="キー名のタイポ（未知キー＋必須キー欠落）",
        ),
        pytest.param({}, id="空 dict"),
        pytest.param(None, id="None"),
        pytest.param("ぜんぶ文字列で書いてしまった", id="dict ではない"),
        pytest.param({"greet1": "", "greet2": "   "}, id="空文字・空白のみ"),
        pytest.param({"greet1": 12345}, id="非文字列"),
    ],
)
def test_broken_login_lines_never_break_startup(db, monkeypatch, broken):
    """① login_lines がどう壊れていても seed_all は成功し、欠落は DEFAULT で補完される。

    従来は「キーを1つ落とす」「キー名をタイポする」で IntegrityError / TypeError が出て
    on_startup が失敗＝**サービス起動不能**だった（Q-8 M-1）。
    """
    monkeypatch.setitem(LIMITED_IDOL, "id", "brandnew")
    monkeypatch.setitem(LIMITED_IDOL, "login_lines", broken)

    seed_all(db)  # 例外が出ないこと自体が検証

    row = db.get(IdolLoginLine, "brandnew")
    assert row is not None
    for field in LINE_FIELDS:
        value = getattr(row, field)
        assert isinstance(value, str) and value.strip()
        # 壊れていた（＝正しい str が無い）フィールドは DEFAULT で埋まる
        given = broken.get(field) if isinstance(broken, dict) else None
        if not (isinstance(given, str) and given.strip()):
            assert value == DEFAULT_LOGIN_LINES[field]


def test_typo_is_warned_not_silently_ignored(db, monkeypatch, caplog):
    """② タイポが無言で無視されない（運営が気づける形＝警告ログ）。"""
    monkeypatch.setitem(LIMITED_IDOL, "id", "brandnew")
    monkeypatch.setitem(
        LIMITED_IDOL,
        "login_lines",
        {**DEFAULT_LOGIN_LINES, "greet_1": "{nickname}、タイポ版"},
    )

    with caplog.at_level(logging.WARNING, logger="app.seed"):
        seed_all(db)

    assert "未知のキー" in caplog.text, caplog.text
    assert "greet_1" in caplog.text


def test_typo_behaves_the_same_for_new_and_existing_slug(db, monkeypatch, caplog):
    """② 同じタイポが「新規 slug は即死／既存 slug は無言の無視」に分かれないこと。

    従来は insert パス（`**lines` 展開）と update パス（`setattr`）で挙動が非対称だった。
    """
    typo = {**DEFAULT_LOGIN_LINES, "greet_1": "{nickname}、タイポ版"}

    # 既存 slug（rinaresu は seed 済み）に同じタイポを入れて再起動
    monkeypatch.setitem(LIMITED_IDOL, "login_lines", typo)
    with caplog.at_level(logging.WARNING, logger="app.seed"):
        seed_all(db)
    assert "greet_1" in caplog.text, "既存 slug でタイポが無言で無視されている"

    row = db.get(IdolLoginLine, LIMITED_IDOL["id"])
    # 未知キーは反映されず、正規の greet1 は DEFAULT（typo の元 dict の値）になる
    assert row.greet1 == DEFAULT_LOGIN_LINES["greet1"]


# ---------------------------------------------------------------- ③ comments の検証


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({1: [], 2: [], 3: []}, id="空配列（truthy で or を素通りしていた）"),
        pytest.param({1: ["{nickname}、やあ"], 4: ["死にデータ"]}, id="ランク4・2と3が0件"),
        pytest.param({1: [12345], 2: [12345], 3: [12345]}, id="数値（PostgreSQLで型エラー）"),
        pytest.param({1: ["a"], 2: ["b"]}, id="ランク3が欠落"),
        pytest.param({1: "文字列", 2: "文字列", 3: "文字列"}, id="リストではない"),
        pytest.param([], id="dict ではない"),
        pytest.param({}, id="空 dict"),
        pytest.param(None, id="None"),
    ],
)
def test_broken_comments_fall_back_to_neutral_nine(db, monkeypatch, broken):
    """③ comments が空・不正でも中立9文に落ちる（フォールバック1文固定にならない）。"""
    monkeypatch.setitem(LIMITED_IDOL, "id", "brandnew")
    monkeypatch.setitem(LIMITED_IDOL, "comments", broken)

    seed_all(db)

    templates = _comments_of(db, "brandnew")
    assert templates == NEUTRAL_SET
    assert len(templates) == 9
    # ランク1〜3 のどれも0件にならない
    for rank in (1, 2, 3):
        assert (
            db.query(IdolComment)
            .filter(IdolComment.idol_id == "brandnew", IdolComment.rank == rank)
            .count()
            == 3
        )


def test_invalid_rank_is_not_persisted(db, monkeypatch):
    """③ rank=4 のような死にデータが DB に入らない。"""
    monkeypatch.setitem(LIMITED_IDOL, "id", "brandnew")
    monkeypatch.setitem(
        LIMITED_IDOL, "comments", {1: ["{nickname}、やあ"], 4: ["死にデータ"]}
    )

    seed_all(db)

    assert (
        db.query(IdolComment)
        .filter(IdolComment.idol_id == "brandnew", IdolComment.rank == 4)
        .count()
        == 0
    )
    assert "死にデータ" not in _comments_of(db, "brandnew")


def test_normalizers_are_pure_helpers():
    """③ 正規化関数そのものの契約（DB なしで確認できる範囲）。"""
    assert _normalize_login_lines("x", None) == DEFAULT_LOGIN_LINES
    assert _normalize_login_lines("x", {"greet2": "オリジナル"})["greet2"] == "オリジナル"
    assert (
        _normalize_login_lines("x", {"greet2": "オリジナル"})["greet1"]
        == DEFAULT_LOGIN_LINES["greet1"]
    )
    assert _normalize_comments("x", {1: [], 2: [], 3: []}, NEUTRAL_COMMENT_TEMPLATES) == (
        NEUTRAL_COMMENT_TEMPLATES
    )
    ok = {1: ["a"], 2: ["b"], 3: ["c"]}
    assert _normalize_comments("x", ok, NEUTRAL_COMMENT_TEMPLATES) == ok


# ---------------------------------------------------------------- ④ 過去 slug


def test_legacy_limited_idol_gets_neutral_voice(db):
    """④ 過去 slug の限定推しにも中立9文＋DEFAULT 文言が行き渡る（Q-8 m-3）。

    月中差し替え（2026-07-23 の seira → rinaresu）で取り残されたユーザーの吹き出しが
    「{nickname}、いつもありがとう！」1文固定のままだった問題。
    """
    db.add(
        Idol(
            id="seira",
            name="星宮セイラ",
            theme_color="#aabbcc",
            catchphrase="旧限定推し",
            is_limited=True,
        )
    )
    db.commit()
    assert _comments_of(db, "seira") == set()

    seed_all(db)

    assert _comments_of(db, "seira") == NEUTRAL_SET
    row = db.get(IdolLoginLine, "seira")
    assert row is not None
    for field in LINE_FIELDS:
        assert getattr(row, field) == DEFAULT_LOGIN_LINES[field]


def test_legacy_limited_idol_existing_voice_is_preserved(db):
    """④ 過去 slug が既に文言を持っている場合は上書きしない（D-4 §6.3）。"""
    db.add(
        Idol(id="seira", name="星宮セイラ", theme_color="#aabbcc",
             catchphrase="旧限定推し", is_limited=True)
    )
    db.flush()
    db.add(IdolComment(idol_id="seira", rank=1, template="{nickname}、セイラだよ"))
    db.add(IdolLoginLine(idol_id="seira", **{**DEFAULT_LOGIN_LINES, "greet2": "セイラの気持ち"}))
    db.commit()

    seed_all(db)

    assert _comments_of(db, "seira") == {"{nickname}、セイラだよ"}
    assert db.get(IdolLoginLine, "seira").greet2 == "セイラの気持ち"


def test_legacy_limited_idol_comment_api_is_not_single_line(client, db, make_user):
    """④ 過去 slug を選択中のユーザーの /comment が1文固定でなくなる。"""
    db.add(
        Idol(id="seira", name="星宮セイラ", theme_color="#aabbcc",
             catchphrase="旧限定推し", is_limited=True)
    )
    db.commit()
    seed_all(db)

    user = make_user(idol_id="seira", points=0, rank=1)
    hdr = client.auth_headers(user.id)
    seen = set()
    for _ in range(30):
        res = client.get(f"/api/users/{user.id}/comment", headers=hdr)
        assert res.status_code == 200
        seen.add(res.json()["comment"])

    assert "{nickname}、いつもありがとう！".replace("{nickname}", user.nickname) not in seen
    assert len(seen) > 1, f"1文固定のまま: {seen}"


# ---------------------------------------------------------------- ⑤ 並行 seed


def _seed_in_new_session() -> str | None:
    """独立セッション（＝別プロセス相当）で seed_all を1回走らせる。"""
    session = SessionLocal()
    try:
        seed_all(session)
        return None
    except Exception as exc:  # noqa: BLE001 — 失敗の有無を検証したい
        return f"{type(exc).__name__}: {exc}"
    finally:
        session.close()


def test_concurrent_seed_does_not_fail_and_stays_idempotent(db):
    """⑤ 複数プロセス同時起動でも seed_all が落ちず、結果が冪等（R-4 M-1）。

    Container Apps のローリング更新では新リビジョンが起動してから旧が落ちるため、
    デプロイのたびに一時的に2プロセスが同時起動する。しかも delete を含む処理なので、
    重複行・主キー競合のどちらも起きてはいけない。
    """
    N = 4
    errors: list[str | None] = [None] * N
    barrier = threading.Barrier(N)

    def worker(i: int):
        barrier.wait()
        errors[i] = _seed_in_new_session()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(e is None for e in errors), f"並行 seed で失敗: {[e for e in errors if e]}"

    db.rollback()
    assert db.query(IdolComment).count() == 63, "重複行が残っている"
    assert db.query(IdolLoginLine).count() == 7
    assert db.query(Idol).count() == 7


def test_concurrent_seed_from_partially_missing_db(db):
    """⑤ 「コメントだけ欠損した既存DB」に2プロセスが同時 seed しても重複しない。

    R-4 M-1 が挙げた再現シナリオそのもの（双方が「不足」と判定して同じ行を insert する）。
    """
    db.query(IdolComment).delete()
    db.query(IdolLoginLine).delete()
    db.commit()

    N = 4
    errors: list[str | None] = [None] * N
    barrier = threading.Barrier(N)

    def worker(i: int):
        barrier.wait()
        errors[i] = _seed_in_new_session()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(e is None for e in errors), f"並行 seed で失敗: {[e for e in errors if e]}"

    db.rollback()
    assert db.query(IdolComment).count() == 63, "重複行が残っている"
    assert db.query(IdolLoginLine).count() == 7
