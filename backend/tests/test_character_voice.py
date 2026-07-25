"""キャラ別口調（D-4）の検証。

DoD:
  ① upsert の冪等性（2回起動しても行が増えない）
  ② 既存 DB からの移行（旧・全アイドル共通コメントがキャラ別に入れ替わる）
  ③ 7人分の吹き出し（63文）とログボ文言（7×6値）が引ける
  ④ 未定義 slug が DEFAULT_LOGIN_LINES / 中立コメントに落ちる
  ⑤ 限定推しの吹き出しが1文固定でなくなる（D-4 §6.1 の穴が塞がっている）
  ⑥ API（GET /api/idols・/api/idols/limited）に login_bonus_lines が載る
  ⑦ 文言そのものの規約（イーサンの記号禁止・{nickname} は1文に1回・{points} の位置）
"""
import pytest

from app.limited_idol import LIMITED_IDOL
from app.models import Idol, IdolComment, IdolLoginLine, UserReward
from app.seed import (
    DEFAULT_LOGIN_LINES,
    IDOL_COMMENT_TEMPLATES,
    IDOL_LOGIN_LINES,
    IDOLS_DATA,
    NEUTRAL_COMMENT_TEMPLATES,
    seed_all,
)
from app.services.ai import DEFAULT_PERSONA, IDOL_PERSONAS, get_idol_persona
from app.services.monthly import current_period_jst

# 通常6人＋限定推し
ALL_SLUGS = [d["id"] for d in IDOLS_DATA] + [LIMITED_IDOL["id"]]
LINE_FIELDS = ("greet1", "greet2", "envelope", "result1", "result2", "already")


# ---------------------------------------------------------------- ① 冪等性


def test_seed_is_idempotent(db):
    """① seed_all を繰り返し呼んでも行が増殖しない（毎起動で通る upsert）。"""
    before_comments = db.query(IdolComment).count()
    before_lines = db.query(IdolLoginLine).count()
    before_idols = db.query(Idol).count()

    for _ in range(3):
        seed_all(db)

    assert db.query(IdolComment).count() == before_comments
    assert db.query(IdolLoginLine).count() == before_lines
    assert db.query(Idol).count() == before_idols


def test_comment_and_line_counts(db):
    """③ 7人 × ランク1〜3 × 各3文 ＝ 63文。ログボ文言は7人ぶん1行ずつ。"""
    assert db.query(IdolComment).count() == 63
    assert db.query(IdolLoginLine).count() == 7

    for slug in ALL_SLUGS:
        for rank in (1, 2, 3):
            count = (
                db.query(IdolComment)
                .filter(IdolComment.idol_id == slug, IdolComment.rank == rank)
                .count()
            )
            assert count == 3, f"{slug} rank{rank} が {count} 件（期待3）"


# ---------------------------------------------------------------- ② 既存DBからの移行


def test_migrates_legacy_shared_comments(db):
    """② 旧・全アイドル共通コメントを持つ既存 DB が、再起動でキャラ別へ入れ替わる。

    これが効かないと「新規 DB では通るが本番では一生変わらない」という最悪の見逃し方をする
    （DESIGN_D-4 §8 #2 / §8.1 #2）。
    """
    legacy = "{nickname}、はじめまして！これからよろしくね♪"

    # 既存 DB の状態を再現: 全アイドルのコメントを旧・共通テンプレ1文だけにする
    db.query(IdolComment).delete()
    db.query(IdolLoginLine).delete()
    for slug in ALL_SLUGS:
        db.add(IdolComment(idol_id=slug, rank=1, template=legacy))
    db.commit()
    assert db.query(IdolComment).filter(IdolComment.template == legacy).count() == 7

    # 再起動相当
    seed_all(db)

    # 旧・共通コメントは消え、キャラ別が入っている
    assert db.query(IdolComment).filter(IdolComment.template == legacy).count() == 0
    assert db.query(IdolComment).count() == 63
    assert db.query(IdolLoginLine).count() == 7

    homura = {
        c.template
        for c in db.query(IdolComment)
        .filter(IdolComment.idol_id == "homura", IdolComment.rank == 1)
        .all()
    }
    assert homura == set(IDOL_COMMENT_TEMPLATES["homura"][1])


def test_migration_does_not_touch_user_progress(db, make_user):
    """② 移行はコメント文言だけ。ユーザーのランク・pt・特典には影響しない。"""
    period = current_period_jst()
    user = make_user(points=777, rank=3, monthly_points=250, monthly_period=period)
    db.add(
        UserReward(
            user_id=user.id,
            tier="T1",
            threshold=100,
            period=period,
            reward_type="limited_idol",
        )
    )
    db.commit()

    seed_all(db)

    db.refresh(user)
    assert user.points == 777
    assert user.rank == 3
    assert user.monthly_points == 250
    assert user.monthly_period == period
    assert db.query(UserReward).filter(UserReward.user_id == user.id).count() == 1


