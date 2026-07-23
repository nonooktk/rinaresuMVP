"""
FAQ マスタ（faq_entries）の upsert 検証。

既存DB（旧文面）でも起動時 seed でポイント計算系の回答が新方式へ更新されること、
重複 insert しないこと、冪等であることを確認する。

背景: 旧 _seed_faq は「1件でもあればスキップ」だったため、稼働中DBのFAQ回答文が
コード更新に追従せず「10gにつき1pt」の旧説明が残っていた（ユーザー向け誤情報）。
question をキーにした upsert へ変更したことを保証する回帰テスト。
"""
from app.models import FaqEntry
from app.seed import _seed_faq

_POINTS_Q = "ポイントの計算方法を教えてください"


def test_faq_points_answer_is_lithium_based(db):
    """新規DB（conftest seed 済み）のポイント計算FAQは新方式（リチウム量ベース）。"""
    entry = db.query(FaqEntry).filter(FaqEntry.question == _POINTS_Q).first()
    assert entry is not None
    # 旧文面が残っていないこと
    assert "10gにつき" not in entry.answer
    assert "リチウム" in entry.answer
    assert "0.1gにつき1pt" in entry.answer


def test_faq_upsert_updates_stale_answer(db):
    """既存DBに旧文面がある状態 → seed で新文面へ更新される（insert ではなく update）。"""
    entry = db.query(FaqEntry).filter(FaqEntry.question == _POINTS_Q).first()
    assert entry is not None
    original_id = entry.id
    before_count = db.query(FaqEntry).count()

    # 旧文面（10gにつき1pt）へ差し戻して既存DB状態を再現
    entry.answer = "{nickname}、目安は10gにつき1ポイントだよ！"
    entry.keywords = "計算,何ポイント,ポイント数,重さ,重量"
    db.commit()

    # upsert 実行
    _seed_faq(db)
    db.commit()

    updated = db.query(FaqEntry).filter(FaqEntry.question == _POINTS_Q).first()
    # 同じ行が更新されている（id 不変＝重複 insert していない）
    assert updated.id == original_id
    assert db.query(FaqEntry).count() == before_count  # 件数不変
    assert "10gにつき" not in updated.answer
    assert "0.1gにつき1pt" in updated.answer


def test_faq_upsert_is_idempotent(db):
    """複数回 seed しても件数・内容が安定（question の重複が生じない）。"""
    before_count = db.query(FaqEntry).count()
    _seed_faq(db)
    db.commit()
    _seed_faq(db)
    db.commit()

    assert db.query(FaqEntry).count() == before_count
    questions = [e.question for e in db.query(FaqEntry).all()]
    assert len(questions) == len(set(questions))  # question 重複なし
