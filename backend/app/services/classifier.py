"""
デバイス判定サービス。

抽象基底クラス DeviceClassifier を定義し、MVPでは MockClassifier を使用する。
MockClassifier はファイル名・サイズ由来のハッシュ値を用いて決定論的に
候補を返す（同じ写真であれば常に同じ結果になる）。

後日、実際の画像認識APIを使う AzureVisionClassifier を追加し、
DeviceClassifier を実装する形で差し替える想定。
"""
import hashlib
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import DeviceType


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


# 現状使用する実装（後日 AzureVisionClassifier に差し替え可能）
classifier: DeviceClassifier = MockClassifier()