def test_stale_comments_are_removed(db):
    """② 期待セットに無い行（過去の文言・重複行）は削除される。"""
    db.add(IdolComment(idol_id="homura", rank=1, template="これは古い文言"))
    # 同じ文言の重複行も掃除対象
    db.add(
        IdolComment(
            idol_id="homura", rank=1, template=IDOL_COMMENT_TEMPLATES["homura"][1][0]
        )
    )
    db.commit()
    assert db.query(IdolComment).filter(IdolComment.idol_id == "homura").count() == 11

    seed_all(db)

    rows = db.query(IdolComment).filter(IdolComment.idol_id == "homura").all()
    assert len(rows) == 9
    assert "これは古い文言" not in {r.template for r in rows}


# ---------------------------------------------------------------- ③ 7人分の引き当て


@pytest.mark.parametrize("slug", ALL_SLUGS)
def test_login_lines_are_seeded_for_every_idol(db, slug):
    """③ 7人ぶんのログボ文言が全フィールド埋まっている。"""
    row = db.get(IdolLoginLine, slug)
    assert row is not None, f"{slug} のログボ文言が無い"
    for field in LINE_FIELDS:
        assert getattr(row, field), f"{slug}.{field} が空"


def test_every_idol_has_distinct_voice(db):
    """③ 7人の口調が実際に異なる（＝「キャラで一緒」の指摘が解消されている）。"""
    greet2 = {
        row.idol_id: row.greet2 for row in db.query(IdolLoginLine).all()
    }
    assert len(set(greet2.values())) == 7, "ログボ挨拶が重複している"

    rank1_first = {}
    for slug in ALL_SLUGS:
        rows = (
            db.query(IdolComment)
            .filter(IdolComment.idol_id == slug, IdolComment.rank == 1)
            .all()
        )
        rank1_first[slug] = {r.template for r in rows}
    # どの2人を取っても、ランク1の3文が完全に一致することはない
    for a in ALL_SLUGS:
        for b in ALL_SLUGS:
            if a < b:
                assert rank1_first[a] != rank1_first[b], f"{a} と {b} の文言が同一"


# ---------------------------------------------------------------- ④ 未定義 slug


def test_unknown_limited_slug_falls_back_to_defaults(db, monkeypatch):
    """④ 限定推しを文言未用意の slug に差し替えても DEFAULT / 中立コメントに落ちる。

    月替わりで slug ごと差し替わるため、文言を用意し忘れても画面が壊れないことが前提
    （DESIGN_D-4 §6.2 原則2・§8.1 #4）。
    """
    monkeypatch.setitem(LIMITED_IDOL, "id", "newcomer")
    monkeypatch.setitem(LIMITED_IDOL, "name", "新人アイドル")
    monkeypatch.delitem(LIMITED_IDOL, "comments", raising=False)
    monkeypatch.delitem(LIMITED_IDOL, "login_lines", raising=False)

    seed_all(db)

    # ログボ文言は DEFAULT（＝ D-3 の原文）
    row = db.get(IdolLoginLine, "newcomer")
    assert row is not None
    for field in LINE_FIELDS:
        assert getattr(row, field) == DEFAULT_LOGIN_LINES[field]

    # 吹き出しは中立9文（API フォールバックの1文固定ではない）
    templates = {
        c.template
        for c in db.query(IdolComment).filter(IdolComment.idol_id == "newcomer").all()
    }
    expected = {t for ts in NEUTRAL_COMMENT_TEMPLATES.values() for t in ts}
    assert templates == expected
    assert len(templates) == 9


def test_unknown_slug_falls_back_to_default_persona():
    """④ FAQ・シェア文面のペルソナも未定義 slug は DEFAULT に落ちる。"""
    assert get_idol_persona("newcomer") == DEFAULT_PERSONA
    assert get_idol_persona(None) == DEFAULT_PERSONA


def test_persona_exists_for_every_idol():
    """④ 現行7人（限定推し含む）はすべて専用ペルソナを持つ（D-4 §6.1 の穴を塞ぐ）。"""
    for slug in ALL_SLUGS:
        assert slug in IDOL_PERSONAS, f"{slug} のペルソナが無い"
        assert get_idol_persona(slug) != DEFAULT_PERSONA


# ---------------------------------------------------------------- ⑤ 限定推し


def test_limited_idol_has_nine_comments(db):
    """⑤ 限定推しの吹き出しが9文ある（「{nickname}、いつもありがとう！」1文固定ではない）。"""
    slug = LIMITED_IDOL["id"]
    rows = db.query(IdolComment).filter(IdolComment.idol_id == slug).all()
    assert len(rows) == 9
    assert {r.rank for r in rows} == {1, 2, 3}
    # API フォールバック文（routers/users.py）が DB に紛れ込んでいないこと
    assert "{nickname}、いつもありがとう！" not in {r.template for r in rows}


