"""
初期データ投入モジュール。

アプリ起動時に呼び出され、既にデータが存在する場合は何もしない（冪等）。
アイドル6人・コメントテンプレ・デバイス種別マスタ・FAQを投入する。
"""
from sqlalchemy.orm import Session

from app.limited_idol import LIMITED_IDOL
from app.models import DeviceType, FaqEntry, Idol, IdolComment


def seed_all(db: Session) -> None:
    """全seedデータを投入する（冪等）。"""
    _seed_idols(db)
    _seed_limited_idol(db)
    _seed_device_types(db)
    _seed_faq(db)
    db.commit()


def _seed_limited_idol(db: Session) -> None:
    """期間限定推し（7人目・T1特典）を idols テーブルへ upsert する。

    定義の真実の源は backend/app/limited_idol.py。運営が同ファイルを書き換えて
    再起動すると、ここで idols テーブルの当該行が最新の名前・色・キャッチフレーズに
    更新される（存在しなければ追加）。is_limited=True のため通常一覧には出ない。
    """
    existing = db.get(Idol, LIMITED_IDOL["id"])
    if existing is None:
        db.add(
            Idol(
                id=LIMITED_IDOL["id"],
                name=LIMITED_IDOL["name"],
                theme_color=LIMITED_IDOL["theme_color"],
                catchphrase=LIMITED_IDOL["catchphrase"],
                is_limited=True,
            )
        )
    else:
        # 運営がファイルを差し替えた場合に備え、属性を最新化する（is_limited は必ず True）
        existing.name = LIMITED_IDOL["name"]
        existing.theme_color = LIMITED_IDOL["theme_color"]
        existing.catchphrase = LIMITED_IDOL["catchphrase"]
        existing.is_limited = True


def _seed_idols(db: Session) -> None:
    """アイドル6人とコメントテンプレートを投入する。"""
    if db.query(Idol).count() > 0:
        return

    # idはフロントエンドのイラストディレクトリ（public/idols/{id}/）と対応するスラッグ。
    # 全6人とも支給イラスト（main.png・背景透過済み）配置済み。
    idols_data = [
        {
            "id": "homura",
            "name": "金城ほむら",
            "theme_color": "#f2b705",  # ゴールドイエロー
            "catchphrase": "キラキラは金色！ほむらにおまかせ♪",
        },
        {
            "id": "minori",
            "name": "紅谷美野里",
            "theme_color": "#e0524d",  # レッド
            "catchphrase": "ハートに一直線、美野里だよっ！",
        },
        {
            "id": "shion",
            "name": "奏多紫苑",
            "theme_color": "#9d8ee0",  # パープル
            "catchphrase": "星降るステージ、一緒に見よ？",
        },
        {
            "id": "miho",
            "name": "蒼乃美帆",
            "theme_color": "#4fc3dd",  # シアンブルー
            "catchphrase": "透きとおる歌声、届けるよ！",
        },
        {
            "id": "yukari",
            "name": "桃宮ゆかり",
            "theme_color": "#f06fae",  # ピンク
            "catchphrase": "ゆかりんパワー、ちゅうにゅ〜♪",
        },
        {
            "id": "ethan",
            "name": "長岡イーサン",
            "theme_color": "#b3273e",  # クリムゾンレッド
            "catchphrase": "その端末、俺に預けてみないか？",
        },
    ]

    idols = []
    for data in idols_data:
        idol = Idol(**data)
        db.add(idol)
        idols.append(idol)
    db.flush()  # idを確定させる

    # ランクが上がるほど親密な文面になるコメントテンプレ（各アイドル×各ランク3種以上）
    comment_templates = {
        1: [
            "{nickname}、はじめまして！これからよろしくね♪",
            "{nickname}が来てくれて嬉しいな。少しずつ仲良くなろうね！",
            "{nickname}、デバイスの登録ありがとう！応援してるよ！",
        ],
        2: [
            "{nickname}、いつも協力してくれてありがとう！すごく頼りにしてるよ！",
            "{nickname}のおかげでポイントも順調だね。もっと一緒に頑張ろう！",
            "{nickname}とはもうすっかり仲良しな気がする！これからもよろしくね♪",
        ],
        3: [
            "{nickname}、大好き！いつも一番の味方でいてくれてありがとう！！",
            "{nickname}となら都市鉱山だってどこまでも掘り進めちゃう気がする！",
            "{nickname}は私にとって特別な存在だよ。本当にありがとう、大好き！",
        ],
    }

    for idol in idols:
        for rank, templates in comment_templates.items():
            for template in templates:
                db.add(IdolComment(idol_id=idol.id, rank=rank, template=template))


