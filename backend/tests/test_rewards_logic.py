"""特典閾値の純ロジック（crossed_thresholds / next_reward / tier判定）のテスト。"""
from app.services.rewards import (
    crossed_thresholds,
    next_reward,
    tier_of_threshold,
)


def test_tier_of_threshold():
    assert tier_of_threshold(100) == "T1"
    assert tier_of_threshold(500) == "T2"
    assert tier_of_threshold(1000) == "T3"
    assert tier_of_threshold(2000) == "T3"
    assert tier_of_threshold(9000) == "T3"


def test_crossed_single_threshold():
    # 90 → 120 で T1(100) のみ
    assert crossed_thresholds(90, 120) == [100]
    # 490 → 520 で T2(500) のみ
    assert crossed_thresholds(490, 520) == [500]
    # 950 → 1050 で T3(1000) のみ
    assert crossed_thresholds(950, 1050) == [1000]


def test_crossed_multiple_thresholds_same_receive():
    # 90 → 600 で T1(100)・T2(500) を同時に跨ぐ
    assert crossed_thresholds(90, 600) == [100, 500]
    # 0 → 1200 で T1・T2・T3(1000) の3つ
    assert crossed_thresholds(0, 1200) == [100, 500, 1000]
    # 1500 → 3500 で T3 を複数（2000, 3000）
    assert crossed_thresholds(1500, 3500) == [2000, 3000]
    # 0 → 3000 で 100,500,1000,2000,3000
    assert crossed_thresholds(0, 3000) == [100, 500, 1000, 2000, 3000]


def test_crossed_boundary_inclusive_exclusive():
    # ちょうど閾値に到達 = 跨いだ扱い（<= new）
    assert crossed_thresholds(0, 100) == [100]
    # 既に閾値ちょうどにいる状態からは再付与しない（old < t の t のみ）
    assert crossed_thresholds(100, 100) == []
    assert crossed_thresholds(100, 490) == []
    # 増加なし・減少は空
    assert crossed_thresholds(500, 500) == []
    assert crossed_thresholds(500, 300) == []


def test_next_reward_progression():
    assert next_reward(0) == {"tier": "T1", "threshold": 100, "remaining": 100}
    assert next_reward(60) == {"tier": "T1", "threshold": 100, "remaining": 40}
    assert next_reward(100) == {"tier": "T2", "threshold": 500, "remaining": 400}
    assert next_reward(499) == {"tier": "T2", "threshold": 500, "remaining": 1}
    # 500〜999 の次は T3(1000)
    assert next_reward(500) == {"tier": "T3", "threshold": 1000, "remaining": 500}
    assert next_reward(999) == {"tier": "T3", "threshold": 1000, "remaining": 1}
    # 1000 ちょうどの次は 2000
    assert next_reward(1000) == {"tier": "T3", "threshold": 2000, "remaining": 1000}
    assert next_reward(2500) == {"tier": "T3", "threshold": 3000, "remaining": 500}
