"""
ポイント計算・ランク判定ロジック。

ポイント計算式: 想定重量g ÷ 10 = ポイント
ランク判定:
  rank1: 0〜49pt
  rank2: 50〜149pt
  rank3: 150pt以上
"""


def calc_points(weight_g: int) -> int:
    """想定重量(g)からポイントを算出する。"""
    return weight_g // 10


def calc_rank(points: int) -> int:
    """累計ポイントからランクを判定する。"""
    if points >= 150:
        return 3
    if points >= 50:
        return 2
    return 1