def test_past_limited_slug_comments_are_preserved(db, monkeypatch):
    """⑤ 過去 slug の限定推しの文言は残置される（D-4 §6.3「消してはいけない」）。"""
    db.add(Idol(id="seira", name="星宮セイラ", theme_color="#aabbcc",
                catchphrase="旧限定推し", is_limited=True))
    db.flush()
    db.add(IdolComment(idol_id="seira", rank=1, template="{nickname}、セイラだよ"))
    db.commit()

    seed_all(db)

    assert db.query(IdolComment).filter(IdolComment.idol_id == "seira").count() == 1


# ---------------------------------------------------------------- ⑥ API


def test_idols_api_returns_login_bonus_lines(client, make_user):
    """⑥ GET /api/idols が login_bonus_lines を返す（後方互換の追加のみ）。"""
    res = client.get("/api/idols")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 6  # 限定推しは含まない（既存仕様）

    for idol in body:
        # 既存フィールドが消えていないこと
        for key in ("id", "name", "theme_color", "catchphrase"):
            assert key in idol
        lines = idol["login_bonus_lines"]
        assert lines is not None, f"{idol['id']} の文言が返っていない"
        for field in LINE_FIELDS:
            assert lines[field]
        assert "{nickname}、" in lines["greet1"]
        assert "{points}" in lines["result1"]


def test_limited_idol_api_returns_login_bonus_lines(client, db, make_user):
    """⑥ GET /api/idols/limited も login_bonus_lines を返す（T1保有者のみ）。"""
    period = current_period_jst()
    user = make_user()
    db.add(
        UserReward(
            user_id=user.id,
            tier="T1",
            threshold=100,
            period=period,
            reward_type="limited_idol",
        )
    )
    db.commit()

    res = client.get("/api/idols/limited", headers=client.auth_headers(user.id))
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == LIMITED_IDOL["id"]
    assert body["login_bonus_lines"] is not None
    assert body["login_bonus_lines"]["greet2"] == LIMITED_IDOL["login_lines"]["greet2"]


def test_user_comment_api_returns_character_voice(client, db, make_user):
    """⑥ GET /api/users/{id}/comment が推しごとに異なる文言を返す。"""
    for slug in ("homura", "ethan"):
        user = make_user(idol_id=slug)
        res = client.get(
            f"/api/users/{user.id}/comment", headers=client.auth_headers(user.id)
        )
        assert res.status_code == 200
        comment = res.json()["comment"]
        expected = {
            t.replace("{nickname}", user.nickname)
            for t in IDOL_COMMENT_TEMPLATES[slug][1]
        }
        assert comment in expected, f"{slug} の文言が想定外: {comment}"


# ---------------------------------------------------------------- ⑦ 文言の規約


def _all_comment_sets() -> dict[str, dict[int, list[str]]]:
    return {**IDOL_COMMENT_TEMPLATES, LIMITED_IDOL["id"]: LIMITED_IDOL["comments"]}


def _all_line_sets() -> dict[str, dict[str, str]]:
    return {**IDOL_LOGIN_LINES, LIMITED_IDOL["id"]: LIMITED_IDOL["login_lines"]}


def test_ethan_uses_no_decorative_symbols():
    """⑦ イーサンの文言に ♪ ♡ 〜 が1つも混入していない（D-4 §1.6・§5-3・§8.1 #7）。"""
    forbidden = ("♪", "♡", "〜")
    texts = [t for ts in IDOL_COMMENT_TEMPLATES["ethan"].values() for t in ts]
    texts += list(IDOL_LOGIN_LINES["ethan"].values())
    for text in texts:
        for symbol in forbidden:
            assert symbol not in text, f"イーサンの文言に {symbol} が混入: {text}"


def test_nickname_appears_at_most_once():
    """⑦ {nickname} は1文に1回だけ（D-4 §4.2。2回入れると「呼ばれすぎ」になる）。"""
    for slug, ranks in _all_comment_sets().items():
        for rank, templates in ranks.items():
            for t in templates:
                assert t.count("{nickname}") == 1, f"{slug} rank{rank}: {t}"
    for slug, lines in _all_line_sets().items():
        for field, text in lines.items():
            assert text.count("{nickname}") <= 1, f"{slug}.{field}: {text}"


def test_login_line_placeholders():
    """⑦ greet1 は「{nickname}、」で始まり、{points} は result1 にのみ入る。"""
    for slug, lines in {**_all_line_sets(), "__default__": DEFAULT_LOGIN_LINES}.items():
        assert lines["greet1"].startswith("{nickname}、"), slug
        assert "{points}" in lines["result1"], slug
        for field in ("greet1", "greet2", "envelope", "result2", "already"):
            assert "{points}" not in lines[field], f"{slug}.{field}"


def test_comment_length_within_limit():
    """⑦ 吹き出しは全角40字以内（375px で2行に収める。D-4 §2.1）。"""
    for slug, ranks in _all_comment_sets().items():
        for rank, templates in ranks.items():
            for t in templates:
                # {nickname} は実際のあだ名（全角8字想定）に置換されて表示される
                rendered = t.replace("{nickname}", "あ" * 8)
                assert len(rendered) <= 48, f"{slug} rank{rank} が長すぎる({len(rendered)}): {t}"
