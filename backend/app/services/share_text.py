"""
シェア投稿文面の生成サービス。

受領済み送付物の内訳と推しアイドルのペルソナ・あだ名をもとに、
Azure OpenAI（gpt-4o）で `#りなれす` を含む 140 字以内の X 投稿文を生成する。
OpenAI が使えない／失敗した場合はテンプレ文面にフォールバックする。
"""
from collections import Counter

from sqlalchemy.orm import Session

from app.models import Device, DeviceType, Shipment, User
from app.services.ai import get_deployment, get_idol_persona, get_openai_client

# X 投稿の最大文字数（要件）
MAX_LEN = 140
HASHTAG = "#りなれす"


def _build_breakdown(shipment_id: int, db: Session) -> tuple[str, int]:
    """
    送付物の内訳文字列（例「スマートフォン2台・ガラケー1台」）と合計台数を返す。

    デバイスの device_type_code を DeviceType.label に解決して集計する。
    """
    devices = db.query(Device).filter(Device.shipment_id == shipment_id).all()

    # code -> label の対応表
    type_map = {dt.code: dt.label for dt in db.query(DeviceType).all()}

    counter: Counter[str] = Counter()
    for d in devices:
        label = type_map.get(d.device_type_code, d.label)
        counter[label] += 1

    parts = [f"{label}{count}台" for label, count in counter.items()]
    return "・".join(parts), len(devices)


def _fallback_text(breakdown: str, nickname: str) -> str:
    """
    OpenAI が使えない場合のテンプレ文面。140 字以内を保証する。
    """
    body = (
        f"{nickname}が家に眠っていた{breakdown}をりなれすに送ったよ！"
        f"都市鉱山リサイクルで推し活しながらエコに貢献♪ みんなも一緒にやってみてね "
        f"{HASHTAG}"
    )
    if len(body) > MAX_LEN:
        # 内訳が長い場合に備え、内訳を省いた短縮版
        body = (
            f"{nickname}が眠っていた端末をりなれすに送ったよ！"
            f"推し活しながら都市鉱山リサイクルでエコに貢献♪ {HASHTAG}"
        )
    if len(body) > MAX_LEN:
        body = body[: MAX_LEN - 1] + "…"
    return body


def _truncate(text: str) -> str:
    """140 字を超える場合、137 字 +「…」に短縮する。"""
    text = text.strip()
    if len(text) <= MAX_LEN:
        return text
    return text[: MAX_LEN - 1] + "…"


def _generate_with_openai(
    client, breakdown: str, persona: str, nickname: str
) -> str | None:
    """
    OpenAI で投稿文を生成する。失敗時は None を返す。

    140 字を超えたら 1 回だけより強い字数指示で再生成し、
    それでも超えたら短縮（呼び出し側で担保）。
    """
    system_prompt = (
        "あなたは都市鉱山回収促進アプリ『りなれす』のユーザーになりきって、"
        "推しアイドルへの気持ちとリサイクルの楽しさが伝わる X（旧Twitter）投稿文を書きます。\n"
        f"あなたの推しアイドルの人物像・口調: {persona}\n"
        "投稿文の条件:\n"
        f"- 必ず日本語で、全体で{MAX_LEN}文字以内（ハッシュタグ・絵文字含む）。厳守。\n"
        f"- 必ずハッシュタグ『{HASHTAG}』を1つ含める。\n"
        "- ジャンク端末をりなれすに送ってリサイクルに協力した、という前向きな内容。\n"
        "- 推し活・エコ・都市鉱山リサイクルの楽しさが伝わるポジティブなトーン。\n"
        "- 絵文字は1〜3個程度まで。URLやメンションは入れない。\n"
        "- 説明や前置きは書かず、投稿本文だけを出力する。"
    )
    user_prompt = (
        f"投稿者のあだ名: {nickname}\n"
        f"りなれすに送った端末の内訳: {breakdown}\n"
        "この内容で投稿文を1つ作ってください。"
    )

    def _call(extra: str = "") -> str | None:
        try:
            resp = client.chat.completions.create(
                model=get_deployment(),
                messages=[
                    {"role": "system", "content": system_prompt + extra},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.9,
                max_tokens=200,
            )
            content = resp.choices[0].message.content
            return content.strip() if content else None
        except Exception:  # noqa: BLE001 — 失敗時はフォールバックさせる
            return None

    text = _call()
    if text is None:
        return None
    if len(text) > MAX_LEN:
        # より強い字数指示で 1 回だけ再生成
        retry = _call(
            f"\n【重要】前回の出力は長すぎました。必ず{MAX_LEN}文字以内に厳密に収めてください。"
        )
        if retry is not None:
            text = retry
    return text


def build_share_text(shipment: Shipment, user: User, db: Session) -> tuple[str, str]:
    """
    シェア投稿文面を生成する。

    戻り値: (text, generated_by)  generated_by は "ai" または "template"
    """
    breakdown, count = _build_breakdown(shipment.id, db)
    if not breakdown:
        breakdown = "ジャンク端末"

    persona = get_idol_persona(user.idol_id)
    nickname = user.nickname

    client = get_openai_client()
    if client is not None:
        text = _generate_with_openai(client, breakdown, persona, nickname)
        if text:
            return _truncate(text), "ai"

    # フォールバック（未設定・失敗時）
    return _fallback_text(breakdown, nickname), "template"
