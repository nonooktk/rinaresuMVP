# 画像判定 精度検証ハーネス（Phase 1）

`POST /api/devices/classify` の中核である `OpenAIVisionClassifier`
（`backend/app/services/classifier.py`）の精度をオフラインで測定するためのハーネス。
uvicorn を起動せず、classifier を直接呼んで判定する。

## ディレクトリ構成

```
backend/eval/
├── eval_classifier.py     # 評価スクリプト本体
├── README.md              # 本ファイル
├── test_images/           # 評価用画像（gitignore 対象・ローカル管理）
│   ├── smartphone/*.jpg
│   ├── feature_phone/*.jpg
│   ├── tablet/*.jpg
│   ├── camera/*.jpg
│   ├── portable_game/*.jpg
│   ├── other/*.jpg        # （任意）その他小型家電
│   ├── negative/*.jpg     # 回収対象外（リモコン・電卓・食べ物など）
│   └── sources.csv        # 各画像の出典URL・ライセンス
└── results/               # 実行結果（gitignore 対象・ローカル管理）
    ├── eval_{タイムスタンプ}.csv   # 画像ごとの明細
    └── eval_{タイムスタンプ}.md    # サマリ
```

`test_images/` のフォルダ名がそのまま**正解ラベル**になる。
正解ラベル = `device_types` の code 6種
（`smartphone` / `feature_phone` / `tablet` / `camera` / `portable_game` / `other`）
＋ `negative`（回収対象外・端末が写っていない画像）。

## 画像の置き方

`test_images/{正解ラベル}/` の下に `.jpg` / `.png` / `.webp` を置く。
出典とライセンスは `test_images/sources.csv` に
「ファイルパス, 出典URL, ライセンス」の形式で記録する（再配布回避のためリポジトリには含めない）。

## 実行方法（venv 必須）

```bash
# リポジトリルートから
cd backend

# Azure OpenAI の環境変数を読み込む（AZURE_OPENAI_ENDPOINT / _API_KEY / _DEPLOYMENT）
source /path/to/openai.env

# フル実行（全画像を1回ずつ判定）
venv/bin/python eval/eval_classifier.py

# 安定性チェック付き（各ラベル先頭1枚を3回ずつ再判定して Top-1 のブレを記録）
venv/bin/python eval/eval_classifier.py --repeat-stability

# 画像を指定して安定性チェック（label/filename をカンマ区切り）
venv/bin/python eval/eval_classifier.py \
  --repeat-stability "smartphone/a.jpg,tablet/b.png" --stability-repeat 3
```

### 環境変数

`app/services/ai.py` が参照する以下が揃っていれば実 gpt-4o で判定する。
未設定の場合は classifier が内部で `MockClassifier` にフォールバックし、
`generated_by=mock` として記録される（実画像は解析されない）。

| 環境変数 | 例 |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | `https://oai-tvmvp-73bb.openai.azure.com/` |
| `AZURE_OPENAI_API_KEY` | （秘匿。ここには書かない） |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` |

### DB について

既定で `backend/data/rinaresu.db` を使う。`device_types` が未 seed の場合は
`create_all` + `seed_all` を自動実行する（冪等）。
常に初期化したい場合は `--fresh-db` を付ける。

## 指標の読み方

- **Top-1 正解率 / Top-3 正解率**（negative 以外の端末クラスが分母）
  - Top-1: 確信度1位の code が正解ラベルと一致した割合
  - Top-3: 返した候補（最大3件）のどれかが正解ラベルに含まれた割合
- **クラス別 Top-1 正解率**: ラベルごとの内訳（弱いクラスの特定用）
- **混同行列（Top-1）**: 行=正解ラベル、列=予測 code。`(none)` は候補ゼロ。
  対角が正解、非対角が誤り。どのクラスをどのクラスと取り違えるかを見る。
- **negative 誤検知率**: negative 画像に対し、端末クラス（`other` を除く）を
  `confidence>0.7` で Top-1 に返した割合。
  参考として `other` も含めた広義誤検知率も併記する。
- **応答時間 p50 / p95**: 1画像あたりの classify 所要秒（前処理＋API往復込み）
- **mock フォールバック発生数**: `generated_by=mock` になった件数
  （API失敗・応答不正・候補ゼロなどで実判定できなかった数）
- **安定性チェック**: 同一画像を複数回判定した際の Top-1 のブレ
  （temperature=0.2 のため多少ブレ得る。運用時の再現性の目安）
- **プロンプトバージョン識別子**: classifier.py の判定プロンプト該当部分の
  SHA-256 先頭12桁。Phase 2 でプロンプトを変えると値が変わるので改善前後の比較に使う。

## 合格基準

| 指標 | 合格基準 |
|---|---|
| Top-3 正解率 | 90% 以上 |
| Top-1 正解率 | 75% 以上 |
| negative 誤検知率 | 5% 以下 |

サマリ Markdown の「合格基準との比較」表で各指標の合否が確認できる。

## 注意

- `app/` 本体のコードは変更しない（プロンプト改善は Phase 2）。
- API コストがかかるため、フル実行は基本1回＋安定性チェック分にとどめる。
- `test_images/` と `results/` は `.gitignore` 済み（フリー素材の再配布回避・結果はローカル管理）。
