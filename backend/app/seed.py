"""
初期データ投入モジュール。

アプリ起動時に呼び出され、既にデータが存在する場合は何もしない（冪等）。
アイドル6人・コメントテンプレ・デバイス種別マスタ・FAQを投入する。
"""
from sqlalchemy.orm import Session

from app.models import DeviceType, FaqEntry, Idol, IdolComment, FaqVariant


def seed_all(db: Session) -> None:
    """全seedデータを投入する（冪等）。"""
    _seed_idols(db)
    _seed_device_types(db)
    _seed_faq(db)
    _seed_idol_comments(db)
    db.commit()


def _seed_idols(db: Session) -> None:
    """アイドル6人を upsert する（既存行があれば属性を最新化）。"""
    idols_data = [
        {
            "id": "riji",
            "name": "リジ・チョー",
            "theme_color": "#E84393",
            "catchphrase": "エコ、チョー映えるっす。",
        },
        {
            "id": "taka",
            "name": "タカ・チャーン",
            "theme_color": "#F2B705",
            "catchphrase": "これって、いい一歩だと思うんですけど。",
        },
        {
            "id": "kurosuke",
            "name": "くろすけん",
            "theme_color": "#4E8D5B",
            "catchphrase": "はい。着実に、回収します。",
        },
        {
            "id": "miirin",
            "name": "みーりん",
            "theme_color": "#F2762E",
            "catchphrase": "めっちゃ集まってるやん、おおきに！",
        },
        {
            "id": "hiroji",
            "name": "ひろじぃ・ネクスト",
            "theme_color": "#7A5CB0",
            "catchphrase": "えー、まぁ…その一台、未来の資源じゃよ。",
        },
        {
            "id": "teraoman",
            "name": "テラオーマン",
            "theme_color": "#2D7DD2",
            "catchphrase": "よいしょ！その一台、オレが受け取るぜ！",
        },
    ]

    for data in idols_data:
        existing = db.get(Idol, data["id"])
        if existing is None:
            db.add(Idol(**data))
        else:
            # 既存があれば属性を最新化（スキーマ互換であれば安全）
            existing.name = data["name"]
            existing.theme_color = data["theme_color"]
            existing.catchphrase = data["catchphrase"]


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
    新カテゴリが入らない。そこで upsert 方式に変更する:
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
    FAQ 回答文がコード側の更新に追従しない。そこで question を一致キーに update/insert する:
    同じ question の行があれば category/keywords/answer を最新化、無ければ insert。
    毎起動で通るため、コードの faq_data を書き換えて再起動すれば既存 DB も最新化される。

    - question は seed データ内で一意（実質のキー）。純 ORM 操作で SQLite/PostgreSQL 両対応。
    - variants の upsert も同時に行う（idol_id・faq_entry_id・answer の組み合わせで判定）。
    """

    faq_data = [
        # ---------- 送付方法 ----------
        {
            "category": "shipping",
            "question": "回収キットはどうやって送ればいいの？",
            "keywords": "送り方,送付方法,どう送る,発送方法",
            "variants": {
                "riji": "{nickname}、伝票PDFを印刷して箱に貼るだけっす！コンビニでPDF印刷→着払いでOKっす。",
                "taka": "{nickname}さん、伝票PDFを印刷して箱に貼るだけで大丈夫です。コンビニで印刷して着払いで送ってくださいね。",
                "kurosuke": "{nickname}、伝票を印刷して箱に貼り、着払いで発送してください。手順は以上です。",
                "miirin": "{nickname}、伝票印刷して箱に貼るだけでええで！コンビニで印刷して着払いで送ってな〜",
                "hiroji": "{nickname}さん、伝票を印刷し箱に貼って着払いで送れば良いのじゃよ。",
                "teraoman": "{nickname}、伝票を印刷して箱に貼って送るんだ！着払いで大丈夫だぞ！",
            },
        },
        {
            "category": "shipping",
            "question": "伝票はどこで印刷できるの？",
            "keywords": "伝票,印刷,コンビニ,プリント",
            "variants": {
                "riji": "{nickname}、コンビニのマルチコピーでPDF印刷すればOKっす。プリントして箱に貼って送ってほしいっす。",
                "taka": "{nickname}さん、コンビニのマルチコピー機でPDF印刷できます。印刷後は箱に貼って着払いで送ってください。",
                "kurosuke": "{nickname}、伝票PDFはコンビニのマルチコピー機で印刷できます。箱に貼り、着払いで発送してください。",
                "miirin": "{nickname}、伝票PDFはコンビニのマルチコピー機で印刷できるで！印刷したら箱に貼って着払いで送ってな〜",
                "hiroji": "{nickname}さん、伝票PDFはコンビニのマルチコピー機で印刷できるのじゃよ。印刷したら箱に貼って着払いで送りなされ。",
                "teraoman": "{nickname}、伝票PDFはコンビニのマルチコピー機で印刷できるぞ！印刷したら箱に貼って着払いで送るんだ！",
            },
        },
        {
            "category": "shipping",
            "question": "送料はかかりますか？",
            "keywords": "送料,着払い,費用,料金",
            "variants": {
                "riji": "{nickname}、送料は着払いだから{nickname}の負担ゼロっす！安心して送ってほしいっす。",
                "taka": "{nickname}さん、送料は着払いなので{nickname}さんの負担はゼロです。安心して送ってくださいね。",
                "kurosuke": "{nickname}、送料は着払いです。負担はありません。ご安心ください。",
                "miirin": "{nickname}、送料は着払いやから{nickname}の負担ゼロやで！安心して送ってな〜",
                "hiroji": "{nickname}さん、送料は着払いでな、{nickname}さんの負担はゼロじゃよ。安心なされ。",
                "teraoman": "{nickname}、送料は着払いだ！{nickname}の負担はゼロだぞ、安心して送ってくれ！",
            },
        },
        {
            "category": "shipping",
            "question": "箱がない場合はどうすればいいですか？",
            "keywords": "箱,段ボール,梱包",
            "variants": {
                "riji": "{nickname}、家にある空き箱や封筒でOKっす！デバイス包んで、伝票貼って送ってほしいっす。",
                "taka": "{nickname}さん、お家の空き箱や封筒でも大丈夫だと思います。デバイスが壊れないように包んで、伝票を貼って送ってくださいね。",
                "kurosuke": "{nickname}、空き箱や封筒で構いません。デバイスを包み、伝票を貼って発送してください。",
                "miirin": "{nickname}、家の空き箱や封筒でええねんで！デバイス包んで、伝票貼って送ってな〜",
                "hiroji": "{nickname}さん、空き箱や封筒でも良いのじゃよ。デバイスを包んで、伝票を貼って送りなされ。",
                "teraoman": "{nickname}、空き箱や封筒でいいんだ！デバイスをしっかり包んで、伝票を貼って送るんだぞ！",
            },
        },
        # ---------- ポイント ----------
        {
            "category": "points",
            "question": "ポイントはいつ付与されますか？",
            "keywords": "ポイント,いつ,付与,反映",
            "variants": {
                "riji": "{nickname}、ポイントはりなれすがデバイス受領して確認したあとに付与っす！ちょい待っってほしいっす。",
                "taka": "{nickname}さん、ポイントはりなれすがデバイスを受け取って確認したあとに付与されます。ちょっとだけ待っていてくださいね。",
                "kurosuke": "{nickname}、ポイントは受領・確認後に付与されます。少しお待ちください。",
                "miirin": "{nickname}、ポイントはりなれすが受け取って確認したあとに付くで！ちょっとだけ待っってな〜",
                "hiroji": "{nickname}さん、ポイントはりなれすが受領して確認したあとに付くのじゃよ。まぁ、少し待ちなされ。",
                "teraoman": "{nickname}、ポイントはりなれすが受け取って確認したあとに付くぞ！もう少しだけ待ってくれ！",
            },
        },
        {
            "category": "points",
            "question": "ポイントの計算方法を教えてください",
            "keywords": "計算,何ポイント,ポイント数,重さ,重量",
            "variants": {
                "riji": "{nickname}、ポイントは端末ごとのリチウムイオン電池のリチウム量の目安（0.1gで1pt）で決まるっす！多く含むほど高ポイントっすよ（例：スマホ12pt・モバイルバッテリー31pt・ノートPC42pt）。付与は届いて確認できたあとっす。",
                "taka": "{nickname}さん、ポイントは端末ごとに、内蔵リチウムイオン電池のリチウム量の目安（0.1gにつき1pt）で決まるんです。多く含む機器ほど高ポイントですね（例：スマホ12pt・モバイルバッテリー31pt・ノートPC42pt）。付与は、りなれすに届いて確認できたあとになります。",
                "kurosuke": "{nickname}、ポイントは端末ごとのリチウム量の目安（0.1gにつき1pt）で決まります。多いほど高ポイントです。例：スマホ12pt、モバイルバッテリー31pt、ノートPC42pt。付与は受領・確認後です。",
                "miirin": "{nickname}、ポイントは端末ごとのリチウムイオン電池のリチウム量の目安（0.1gで1pt）で決まるんやで！多いほど高ポイントや（例：スマホ12pt・モバイルバッテリー31pt・ノートPC42pt）。付与は届いて確認できたあとやで〜",
                "hiroji": "{nickname}さん、ポイントはな、端末ごとの内蔵リチウムイオン電池のリチウム量の目安（0.1gにつき1pt）で決まるのじゃよ。多く含むほど高ポイントじゃ（例：スマホ12pt・モバイルバッテリー31pt・ノートPC42pt）。付与は、りなれすに届いて確認できたあとじゃな。",
                "teraoman": "{nickname}、ポイントは端末ごとのリチウムイオン電池のリチウム量の目安（0.1gにつき1pt）で決まるんだ！多く含むほど高ポイントだぞ（例：スマホ12pt・モバイルバッテリー31pt・ノートPC42pt）。付与は、りなれすに届いて確認できたあとだ！",
            },
        },
        {
            "category": "points",
            "question": "ポイントは何に使えますか？",
            "keywords": "ポイント 使い道,ランク,特典",
            "variants": {
                "riji": "{nickname}、貯めたポイントでランクが上がって、オレのコメントがどんどん特別になるっす！いっぱい貯めて仲良くなろうっす〜",
                "taka": "{nickname}さん、貯めたポイントに応じてランクが上がって、ぼくからのコメントもどんどん特別になっていくんです。たくさん貯めて、もっと仲良くなれたらうれしいです。",
                "kurosuke": "{nickname}、ポイントに応じてランクが上がります。上がるほど、私のコメントも特別になります。",
                "miirin": "{nickname}、貯めたポイントでランク上がって、うちのコメントがどんどん特別になるで！いっぱい貯めて、もっと仲良うなろな〜",
                "hiroji": "{nickname}さん、貯めたポイントに応じてランクが上がってな、わしのコメントもどんどん特別になっていくのじゃよ。まぁ、たくさん貯めて仲良うしようぞ。",
                "teraoman": "{nickname}、貯めたポイントでランクが上がって、オレのコメントもどんどん特別になるぞ！たくさん貯めて、もっと仲良くなろうな！",
            },
        },
        # ---------- データ消去 ----------
        {
            "category": "data_erase",
            "question": "データはちゃんと消去されますか？",
            "keywords": "データ,消去,情報,漏洩,消える",
            "variants": {
                "riji": "{nickname}、安心してほしいっす！提携業者が専用ソフトで完全にデータ消去してくれるっす。終わったら証明書も出るから、{nickname}の大事な情報はしっかり守られるっす。",
                "taka": "{nickname}さん、安心してくださいね。提携業者が専用ソフトを使って完全にデータを消去してくれます。消去が終わると証明書も発行されるので、{nickname}さんの大事な情報はしっかり守られますよ。",
                "kurosuke": "{nickname}、ご安心ください。提携業者が専用ソフトで完全に消去します。完了後、証明書も発行されます。{nickname}の情報は守られます。",
                "miirin": "{nickname}、安心してや！提携業者が専用ソフトで完全にデータ消してくれるで。終わったら証明書も出るから、{nickname}の大事な情報はしっかり守られるで〜",
                "hiroji": "{nickname}さん、安心なされ。提携業者が専用ソフトでな、完全にデータを消去してくれるのじゃよ。終われば証明書も発行される。{nickname}さんの大事な情報はしっかり守られるでな。",
                "teraoman": "{nickname}、安心しろ！提携業者が専用ソフトで完全にデータを消去してくれるぞ。終わったら証明書も出る。{nickname}の大事な情報はオレたちがしっかり守るからな！",
            },
        },
        {
            "category": "data_erase",
            "question": "初期化してから送った方がいいですか？",
            "keywords": "初期化,リセット,工場出荷",
            "variants": {
                "riji": "{nickname}、初期化しなくてOKっす！提携業者が専用ソフトで完全消去してから処理するっす。そのまま送って安心してほしいっす。",
                "taka": "{nickname}さん、初期化しなくても大丈夫ですよ。提携業者が専用ソフトでデータを完全に消去してから処理してくれるので、そのまま送って安心してくださいね。",
                "kurosuke": "{nickname}、初期化は不要です。提携業者が専用ソフトで完全消去してから処理します。そのまま送ってください。",
                "miirin": "{nickname}、初期化せんでも大丈夫やで！提携業者が専用ソフトで完全に消してから処理してくれるから、そのまま送って安心してな〜",
                "hiroji": "{nickname}さん、初期化はせんでも良いのじゃよ。提携業者が専用ソフトで完全に消去してから処理してくれるでな。そのまま送って安心なされ。",
                "teraoman": "{nickname}、初期化はしなくていいんだ！提携業者が専用ソフトで完全消去してから処理するぞ。そのまま送って安心してくれ！",
            },
        },
        {
            "category": "data_erase",
            "question": "消去証明はもらえますか？",
            "keywords": "証明,証明書,消去証明",
            "variants": {
                "riji": "{nickname}、データ消去後にちゃんと消去証明が発行される仕組みっす！{nickname}の安心のために、しっかり対応するっす。",
                "taka": "{nickname}さん、データ消去のあとには、ちゃんと消去証明が発行される仕組みになっています。{nickname}さんの安心のために、しっかり対応させてもらいますね。",
                "kurosuke": "{nickname}、消去後に消去証明を発行します。{nickname}のために、確実に対応します。",
                "miirin": "{nickname}、データ消したあとに、ちゃんと消去証明が出る仕組みになってるで！{nickname}の安心のために、しっかり対応するからな〜",
                "hiroji": "{nickname}さん、データ消去のあとにな、ちゃんと消去証明が発行される仕組みなのじゃよ。{nickname}さんの安心のために、しっかり対応するでな。",
                "teraoman": "{nickname}、データ消去のあとに、消去証明がちゃんと発行される仕組みだ！{nickname}の安心のために、オレがしっかり対応するぞ！",
            },
        },
        {
            "category": "data_erase",
            "question": "写真や連絡先も消えますか？",
            "keywords": "写真,連絡先,個人情報",
            "variants": {
                "riji": "{nickname}、写真も連絡先も専用ソフトで完全消去するっす！心配いらないっす、安心してりなれすに任せてほしいっす。",
                "taka": "{nickname}さん、写真や連絡先も含めて専用ソフトで完全に消去するので、心配いりませんよ。安心してりなれすに任せてくださいね。",
                "kurosuke": "{nickname}、写真も連絡先も専用ソフトで完全に消去します。心配いりません。お任せください。",
                "miirin": "{nickname}、写真も連絡先も専用ソフトで完全に消すから、心配いらんで！安心してりなれすに任せてな〜",
                "hiroji": "{nickname}さん、写真も連絡先も含めてな、専用ソフトで完全消去するのじゃよ。心配いらん。安心してりなれすに任せなされ。",
                "teraoman": "{nickname}、写真も連絡先も専用ソフトで完全消去するぞ！心配いらないんだ、安心してりなれすに任せてくれ！",
            },
        },
    ]

    for faq in faq_data:
        existing = db.query(FaqEntry).filter(FaqEntry.question == faq["question"]).first()

        # 代表 answer を決める（faq["answer"] があればそれを採る、無ければ variants の先頭を代表にする）
        canonical_answer = faq.get("answer")
        if not canonical_answer:
            variants = faq.get("variants") or {}
            canonical_answer = next(iter(variants.values()), None) or ""

        if existing is None:
            entry = FaqEntry(
                category=faq["category"],
                question=faq["question"],
                keywords=faq["keywords"],
                answer=canonical_answer,
            )
            db.add(entry)
            db.flush()  # entry.id を確定させる
        else:
            existing.category = faq["category"]
            existing.keywords = faq["keywords"]
            existing.answer = canonical_answer
            entry = existing

        # variants の upsert（存在すれば更新、無ければ挿入）
        variants = faq.get("variants") or {}
        for idol_id, var_answer in variants.items():
            fv = (
                db.query(FaqVariant)
                .filter(
                    FaqVariant.faq_entry_id == entry.id,
                    FaqVariant.idol_id == idol_id,
                )
                .first()
            )
            if fv is None:
                db.add(
                    FaqVariant(
                        faq_entry_id=entry.id,
                        idol_id=idol_id,
                        answer=var_answer,
                        generated_by="seed",
                    )
                )
            else:
                fv.answer = var_answer
                fv.generated_by = "seed"


def _seed_idol_comments(db: Session) -> None:
    """
    アイドル別×ランク別のコメントテンプレートを投入する（コード内定義）。
    
    各アイドルに対してランク 1〜3 のテンプレートを複数設定し、
    存在しなければ追加する（重複挿入を防ぐ）。
    
    形式: { "idol_id": { "1": ["...", "..."], "2": [...], ... } }
    """

    idol_comments_data = {
        "riji": {
            "1": [
                "{nickname}、はじめまして！これからよろしくっす♪",
                "{nickname}が来てくれて嬉しいっす。少しずつ仲良くなろうっす！",
                "{nickname}、デバイスの登録ありがとう！応援してるっす！",
            ],
            "2": [
                "{nickname}、いつも協力してくれてありがとうっす！すごく頼りにしてるっす！",
                "{nickname}のおかげでポイントも順調っすね。もっと一緒に頑張ろうっす！",
                "{nickname}とはもうすっかり仲良しな気がするっす！これからもよろしくっす♪",
            ],
            "3": [
                "{nickname}、大好きっす！いつも一番の味方でいてくれてありがとう！！",
                "{nickname}となら都市鉱山だってどこまでも掘り進めちゃう気がするっす！",
                "{nickname}はオレにとって特別な存在っす。本当にありがとう、大好きっす！",
            ],
        },
        "taka": {
            "1": [
                "{nickname}さん、はじめまして。ぼくと一緒に進みましょう。",
                "{nickname}さんが来てくれて嬉しいです。少しずつ仲良くなっていきたいです。",
                "{nickname}さん、デバイスの登録ありがとうございます。応援しています！",
            ],
            "2": [
                "{nickname}さん、いつも協力してくれてありがとうございます。すごく頼りにしています。",
                "{nickname}さんのおかげでポイントも順調ですね。もっと一緒に頑張りましょう。",
                "{nickname}さんとはもうすっかり仲良しな気がします。これからもよろしくお願いします。",
            ],
            "3": [
                "{nickname}さん、大好きです。いつも一番の味方でいてくれてありがとうございます。",
                "{nickname}さんとなら都市鉱山だってどこまでも進めそうな気がします。",
                "{nickname}さんはぼくにとって特別な存在です。本当にありがとうございます、大好きです。",
            ],
        },
        "kurosuke": {
            "1": [
                "{nickname}、はじめまして。これからよろしくお願いします。",
                "{nickname}が来てくれて良かった。仲良くしましょう。",
                "{nickname}、デバイスの登録ありがとうございます。応援します。",
            ],
            "2": [
                "{nickname}、いつも協力してくれてありがとうございます。頼りにしています。",
                "{nickname}のおかげでポイントも順調です。もっと頑張りましょう。",
                "{nickname}とはもう良い関係ですね。これからもよろしくお願いします。",
            ],
            "3": [
                "{nickname}、大好きです。いつも支えてくれてありがとうございます。",
                "{nickname}となら何でも成し遂げられそうです。本当にありがとう。",
                "{nickname}は私にとって大切な人です。心から感謝しています。",
            ],
        },
        "miirin": {
            "1": [
                "{nickname}、よろしくな！これからいっしょに頑張ろぜ！",
                "{nickname}が来てくれて嬉しいで。仲良うしようや！",
                "{nickname}、デバイスの登録ありがとう。応援してるで〜",
            ],
            "2": [
                "{nickname}、いつも協力してくれてありがとうな！頼りにしてるで！",
                "{nickname}のおかげでポイントも順調やな。もっと一緒に頑張ろぜ！",
                "{nickname}とはもうすっかり仲良しやな。これからもよろしくな〜",
            ],
            "3": [
                "{nickname}、大好きや！いつも一番の味方でいてくれてありがとう！！",
                "{nickname}となら都市鉱山だってどこまでも掘り進めちゃう気がするで！",
                "{nickname}はうちにとって特別な存在や。本当にありがとう、大好きやで！",
            ],
        },
        "hiroji": {
            "1": [
                "{nickname}さん、はじめまして。これからよろしくのう。",
                "{nickname}さんが来てくれて良かったのう。仲良うしようぞ。",
                "{nickname}さん、デバイスの登録ありがとうぞ。応援しとるで。",
            ],
            "2": [
                "{nickname}さん、いつも協力してくれてありがとうのう。頼りにしとるで。",
                "{nickname}さんのおかげでポイントも順調じゃな。もっと一緒に頑張ろうぞ。",
                "{nickname}さんとはもう良い関係じゃな。これからもよろしくのう。",
            ],
            "3": [
                "{nickname}さん、大好きじゃ。いつも支えてくれてありがとうのう。",
                "{nickname}さんとなら何でも成し遂げられそうじゃ。本当にありがとうぞ。",
                "{nickname}さんは我にとって大切な人じゃ。心から感謝しておるで。",
            ],
        },
        "teraoman": {
            "1": [
                "{nickname}、よろしくな！一緒に頑張ろうぜ！",
                "{nickname}が来てくれて嬉しいぞ。仲良くしような！",
                "{nickname}、デバイスの登録ありがとう。応援してるぞ！",
            ],
            "2": [
                "{nickname}、いつも協力してくれてありがとうな！頼りにしてるぞ！",
                "{nickname}のおかげでポイントも順調だ。もっと一緒に頑張ろうぜ！",
                "{nickname}とはもうすっかり仲良しだな。これからもよろしくな〜",
            ],
            "3": [
                "{nickname}、大好きだ！いつも一番の味方でいてくれてありがとう！！",
                "{nickname}となら都市鉱山だってどこまでも掘り進めちゃう気がするぞ！",
                "{nickname}はオレにとって特別な存在だ。本当にありがとう、大好きだぞ！",
            ],
        },
    }

    for idol_id, ranks in idol_comments_data.items():
        for rank_str, templates in ranks.items():
            try:
                rank = int(rank_str)
            except ValueError:
                continue

            for template in templates:
                # 同一 idol_id + rank + template が無ければ追加（重複防止）
                existing = (
                    db.query(IdolComment)
                    .filter(
                        IdolComment.idol_id == idol_id,
                        IdolComment.rank == rank,
                        IdolComment.template == template,
                    )
                    .first()
                )
                if existing is None:
                    db.add(IdolComment(idol_id=idol_id, rank=rank, template=template))
