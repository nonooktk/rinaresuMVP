"""
デバイス判定サービス。

抽象基底クラス DeviceClassifier を定義する。
本番では Azure OpenAI gpt-4o の画像入力（Vision）で判定する
OpenAIVisionClassifier を使用し、環境変数未設定・API失敗時は
MockClassifier（ファイル名・サイズ由来のハッシュで決定論的に候補を返す）に
フォールバックする。判定機能そのものは止めない設計。

戻り値の label/points は必ず device_types マスタから確定させ、
AI の申告値は採用しない（マスタ非依存の創作を防ぐ）。
"""
import base64
import hashlib
import io
import json
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import DeviceType
from app.services.ai import get_deployment, get_openai_client


class DeviceClassifier(ABC):
    """デバイス判定の抽象基底クラス。"""

    @abstractmethod
    def classify(
        self, file_bytes: bytes, filename: str, db: Session
    ) -> list[dict]:
        """
        写真データからデバイス種別候補を確信度降順で返す。

        戻り値: [{"device_type": code, "label": ラベル, "points": pt, "confidence": 0.0-1.0}, ...]
        """
        raise NotImplementedError

    def classify_with_source(
        self, file_bytes: bytes, filename: str, db: Session
    ) -> tuple[list[dict], str]:
        """
        classify に加えて判定手段（generated_by）も返す。

        戻り値: (candidates, generated_by)。generated_by は "ai" | "mock"。
        既定実装はモック扱い。OpenAIVisionClassifier がオーバーライドする。
        """
        return self.classify(file_bytes, filename, db), "mock"


class MockClassifier(DeviceClassifier):
    """
    モック実装。

    ファイル名とファイルサイズから決定論的なハッシュ値を作り、
    device_types マスタの中から3件を確信度付きで選出する。
    同一の写真（同名・同サイズ）であれば常に同じ結果を返す。
    """

    def classify(
        self, file_bytes: bytes, filename: str, db: Session
    ) -> list[dict]:
        device_types = db.query(DeviceType).all()
        if not device_types:
            return []

        # ファイル名+サイズからハッシュを生成し、決定論的な整数シードにする
        seed_source = f"{filename}:{len(file_bytes)}".encode("utf-8")
        digest = hashlib.sha256(seed_source).hexdigest()
        seed = int(digest, 16)

        # device_typesをコードでソートし、順序を安定させる
        sorted_types = sorted(device_types, key=lambda dt: dt.code)
        n = len(sorted_types)

        # ハッシュ値から回転量を決め、候補の並びを決定論的にシャッフルする
        rotation = seed % n
        rotated = sorted_types[rotation:] + sorted_types[:rotation]
        top3 = rotated[:3] if n >= 3 else rotated

        # 確信度はハッシュ値から決定論的に算出し、降順になるよう調整する
        base_confidences = []
        for i in range(len(top3)):
            # 各候補ごとに異なる桁を使って0.0-1.0の疑似ランダム値を作る
            chunk = digest[i * 4 : i * 4 + 4]
            val = int(chunk, 16) / 0xFFFF  # 0.0〜1.0
            base_confidences.append(val)

        # 降順ソートし、1位を0.6-0.95程度、以降を減衰させて確信度らしくする
        base_confidences.sort(reverse=True)
        confidences = []
        top_conf = 0.6 + base_confidences[0] * 0.35
        confidences.append(round(top_conf, 2))
        for i in range(1, len(base_confidences)):
            prev = confidences[-1]
            decayed = prev * (0.4 + base_confidences[i] * 0.3)
            confidences.append(round(max(decayed, 0.01), 2))

        candidates = []
        for dt, conf in zip(top3, confidences):
            candidates.append(
                {
                    "device_type": dt.code,
                    "label": dt.label,
                    "points": dt.points,
                    "confidence": conf,
                }
            )
        return candidates


