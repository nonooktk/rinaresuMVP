"""
ポイント計算・ランク判定ロジック。

ポイント算定方式（2026-07-23 改定）:
  各デバイスの pt は「リチウム含有量(g)中央値 × 10（0.1g で 1pt・四捨五入・最低1pt）」で、
  device_types マスタ（seed.py の DEVICE_TYPES）に直書きした値が正。
  デバイス登録時に DeviceType.points を Device.points へコピーする登録時スナップショット方式のため、
  マスタの pt を更新しても既存の登録デバイス・ユーザーの累計/月間ptには遡及しない。
  Li含有量の換算・出典は 02_プロジェクト/rinaresu/DESIGN_li-battery-devices.md を参照。
  （旧方式「想定重量g ÷ 10」は廃止。weight_g は参考メモとして残置。）

ランク判定（累計ポイント。閾値は不変）:
  rank1: 0〜49pt
  rank2: 50〜149pt
  rank3: 150pt以上
"""


def calc_points(weight_g: int) -> int:
    """[非推奨] 旧方式の重量ベース pt 算定（想定重量g ÷ 10）。

    現在の pt はリチウム含有量ベースで device_types マスタに直書きしており、
    デバイス登録は DeviceType.points をそのままコピーする（本関数は呼ばない）。
    現時点で呼び出し箇所は無い。後方互換のため残置するが、新規実装では使わないこと。
    """
    return weight_g // 10


def calc_rank(points: int) -> int:
    """累計ポイントからランクを判定する。"""
    if points >= 150:
        return 3
    if points >= 50:
        return 2
    return 1
