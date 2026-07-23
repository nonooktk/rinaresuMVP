"""
pt特典プログラムの閾値判定・付与・保有状況算出ロジック。

閾値列（月間pt）:
  - 100pt   → T1（期間限定推し / limited_idol）
  - 500pt   → T2（特殊ビジュアル / special_visual）
  - 1000pt 以降 1000ptごと（1000,2000,3000…） → T3（握手会抽選券 / handshake_ticket）

受領で月間ptが「旧→新」で跨いだ閾値を **すべて** 付与する（複数同時付与あり）。
付与履歴は user_rewards テーブル。同一 period 内の同一 threshold は重複付与しない。
"""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserReward

# 固定閾値（下位2段）。T3 は 1000pt ごとに動的生成する。
T1_THRESHOLD = 100
T2_THRESHOLD = 500
T3_STEP = 1000

# tier → reward_type の対応
REWARD_TYPE_BY_TIER = {
    "T1": "limited_idol",
    "T2": "special_visual",
    "T3": "handshake_ticket",
}

# 達成演出・表示用の日本語ラベル
LABEL_BY_TIER = {
    "T1": "期間限定推し",
    "T2": "特殊ビジュアル",
    "T3": "握手会抽選券",
}


def tier_of_threshold(threshold: int) -> str:
    """閾値から tier を判定する（100=T1 / 500=T2 / 1000以降=T3）。"""
    if threshold == T1_THRESHOLD:
        return "T1"
    if threshold == T2_THRESHOLD:
        return "T2"
    return "T3"  # 1000, 2000, 3000, ...


def crossed_thresholds(old_mp: int, new_mp: int) -> list[int]:
    """月間ptが old_mp → new_mp へ増えたときに跨いだ閾値を昇順で返す。

    「跨いだ」= old_mp < threshold <= new_mp。減少（old>=new）や据え置きは空リスト。
    """
    if new_mp <= old_mp:
        return []

    result: list[int] = []
    # 固定段（T1・T2）
    for t in (T1_THRESHOLD, T2_THRESHOLD):
        if old_mp < t <= new_mp:
            result.append(t)
    # T3（1000ごと）: new_mp までの 1000 の倍数のうち old_mp を超えたもの
    #   old_mp より大きい最初の 1000 の倍数から開始
    first = (old_mp // T3_STEP + 1) * T3_STEP
    t = first
    while t <= new_mp:
        result.append(t)
        t += T3_STEP

    return sorted(result)


def next_reward(monthly_points: int) -> dict | None:
    """現在の月間ptに対する「次に狙う特典」を返す。

    返り値: {"tier": str, "threshold": int, "remaining": int}
    全段が T3 で無限に続くため None にはならないが、型の安全のため Optional にしておく。
    """
    mp = max(monthly_points, 0)
    if mp < T1_THRESHOLD:
        threshold = T1_THRESHOLD
    elif mp < T2_THRESHOLD:
        threshold = T2_THRESHOLD
    else:
        # 500以上は次の 1000 刻み（T3）。500〜999 は 1000、1000 ちょうどは 2000。
        threshold = (mp // T3_STEP + 1) * T3_STEP

    return {
        "tier": tier_of_threshold(threshold),
        "threshold": threshold,
        "remaining": threshold - mp,
    }


def grant_rewards(
    user: User, old_mp: int, new_mp: int, period: str, db: Session
) -> list[dict]:
    """跨いだ閾値ぶんの特典を付与し、付与できた特典の一覧を返す。

    - 各閾値について UserReward を作成する（同一 period・同一 threshold は
      UNIQUE 制約と事前チェックの二重で重複付与を防ぐ）。
    - この関数は flush までを行い、commit は呼び出し側（受領処理）に委ねる。
    - 返り値: [{"tier","threshold","reward_type","label"}, ...]（付与順・昇順）
    """
    granted: list[dict] = []

    for threshold in crossed_thresholds(old_mp, new_mp):
        # 既に同一 period で同一 threshold を付与済みなら二重付与しない（跨ぎ判定でも
        # 通常起きないが、二重受領・並行リクエスト等の保険）。
        exists = (
            db.query(UserReward)
            .filter(
                UserReward.user_id == user.id,
                UserReward.threshold == threshold,
                UserReward.period == period,
            )
            .first()
        )
        if exists:
            continue

        tier = tier_of_threshold(threshold)
        reward_type = REWARD_TYPE_BY_TIER[tier]
        reward = UserReward(
            user_id=user.id,
            tier=tier,
            threshold=threshold,
            period=period,
            reward_type=reward_type,
        )
        db.add(reward)
        try:
            # UNIQUE(user_id, threshold, period) 制約違反を早期検知する（並行付与の保険）。
            db.flush()
        except IntegrityError:
            db.rollback()
            continue

        granted.append(
            {
                "tier": tier,
                "threshold": threshold,
                "reward_type": reward_type,
                "label": LABEL_BY_TIER[tier],
            }
        )

    return granted


def rewards_status(user: User, db: Session, period: str) -> dict:
    """ユーザーの特典保有状況を返す。

    - special_visual（T2・恒久）: reward_type="special_visual" が1件でもあれば True
    - limited_idol_active（T1・当月のみ）: reward_type="limited_idol" かつ period=当月 があれば True
    - tickets（T3・恒久・積み上げ）: reward_type="handshake_ticket" のレコード件数
    """
    special_visual = (
        db.query(UserReward)
        .filter(
            UserReward.user_id == user.id,
            UserReward.reward_type == "special_visual",
        )
        .first()
        is not None
    )
    limited_idol_active = (
        db.query(UserReward)
        .filter(
            UserReward.user_id == user.id,
            UserReward.reward_type == "limited_idol",
            UserReward.period == period,
        )
        .first()
        is not None
    )
    tickets = (
        db.query(UserReward)
        .filter(
            UserReward.user_id == user.id,
            UserReward.reward_type == "handshake_ticket",
        )
        .count()
    )
    return {
        "special_visual": special_visual,
        "limited_idol_active": limited_idol_active,
        "tickets": tickets,
    }