class OpenAIVisionClassifier(DeviceClassifier):
    """
    Azure OpenAI gpt-4o の画像入力（Vision）でデバイスを判定する実装。

    画像を長辺1024pxに縮小・JPEG化して base64 data URL にし、
    device_types マスタ（DBから動的取得）を提示したプロンプトで
    上位最大3件を確信度付き JSON で返させる。

    - label/points はマスタから確定させ、AI の申告値は使わない。
    - device_type はマスタに存在するもののみ採用、confidence は 0.0〜1.0 にクランプ。
    - クライアント未設定・API例外・応答不正・候補ゼロのいずれでも MockClassifier に
      フォールバックし、判定機能を止めない。
    """

    # 縮小後の長辺の最大ピクセル数
    MAX_EDGE = 1024

    def __init__(self) -> None:
        # フォールバック用にモック実装を内部保持する
        self._fallback = MockClassifier()

    def _to_data_url(self, file_bytes: bytes) -> str | None:
        """画像を長辺1024pxに縮小・JPEG化して base64 data URL を返す。失敗時 None。"""
        try:
            from PIL import Image

            with Image.open(io.BytesIO(file_bytes)) as img:
                # JPEG化のため RGBA/P などは RGB に変換する
                if img.mode != "RGB":
                    img = img.convert("RGB")
                # 長辺を MAX_EDGE に収める（拡大はしない）
                w, h = img.size
                longest = max(w, h)
                if longest > self.MAX_EDGE:
                    scale = self.MAX_EDGE / longest
                    img = img.resize(
                        (max(1, round(w * scale)), max(1, round(h * scale)))
                    )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/jpeg;base64,{b64}"
        except Exception:  # noqa: BLE001 — 前処理失敗時はフォールバック
            return None

    def _build_prompt(self, sorted_types: list[DeviceType]) -> str:
        """device_types マスタを提示する判定プロンプトを組み立てる。"""
        catalog = "\n".join(
            f"- {dt.code}: {dt.label}" for dt in sorted_types
        )
        return (
            "あなたは都市鉱山回収アプリの画像判定担当です。\n"
            "写真に写っている端末（回収対象の電子機器）を、次の一覧の中から判定してください。\n\n"
            f"【判定できる種別（code: ラベル）】\n{catalog}\n\n"
            "【ルール】\n"
            "- 一覧の code のみを使うこと（一覧にない種別名は返さない）。\n"
            "- 可能性が高い順に最大3件、それぞれ確信度(0.0〜1.0)を付けて返す。\n"
            "- 端末が写っていない・判別できない場合は "
            "\"other\" を低い確信度で1件だけ返す。\n"
            "- 次のJSON形式のみを出力する（余計な文章は書かない）:\n"
            '{"candidates": [{"device_type": "<code>", "confidence": <0.0-1.0>}, ...]}'
        )

    def _parse_candidates(
        self, content: str, type_map: dict[str, DeviceType]
    ) -> list[dict]:
        """AI応答JSONを検証し、マスタ準拠の候補リストに整形する。不正なら空リスト。"""
        data = json.loads(content)
        raw = data.get("candidates")
        if not isinstance(raw, list):
            return []

        candidates: list[dict] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            code = item.get("device_type")
            # マスタに存在する code のみ採用（重複は除外）
            dt = type_map.get(code)
            if dt is None or code in seen:
                continue
            seen.add(code)

            # confidence を 0.0〜1.0 にクランプ（数値でなければ 0.0 扱い）
            try:
                conf = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                conf = 0.0
            conf = max(0.0, min(1.0, conf))

            candidates.append(
                {
                    "device_type": dt.code,
                    "label": dt.label,   # ラベルはマスタから確定
                    "points": dt.points,  # ポイントもマスタから確定
                    "confidence": round(conf, 2),
                }
            )

        # 確信度の降順にソートし、最大3件に絞る
        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        return candidates[:3]

    def classify(
        self, file_bytes: bytes, filename: str, db: Session
    ) -> list[dict]:
        candidates, _ = self.classify_with_source(file_bytes, filename, db)
        return candidates

    def classify_with_source(
        self, file_bytes: bytes, filename: str, db: Session
    ) -> tuple[list[dict], str]:
        client = get_openai_client()
        device_types = db.query(DeviceType).all()

        # クライアント未設定・マスタ空はモックにフォールバック
        if client is None or not device_types:
            return self._fallback.classify(file_bytes, filename, db), "mock"

        data_url = self._to_data_url(file_bytes)
        if data_url is None:
            return self._fallback.classify(file_bytes, filename, db), "mock"

        sorted_types = sorted(device_types, key=lambda dt: dt.code)
        type_map = {dt.code: dt for dt in sorted_types}
        prompt = self._build_prompt(sorted_types)

        try:
            resp = client.chat.completions.create(
                model=get_deployment(),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url, "detail": "low"},
                            },
                        ],
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=300,
            )
            content = resp.choices[0].message.content
            candidates = self._parse_candidates(content, type_map) if content else []
        except Exception:  # noqa: BLE001 — API失敗時はモックにフォールバック
            candidates = []

        # 候補ゼロ（応答不正含む）はモックにフォールバック
        if not candidates:
            return self._fallback.classify(file_bytes, filename, db), "mock"

        return candidates, "ai"


# 現状使用する実装（OpenAI未設定・失敗時は内部でモックにフォールバック）
classifier: DeviceClassifier = OpenAIVisionClassifier()
