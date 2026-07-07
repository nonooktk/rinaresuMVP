"""
初期データ投入モジュール。

アプリ起動時に呼び出され、既にデータが存在する場合は何もしない（冪等）。
アイドル6人・コメントテンプレ・デバイス種別マスタ・FAQを投入する。
"""
from sqlalchemy.orm import Session

from app.models import DeviceType, FaqEntry, Idol, IdolComment


def seed_all(db: Session) -> None:
    """全seedデータを投入する（冪等）。"""
    _seed_idols(db)
    _seed_device_types(db)
    _seed_faq(db)
    db.commit()


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


def _seed_device_types(db: Session) -> None:
    """デバイス種別マスタを投入する。"""
    if db.query(DeviceType).count() > 0:
        return

    device_types = [
        {"code": "smartphone", "label": "スマートフォン", "weight_g": 170, "points": 17},
        {"code": "feature_phone", "label": "ガラケー", "weight_g": 100, "points": 10},
        {"code": "tablet", "label": "タブレット", "weight_g": 450, "points": 45},
        {"code": "camera", "label": "デジタルカメラ", "weight_g": 300, "points": 30},
        {"code": "portable_game", "label": "携帯ゲーム機", "weight_g": 250, "points": 25},
        {"code": "other", "label": "その他小型家電", "weight_g": 100, "points": 10},
    ]
    for dt in device_types:
        db.add(DeviceType(**dt))


def _seed_faq(db: Session) -> None:
    """FAQエントリを投入する（送付方法・ポイント・データ消去の3カテゴリ各3件以上）。"""
    if db.query(FaqEntry).count() > 0:
        return

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
            "keywords": "計算,何ポイント,ポイント数,重さ,重量",
            "answer": (
                "{nickname}、目安は10gにつき1ポイントだよ！"
                "デバイスの種類によって想定重量が決まっていて、それに応じてポイントが決まるんだ。"
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
        db.add(FaqEntry(**faq))
