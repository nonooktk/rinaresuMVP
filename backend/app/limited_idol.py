"""
期間限定推し（7人目・T1特典）の定義を集約する単一の設定箇所。

【運営向け・月替わり運用手順】
  このファイルの LIMITED_IDOL を書き換え、対応する立ち絵PNGを
  frontend/public/idols/{slug}/main.png に置き換えて再起動（本番は再デプロイ）するだけで、
  期間限定推しを差し替えられる。管理GUIは無い。
    1. LIMITED_IDOL["id"]（slug）・name・theme_color・catchphrase を今月の限定推しに書き換える
    2. frontend/public/idols/{新slug}/main.png に立ち絵（背景透過PNG）を配置する
       （特殊ビジュアルと同様、ファイルを置くだけ。IdolImage 経由で表示される）
    3. バックエンドを再起動する（seed が idols テーブルへ upsert する）
  ※ slug を月ごとに変えると idols テーブルに過去の限定推し行が残るが、
    いずれも is_limited=True で通常一覧には出ないため問題ない。
    先月の限定推しを選択していたユーザーは、月替わりの遅延リセットで
    元の推し（prev_idol_id）へ自動的に復帰する。

このモジュールは backend/app/seed.py（idols への seed/upsert）と
backend/app/routers/idols.py（GET /api/idols/limited）から参照される。
アプリのコード側はこの定数のみを真実の源とし、限定推しの属性を他所にハードコードしない。
"""

# 期間限定推し（7人目）。既存6人（backend/app/seed.py）と同型のデータ構造。
# id はスラッグ。frontend/public/idols/{id}/ の立ち絵ディレクトリと対応する。
LIMITED_IDOL: dict[str, str] = {
    "id": "seira",
    "name": "星宮セイラ",
    "theme_color": "#8a5cf0",  # 限定感のあるバイオレット
    "catchphrase": "今月だけの特別なステージ、いっしょに輝こ？",
}