# デバイス種別マスタ（21種）の真実の源。
#
# 家庭から出るリチウムイオン電池内蔵の小型機器を、画像判定で弁別しやすい粒度で網羅する。
# pt はリチウム含有量(g)中央値ベース（案B・×10＝0.1gで1pt・四捨五入・最低1pt保証）。
# 換算式は Li当量(g) = 定格エネルギー(Wh) ÷ 12 ＝ 0.3 × 定格容量(Ah)（IATA/ICAO の危険物当量）。
# 設計の正本と出典は 02_プロジェクト/rinaresu/DESIGN_li-battery-devices.md を参照。
#
# weight_g は旧方式（重量10g=1pt）の名残で、現在は pt 算定に使わない参考メモ（代表機器質量の概算）。
# 既存6コード（smartphone/feature_phone/tablet/camera/portable_game/other）は互換のため code を維持し、
# pt 値のみ新方式へ更新する（camera は label「デジタルカメラ」を維持、other は label を刷新）。
DEVICE_TYPES: list[dict] = [
    # --- 小型（Li < 0.5g 前後）---
    {"code": "wireless_earbuds", "label": "ワイヤレスイヤホン", "weight_g": 55, "points": 1},
    {"code": "smart_band_watch", "label": "スマートウォッチ・活動量計", "weight_g": 45, "points": 1},
    {"code": "wireless_mouse_kbd", "label": "ワイヤレスマウス・キーボード", "weight_g": 100, "points": 1},
    {"code": "e_cigarette", "label": "電子タバコ（VAPE）", "weight_g": 60, "points": 2},
    {"code": "electric_toothbrush", "label": "電動歯ブラシ", "weight_g": 120, "points": 2},
    {"code": "electric_shaver", "label": "電気シェーバー・バリカン", "weight_g": 180, "points": 3},
    # --- 中型 ---
    {"code": "handy_fan", "label": "ハンディファン・携帯扇風機", "weight_g": 200, "points": 6},
    {"code": "heated_tobacco", "label": "加熱式タバコ", "weight_g": 120, "points": 6},
    {"code": "feature_phone", "label": "ガラケー", "weight_g": 100, "points": 4},
    {"code": "camera", "label": "デジタルカメラ", "weight_g": 300, "points": 4},
    {"code": "mobile_router", "label": "モバイルルーター・ポケットWiFi", "weight_g": 120, "points": 9},
    {"code": "bluetooth_speaker", "label": "Bluetoothスピーカー", "weight_g": 400, "points": 9},
    {"code": "smartphone", "label": "スマートフォン", "weight_g": 170, "points": 12},
    {"code": "portable_game", "label": "携帯ゲーム機", "weight_g": 250, "points": 13},
    {"code": "tablet", "label": "タブレット", "weight_g": 450, "points": 22},
    # --- 大型（Li 高含有）---
    {"code": "drone", "label": "ドローン（ホビー用）", "weight_g": 400, "points": 25},
    {"code": "mobile_battery", "label": "モバイルバッテリー", "weight_g": 250, "points": 31},
    {"code": "laptop", "label": "ノートPC", "weight_g": 1400, "points": 42},
    {"code": "cordless_vacuum", "label": "コードレス掃除機", "weight_g": 2500, "points": 50},
    {"code": "power_tool", "label": "電動工具バッテリー", "weight_g": 650, "points": 60},
    # --- フォールバック ---
    {"code": "other", "label": "その他小型充電式機器", "weight_g": 100, "points": 5},
]


def _seed_device_types(db: Session) -> None:
    """デバイス種別マスタ（21種）を code をキーに upsert する（冪等）。

    従来は「1件でもあればスキップ」だったが、それだと既存 DB（本番・稼働中ローカル）に
    新カテゴリが入らない。そこで _seed_limited_idol と同じ upsert 方式に変更する:
    無い code は insert、既存 code は label/weight_g/points を最新化する。
    毎起動で通るため、DEVICE_TYPES を書き換えて再起動すればマスタが最新化される。

    - 純粋な ORM 操作のため SQLite / PostgreSQL 両対応。
    - 既存デバイス（Device.points）は登録時スナップショットのため、ここでの pt 更新は
      過去の登録分へ遡及しない（新規登録分から新 pt が適用される＝遡及なし移行）。
    """
    for dt in DEVICE_TYPES:
        existing = db.get(DeviceType, dt["code"])
        if existing is None:
            db.add(DeviceType(**dt))
        else:
            existing.label = dt["label"]
            existing.weight_g = dt["weight_g"]
            existing.points = dt["points"]


def _seed_faq(db: Session) -> None:
    """FAQエントリを question をキーに upsert する（冪等）。

    従来は「1件でもあればスキップ」だったが、それだと既存 DB（本番・稼働中ローカル）の
    FAQ 回答文がコード側の更新に追従しない（例: ポイント計算の説明が旧「10gにつき1pt」の
    まま残る＝ユーザー向けの誤情報）。そこで question を一致キーに update/insert する:
    同じ question の行があれば category/keywords/answer を最新化、無ければ insert。
    毎起動で通るため、コードの faq_data を書き換えて再起動すれば既存 DB も最新化される。

    - question は seed データ内で一意（実質のキー）。純 ORM 操作で SQLite/PostgreSQL 両対応。
    """
    faq_data = [
        # ---------- 送付方法 ----------
        {
            "category": "shipping",
            "question": "回収キットはどうやって送ればいいの？",
            "keywords": "送り方,送付方法,どう送る,発送方法",
            "answer": (
                "{nickname}、送り方はかんたんだよ！まず伝票PDFをコンビニのプリンターで印刷してね。"
                "それを段ボールに貼り付けて、そのまま着払いで郵送してもらえば完了！"
            ),
        },
        {
            "category": "shipping",
            "question": "伝票はどこで印刷できるの？",
            "keywords": "伝票,印刷,コンビニ,プリント",
            "answer": (
                "{nickname}、伝票PDFはコンビニのマルチコピー機でPDF印刷すれば大丈夫だよ！"
                "印刷した伝票を箱に貼って、着払いで送ってね。"
            ),
        },
        {
            "category": "shipping",
            "question": "送料はかかりますか？",
            "keywords": "送料,着払い,費用,料金",
            "answer": (
                "{nickname}、送料は着払いだから{nickname}の負担はゼロだよ！"
                "安心してりなれす宛てに送ってね♪"
            ),
        },
        {
            "category": "shipping",
            "question": "箱がない場合はどうすればいいですか？",
            "keywords": "箱,段ボール,梱包",
            "answer": (
                "{nickname}、お家にある空き箱や封筒でも大丈夫だよ！"
                "デバイスが壊れないように包んで、伝票を貼って送ってね。"
            ),
        },
        # ---------- ポイント ----------
        {
            "category": "points",
            "question": "ポイントはいつ付与されますか？",
            "keywords": "ポイント,いつ,付与,反映",
            "answer": (
                "{nickname}、ポイントはりなれすがデバイスを受領して内容を確認したあとに付与されるよ！"
                "少しだけ待っててね。"
            ),
        },
        {
            "category": "points",
            "question": "ポイントの計算方法を教えてください",
            "keywords": "計算,何ポイント,ポイント数,リチウム,電池",
            "answer": (
                "{nickname}、ポイントは端末の種類ごとに、内蔵リチウムイオン電池の"
                "リチウム量の目安（0.1gにつき1pt）をもとに決まるよ！"
                "リチウムを多く含む機器ほど高ポイント（例: スマートフォン12pt・"
                "モバイルバッテリー31pt・ノートPC42pt）。"
                "付与は、りなれすに届いて確認できたあとだよ。"
            ),
        },
        {
            "category": "points",
            "question": "ポイントは何に使えますか？",
            "keywords": "ポイント 使い道,ランク,特典",
            "answer": (
                "{nickname}、貯めたポイントに応じてランクが上がって、私からのコメントがどんどん特別になっていくよ！"
                "たくさん貯めて、もっと仲良くなろうね♪"
            ),
        },
        # ---------- データ消去 ----------
        {
            "category": "data_erase",
            "question": "データはちゃんと消去されますか？",
            "keywords": "データ,消去,情報,漏洩,消える",
            "answer": (
                "{nickname}、安心して！提携業者が専用ソフトを使って完全にデータを消去してくれるよ。"
                "消去が終わったら証明書も発行されるから、{nickname}の大事な情報はしっかり守られるよ。"
            ),
        },
        {
            "category": "data_erase",
            "question": "初期化してから送った方がいいですか？",
            "keywords": "初期化,リセット,工場出荷",
            "answer": (
                "{nickname}、初期化しなくても大丈夫だよ！"
                "提携業者が専用ソフトでデータを完全に消去してから処理してくれるから、そのまま送って安心してね。"
            ),
        },
        {
            "category": "data_erase",
            "question": "消去証明はもらえますか？",
            "keywords": "証明,証明書,消去証明",
            "answer": (
                "{nickname}、データ消去後にはちゃんと消去証明が発行される仕組みになっているよ。"
                "{nickname}の安心のために、しっかり対応させてもらうね！"
            ),
        },
        {
            "category": "data_erase",
            "question": "写真や連絡先も消えますか？",
            "keywords": "写真,連絡先,個人情報",
            "answer": (
                "{nickname}、写真や連絡先を含めて専用ソフトで完全消去するから心配いらないよ！"
                "安心してりなれすに任せてね。"
            ),
        },
    ]
    for faq in faq_data:
        existing = (
            db.query(FaqEntry).filter(FaqEntry.question == faq["question"]).first()
        )
        if existing is None:
            db.add(FaqEntry(**faq))
        else:
            existing.category = faq["category"]
            existing.keywords = faq["keywords"]
            existing.answer = faq["answer"]
