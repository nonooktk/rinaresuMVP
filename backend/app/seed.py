"""
初期データ投入モジュール。

アプリ起動時に呼び出され、**毎回 upsert として通る**（冪等）。
アイドル6人・キャラ別コメントテンプレ・キャラ別ログインボーナス文言・
デバイス種別マスタ・FAQ を投入する。

【重要】従来 `_seed_idols` は「1件でもあればスキップ」だったため、コード側の文言を
書き換えても既存 DB（本番・稼働中ローカル）には一生反映されなかった。
`_seed_device_types` / `_seed_faq` で実績のある upsert 方式にそろえ、
**再起動するだけで既存 DB も最新の文言へ移行する**ようにしている（DESIGN_D-4 §8 #2）。
"""
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.limited_idol import LIMITED_IDOL
from app.models import DeviceType, FaqEntry, Idol, IdolComment, IdolLoginLine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- アイドル名簿

# id はフロントエンドのイラストディレクトリ（public/idols/{id}/）と対応するスラッグ。
# 全6人とも支給イラスト（main.png・背景透過済み）配置済み。
IDOLS_DATA: list[dict] = [
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

# ---------------------------------------------------------------- ホームの吹き出し

# キャラ別コメントテンプレ（7人 × ランク1〜3 × 各3文 ＝ 63文）。文言の正本は
# 02_プロジェクト/rinaresu/DESIGN_D-4_character-voice.md §2。
#
# 3文はスロット制（D-4 §2.1）:
#   ①関係の宣言 ②並走・未来 ③アプリ文脈（ランク1=登録/端末・2=今月の成果・3=あなたは特別）
# ランクが上がるほど親密になる構造と {nickname} プレースホルダーは従来どおり。
# {nickname} は1文に必ず1回だけ（D-4 §4.2）。
IDOL_COMMENT_TEMPLATES: dict[str, dict[int, list[str]]] = {
    # 金城ほむら: 一人称「ほむら」／♪ 可・♡ 不可／光・金色・ステージの語彙
    "homura": {
        1: [
            "{nickname}、はじめまして！ ほむらとキラキラ集めよう♪",
            "{nickname}が来てくれた！ 今日もいいことありそう♪",
            "{nickname}、とうろくありがとう！ ほむら、ちゃんと見てるからね",
        ],
        2: [
            "{nickname}、いつもありがとう！ すっかり頼りにしてるよ♪",
            "{nickname}とならもっと上を目指せる気がする！ いっしょに行こ♪",
            "{nickname}のおかげで今月もキラキラだよ♪ ほむら、うれしい！",
        ],
        3: [
            "{nickname}、大好き！ 一番の味方でいてくれてありがとう♪",
            "{nickname}となら、どんなステージも光らせられる気がするよ♪",
            "{nickname}がいるから、ほむらはずっと金色でいられるの。ありがとう！",
        ],
    },
    # 紅谷美野里: 一人称「美野里」／小さい「っ」で押す／♪♡ 不可／炎・走るの語彙
    "minori": {
        1: [
            "{nickname}、はじめまして！ 美野里、全力でいくよっ！",
            "{nickname}が来てくれて、美野里のハートに火がついたっ！",
            "{nickname}、とうろくありがとうっ！ その一台、ちゃんと届けるね！",
        ],
        2: [
            "{nickname}、いつもありがとうっ！ 美野里、本気で頼りにしてるよ！",
            "{nickname}とならどこまでも走れる！ ペース、合わせるからねっ！",
            "{nickname}のがんばり、美野里ぜんぶ見てたよっ！ 今月もすごい！",
        ],
        3: [
            "{nickname}、大好きっ！ この一直線の気持ち、受け取ってね！",
            "{nickname}となら、美野里はもう何もこわくないよっ！",
            "{nickname}は美野里のまんなかにいる人だよ。ずっとありがとうっ！",
        ],
    },
    # 奏多紫苑: 一人称「わたし」／感嘆符をほぼ使わない／♪♡ 不可／星・夜空の語彙
    "shion": {
        1: [
            "{nickname}、はじめまして。今夜から、同じ星を見ようね",
            "{nickname}が来てくれた日は、少しだけ空が明るいの",
            "{nickname}、登録ありがとう。ひとつずつ、星が増えるみたいね",
        ],
        2: [
            "{nickname}、いつもありがとう。わたしの空、また少し広くなったの",
            "{nickname}と歩く夜道は、不思議とこわくないのよ",
            "{nickname}のおかげで、今月の空はずいぶんにぎやかね",
        ],
        3: [
            "{nickname}、大好き。この気持ちは、たぶん星より遠くまで届くの",
            "{nickname}となら、どんなに暗い夜でも歌えるよ",
            "{nickname}はわたしにとって、いちばん近くで光っている星なの",
        ],
    },
    # 蒼乃美帆: 一人称「美帆」／♪♡ 不可／歌・声・澄む・流れの語彙
    "miho": {
        1: [
            "{nickname}、はじめまして！ 美帆の歌、まっすぐ届けるね！",
            "{nickname}が来てくれて、心がすうっと澄んだ気がするよ！",
            "{nickname}、登録ありがとう！ ここから一緒にはじめよう！",
        ],
        2: [
            "{nickname}、いつもありがとう！ 美帆、すごく心強いよ！",
            "{nickname}と重ねる声は、ひとりのときよりずっときれいだね！",
            "{nickname}のおかげで、今月もいい流れがきてるよ！",
        ],
        3: [
            "{nickname}、大好き！ 美帆の歌は、ぜんぶここに届けにきてるの！",
            "{nickname}となら、どこまでも澄んだ音が出せる気がするよ！",
            "{nickname}は美帆にとって、いちばんあたたかい場所だよ。ありがとう！",
        ],
    },
    # 桃宮ゆかり: 一人称「ゆかりん」／♪♡〜 多用（1文に合計2つまで）／擬音・甘えの語彙
    "yukari": {
        1: [
            "{nickname}、はじめまして〜♪ ゆかりん、なかよくしたいなっ",
            "{nickname}が来てくれた〜！ ゆかりんパワー、ちゅうにゅ〜♪",
            "{nickname}、とうろくありがと♡ これからよろしくね〜！",
        ],
        2: [
            "{nickname}、いつもありがと〜♪ ゆかりん、ちょっと甘えちゃうね",
            "{nickname}といると、ゆかりんずっとにこにこなの♡",
            "{nickname}のおかげで今月もいい感じ〜！ えらすぎるよ♪",
        ],
        3: [
            "{nickname}、大好き〜っ♡ ゆかりん、ぎゅ〜ってしたい気分なの",
            "{nickname}となら、どこまでもふたりでいけちゃう気がする♪",
            "{nickname}はゆかりんのいちばん。ぜったい離さないもん♡",
        ],
    },
    # 長岡イーサン（唯一の男性）: 一人称「俺」／**♪♡〜 すべて不可**／道具・時間・預かるの語彙。
    # 感情の段階を1段遅らせ、ランク3で初めて口にする。他6人と違い「大好き」は使わない（D-4 §5）。
    "ethan": {
        1: [
            "{nickname}、はじめまして。まずは肩の力を抜いていこうか",
            "{nickname}が来てくれたか。ちょうど待ってたところだ",
            "{nickname}、登録ありがとう。その端末、俺が責任もって預かる",
        ],
        2: [
            "{nickname}、いつも助かってる。正直、かなり頼りにしてるんだ",
            "{nickname}のペースでいい。俺はちゃんと横で見てるからな",
            "今月もよくやったな、{nickname}。手を抜かないところがいい",
        ],
        3: [
            "{nickname}、大事に思ってる。こういうこと、普段は言わないんだけどな",
            "{nickname}となら、まだ先まで行ける気がする。付き合ってくれるか？",
            "{nickname}がいるから、俺はここに立っていられる。ありがとうな",
        ],
    },
}

# 限定推し用の中立コメント（ランク→3文）。
# 【DESIGN_D-4 §6.2 原則2】限定推しの文言（LIMITED_IDOL["comments"]）を用意し忘れても、
# API フォールバックの「{nickname}、いつもありがとう！」1文固定にならないようにするための既定値。
# 内容は D-4 以前の全アイドル共通テンプレ（中立口調）をそのまま流用している。
NEUTRAL_COMMENT_TEMPLATES: dict[int, list[str]] = {
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

# ---------------------------------------------------------------- ログインボーナス文言

# キャラ別ログインボーナス文言（6人分・5フィールド）。文言の正本は DESIGN_D-4 §3.3。
# 限定推しぶんは backend/app/limited_idol.py の LIMITED_IDOL["login_lines"] に同居させている
# （差し替え箇所を1ファイルに寄せるため。D-4 §6.2 原則3）。
#
# **pt 値には一切依存しない**（pt 別のサブコピーはキャラ非依存の定数としてフロントが持つ）。
# キャラ軸と pt 軸を交差させないことで、キャラ追加は +1行・pt 帯追加は +1文で済む（D-4 §3.1）。
IDOL_LOGIN_LINES: dict[str, dict[str, str]] = {
    "homura": {
        "greet1": "{nickname}、今日も会いにきてくれてありがとう♪",
        "greet2": "ほむらからの気持ち、受け取ってね！",
        "envelope": "はい、これ。あけてみて…♪",
        "result1": "{points}ptをゲットしたよ♪",
        "result2": "また明日も会いにきてね！",
        "already": "今日のぶんは もう受け取ってるみたい…！ また明日ね♪",
    },
    "minori": {
        "greet1": "{nickname}、今日も会いにきてくれてありがとうっ！",
        "greet2": "美野里の気持ち、まっすぐ受け取ってね！",
        "envelope": "はいっ、これ！ あけてみて！",
        "result1": "{points}ptをゲットだよっ！",
        "result2": "また明日も会いにきてねっ！",
        "already": "今日のぶんは もう渡しちゃったっ！ また明日ねっ！",
    },
    "shion": {
        "greet1": "{nickname}、今日も会いにきてくれてありがとう",
        "greet2": "わたしからの気持ち、受け取ってね",
        "envelope": "はい、これ。あけてみて…",
        "result1": "{points}ptをゲットしたよ",
        "result2": "また明日も会いにきてね。待ってる",
        "already": "今日のぶんは、もう渡したみたい…。また明日ね",
    },
    "miho": {
        "greet1": "{nickname}、今日も会いにきてくれてありがとう！",
        "greet2": "美帆からの気持ち、受け取ってね！",
        "envelope": "はい、これ。あけてみて…！",
        "result1": "{points}ptをゲットしたよ！",
        "result2": "また明日も会いにきてね！",
        "already": "今日のぶんは もう受け取ってるみたい…！ また明日ね",
    },
    "yukari": {
        "greet1": "{nickname}、今日も会いにきてくれてありがと〜♡",
        "greet2": "ゆかりんの気持ち、受け取ってね♪",
        "envelope": "はい、これ♡ あけてみて〜",
        "result1": "{points}ptゲットだよ〜♪",
        "result2": "また明日も会いにきてね♡",
        "already": "今日のぶんは もうあげちゃった〜！ また明日ね♡",
    },
    # イーサンのみ ♪ ♡ 〜（伸ばし棒）を一切使わない（D-4 §1.6・§5-3）
    "ethan": {
        "greet1": "{nickname}、今日も会いにきてくれてありがとうな",
        "greet2": "俺からの気持ち、受け取ってくれ",
        "envelope": "ほら、これ。開けてみてくれ",
        "result1": "{points}ptをゲットだ！",
        "result2": "また明日も顔を見せてくれ",
        "already": "今日のぶんは、もう渡したあとみたいだな。また明日だ",
    },
}

# キャラ未定義 slug 用のフォールバック（DESIGN_D-4 §3.3 DEFAULT）。
# 内容は DESIGN_D-3 §3.1 の確定文言そのまま（「私」表記＝ D-3 §9-1 の決着を保持）。
# 限定推しが月替わりで差し替わり文言が未用意でも、ここに落ちるので画面は壊れない。
DEFAULT_LOGIN_LINES: dict[str, str] = {
    "greet1": "{nickname}、今日も会いにきてくれてありがとう♡",
    "greet2": "私からの気持ち、受け取ってね！",
    "envelope": "はい、これ。あけてみて…♡",
    "result1": "{points}ptをゲットしたよ！",
    "result2": "また明日も会いにきてね！",
    "already": "今日のぶんは もう受け取ってるみたい…！ また明日ね♡",
}

# ---------------------------------------------------------------- 入力の正規化

# 有効なランク（吹き出しは 1〜3 のみ。ユーザーの rank カラムと対応する）
VALID_RANKS = (1, 2, 3)


def _normalize_login_lines(idol_id: str, raw: object) -> dict[str, str]:
    """運営が書いたログボ文言を検証し、安全な形に正規化する。

    【QA_Q-8 M-1 対応】従来は `IdolLoginLine(idol_id=..., **lines)` と**無検証で展開**していたため、
    運営が `limited_idol.py` を書き間違えると **バックエンドが起動不能**になっていた。
      - キーを1つ落とす → `IntegrityError: NOT NULL constraint failed` で `on_startup` 失敗
      - キー名のタイポ（`greet_1`）→ `TypeError: invalid keyword argument` で同じく起動不能
      - 一方「キーを丸ごと省略」は DEFAULT に落ちて救われる、という非対称があった
    運営が現実に踏むのは「5つ書いて1つ忘れる」側なので、**壊れない側へ倒す**
    （DESIGN_D-4 §6.2 原則2「文言を用意し忘れても画面は壊れない」）。

    さらに、既存 slug は update パス（`setattr`）を通るため**タイポが無言で無視**され、
    運営が「直したのに反映されない」状態に陥っていた。ここで正規化してから
    insert / update の**両パスで同じ dict を使う**ことで挙動をそろえ、
    捨てた入力は必ず**警告ログ**に出して気づけるようにする。

    - `dict` でない（None・リスト等）→ まるごと DEFAULT
    - 未知キー → 無視（警告）
    - 不足キー・空文字・非 str → DEFAULT の値で補完（警告）
    """
    if not isinstance(raw, dict):
        if raw is not None:
            logger.warning(
                "[seed] %s の login_lines が dict ではありません（%s）。"
                "DEFAULT_LOGIN_LINES を使います",
                idol_id,
                type(raw).__name__,
            )
        return dict(DEFAULT_LOGIN_LINES)

    unknown = [k for k in raw if k not in DEFAULT_LOGIN_LINES]
    if unknown:
        logger.warning(
            "[seed] %s の login_lines に未知のキーがあります: %s（無視します。"
            "キー名のタイポの可能性があります。有効なキー: %s）",
            idol_id,
            ", ".join(sorted(map(str, unknown))),
            ", ".join(DEFAULT_LOGIN_LINES),
        )

    normalized: dict[str, str] = {}
    missing: list[str] = []
    for field, default in DEFAULT_LOGIN_LINES.items():
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            normalized[field] = value
        else:
            normalized[field] = default
            missing.append(field)
    if missing:
        logger.warning(
            "[seed] %s の login_lines に欠落・不正な値があります: %s"
            "（DEFAULT_LOGIN_LINES の文言で補完しました）",
            idol_id,
            ", ".join(missing),
        )
    return normalized


def _normalize_comments(
    idol_id: str, raw: object, fallback: dict[int, list[str]]
) -> dict[int, list[str]]:
    """運営が書いた吹き出しコメントを検証し、安全な形に正規化する。

    【QA_Q-8 m-1 対応】従来の `LIMITED_IDOL.get("comments") or NEUTRAL_COMMENT_TEMPLATES` は、
    `{1: [], 2: [], 3: []}`（空配列）が **truthy なので `or` を素通り**し、期待セットが空＝
    コメント0件になっていた（画面は API フォールバックの1文固定に戻る）。
    **「キーがあるか」ではなく「中身が1文以上あるか」で判定する。**

    【QA_Q-8 m-2 対応】ランク値・型が無検証で、`rank=4`（誰にも引かれない死にデータ）や
    数値がそのまま DB に入っていた。数値は SQLite では暗黙変換されるが
    **PostgreSQL では型エラーで起動失敗しうる**（Q-8 C-1）。ここで弾く。

    - ランクは 1〜3 のみ／値は非空の str のみ（外れたものは警告して捨てる）
    - **どれか1つでも 0 件のランクが残ったら、全体を fallback に落とす**
      （「ランク2・3 のユーザーだけ 0 件」という静かな劣化を防ぐ）
    """
    if not isinstance(raw, dict):
        if raw is not None:
            logger.warning(
                "[seed] %s の comments が dict ではありません（%s）。既定の文言を使います",
                idol_id,
                type(raw).__name__,
            )
        return fallback

    normalized: dict[int, list[str]] = {rank: [] for rank in VALID_RANKS}
    dropped: list[str] = []
    for rank, templates in raw.items():
        if rank not in VALID_RANKS:
            dropped.append(f"rank={rank!r}（有効なランクは 1〜3）")
            continue
        if not isinstance(templates, (list, tuple)):
            dropped.append(f"rank={rank} の値がリストではありません")
            continue
        for template in templates:
            if isinstance(template, str) and template.strip():
                normalized[rank].append(template)
            else:
                dropped.append(f"rank={rank} の要素 {template!r}（非文字列または空）")

    if dropped:
        logger.warning(
            "[seed] %s の comments に不正な入力があります: %s（無視しました）",
            idol_id,
            " / ".join(dropped),
        )

    empty = [rank for rank in VALID_RANKS if not normalized[rank]]
    if empty:
        logger.warning(
            "[seed] %s の comments はランク %s が0件です。既定の文言に切り替えます"
            "（一部ランクだけ吹き出しが出ない状態を避けるため）",
            idol_id,
            ", ".join(map(str, empty)),
        )
        return fallback
    return normalized


# ---------------------------------------------------------------- 並行起動への防御

# seed 全体を直列化するためのアドバイザリロックのキー（PostgreSQL のみ）。
# 任意の 64bit 整数。他所で使わない固定値にする。
_SEED_LOCK_KEY = 0x72696E61  # "rina"


def _acquire_seed_lock(db: Session) -> None:
    """seed 全体をプロセス間で直列化する。

    【R-4 M-1 対応】`_sync_idol_comments` は「読取→差分判定→insert/delete」なので、
    複数プロセスが同時に `seed_all()` を走らせると、双方が「不足」と判定して同じ行を
    insert し重複が残る／`idol_login_lines` は主キー競合で `seed_all` 全体が
    `IntegrityError` で落ちる、という事故が起こりうる。
    **Container Apps のローリング更新では新リビジョンが起動してから旧が落ちる**ため、
    デプロイのたびに一時的に2プロセスが同時起動する。しかも今回は delete を含む処理なので
    運用任せにはできない。

    - PostgreSQL: `pg_advisory_xact_lock` を取る。**トランザクション終了で自動解放**されるため、
      末尾で1回だけ commit する `seed_all` の構造とそのまま噛み合う。
    - SQLite: 単一ライタなので、**差分を読む前に書込ロックを取ってしまう**。
      値を変えない UPDATE（`SET name = name`）でロックだけ取得する（データには影響しない）。
    - その他の方言: 何もしない（後段の savepoint 隔離で最低限の安全性は担保する）。
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _SEED_LOCK_KEY})
    elif dialect == "sqlite":
        # 空テーブル（初回起動）では 0 行更新でロックを取れないことがあるが、
        # その場合も _insert_safely の savepoint 隔離で衝突を吸収できる。
        db.execute(text("UPDATE idols SET name = name"))


def _insert_safely(db: Session, obj: object) -> bool:
    """他プロセスが同じ行を先に入れていても落ちないように savepoint 隔離で INSERT する。

    【R-4 M-1 対応】衝突（`IntegrityError`）した場合は **その savepoint だけ**ロールバックし、
    「相手の結果を受け入れる」意味で False を返す。外側のトランザクションは無傷なので、
    seed_all 全体が落ちることはない。前スプリントの R-1 B-1／QA B2-1 と同じ流儀。
    """
    try:
        with db.begin_nested():
            db.add(obj)
            db.flush()
        return True
    except IntegrityError:
        return False


# ---------------------------------------------------------------- seed 本体


def seed_all(db: Session) -> None:
    """全seedデータを投入する（**毎起動で通る upsert**・冪等・並行起動でも落ちない）。"""
    _acquire_seed_lock(db)
    _seed_idols(db)
    _seed_limited_idol(db)
    _seed_legacy_limited_idols(db)
    _seed_device_types(db)
    _seed_faq(db)
    db.commit()


def _sync_idol_comments(
    db: Session, idol_id: str, templates_by_rank: dict[int, list[str]]
) -> None:
    """指定アイドルの吹き出しコメントを期待セットへ同期する（冪等）。

    `IdolComment` には自然キーが無い（同じ文言を複数持てる構造）ため、
    **`(rank, template)` の集合そのものをキーとみなして期待セットと突き合わせる**方式を採る。
    テーブルは1アイドルあたり9行と小さいので、全件読んで差分を取っても負荷にならない。

      - 期待セットに無い既存行 → delete（旧・全アイドル共通テンプレはここで消える＝移行）
      - 既存に無い期待行       → insert
      - 一致する行             → そのまま残す（2回目以降の起動は無変更＝行が増殖しない）

    **対象アイドルの行だけ**を触る。過去 slug の限定推し（seira 等）のコメントは
    別 idol_id なので残置される（DESIGN_D-4 §6.3「過去 slug の文言は消してはいけない」）。
    純 ORM 操作のため SQLite / PostgreSQL 両対応。
    """
    expected: set[tuple[int, str]] = {
        (rank, template)
        for rank, templates in templates_by_rank.items()
        for template in templates
    }

    kept: set[tuple[int, str]] = set()
    for row in db.query(IdolComment).filter(IdolComment.idol_id == idol_id).all():
        key = (row.rank, row.template)
        if key in expected and key not in kept:
            kept.add(key)  # 期待どおりの行は残す
        else:
            db.delete(row)  # 期待外（旧文言）または重複行は削除する

    for rank, template in expected - kept:
        # 【R-4 M-1】並行 seed で相手が先に同じ行を入れていても落ちないよう savepoint 隔離
        _insert_safely(db, IdolComment(idol_id=idol_id, rank=rank, template=template))


def _sync_login_lines(db: Session, idol_id: str, lines: dict[str, str]) -> None:
    """指定アイドルのログインボーナス文言を upsert する（冪等）。

    `idol_id` が主キーなので素直な upsert で足りる。渡される `lines` は
    `_normalize_login_lines` で検証済みの6キーであることを前提とする
    （呼び出し側で必ず通すこと。無検証の dict をそのまま展開しない＝ QA_Q-8 M-1）。
    """
    existing = db.get(IdolLoginLine, idol_id)
    if existing is None:
        # 【R-4 M-1】並行 seed での主キー競合を savepoint で吸収し、
        # 負けた側は相手が入れた行を読み直して update に回る。
        if _insert_safely(db, IdolLoginLine(idol_id=idol_id, **lines)):
            return
        existing = db.get(IdolLoginLine, idol_id)
        if existing is None:
            return
    for field, value in lines.items():
        setattr(existing, field, value)


def _seed_limited_idol(db: Session) -> None:
    """期間限定推し（7人目・T1特典）を upsert する（idols＋コメント＋ログボ文言）。

    定義の真実の源は backend/app/limited_idol.py。運営が同ファイルを書き換えて
    再起動すると、ここで idols テーブルの当該行が最新の名前・色・キャッチフレーズに
    更新される（存在しなければ追加）。is_limited=True のため通常一覧には出ない。

    【DESIGN_D-4 §6.1 の穴を塞ぐ】従来は `Idol` 行しか作らなかったため、限定推しを
    選んだユーザーのホーム吹き出しは API フォールバックの「{nickname}、いつもありがとう！」
    1文固定だった（T1 特典を取った人ほど体験が貧しくなる逆転）。ここでコメントも投入する。
    文言が未用意の場合は中立9文／DEFAULT_LOGIN_LINES に落ちるので、差し替え時に
    文言を忘れても画面は壊れない（§6.2 原則2）。
    """
    slug = LIMITED_IDOL["id"]
    existing = db.get(Idol, slug)
    if existing is None:
        _insert_safely(
            db,
            Idol(
                id=slug,
                name=LIMITED_IDOL["name"],
                theme_color=LIMITED_IDOL["theme_color"],
                catchphrase=LIMITED_IDOL["catchphrase"],
                is_limited=True,
            ),
        )
        existing = db.get(Idol, slug)
    if existing is not None:
        # 運営がファイルを差し替えた場合に備え、属性を最新化する（is_limited は必ず True）
        existing.name = LIMITED_IDOL["name"]
        existing.theme_color = LIMITED_IDOL["theme_color"]
        existing.catchphrase = LIMITED_IDOL["catchphrase"]
        existing.is_limited = True
    db.flush()  # 子テーブル（コメント・文言）の FK 解決のため先に確定させる

    # 【QA_Q-8 M-1・m-1・m-2】運営が書いた文言は必ず検証してから使う。
    # 壊れていても DEFAULT／中立9文に落ち、**起動は必ず成功する**（D-4 §6.2 原則2）。
    _sync_idol_comments(
        db,
        slug,
        _normalize_comments(slug, LIMITED_IDOL.get("comments"), NEUTRAL_COMMENT_TEMPLATES),
    )
    _sync_login_lines(
        db, slug, _normalize_login_lines(slug, LIMITED_IDOL.get("login_lines"))
    )


def _seed_legacy_limited_idols(db: Session) -> None:
    """**過去 slug の限定推し**にも中立9文と DEFAULT 文言を行き渡らせる（冪等）。

    【QA_Q-8 m-3 対応】文言を投入していたのは `IDOLS_DATA` の6人＋**現行の** `LIMITED_IDOL` だけ
    だったため、月中差し替え（2026-07-23 の seira → rinaresu 等）で取り残されたユーザーは、
    吹き出しが API フォールバックの「{nickname}、いつもありがとう！」**1文固定**のままだった。
    T1 を取った最上位貢献者ほど体験が貧しいという、D-4 §6.1 が直したはずの逆転が
    過去 slug で再発していた形。

    **既にコメント／文言を持っている過去 slug は一切上書きしない**（不足ぶんを埋めるだけ）。
    過去 slug の文言は「消す必要はなく、消してもいけない」ため（DESIGN_D-4 §6.3）。
    """
    legacy_ids = [
        idol.id
        for idol in db.query(Idol).filter(Idol.is_limited.is_(True)).all()
        if idol.id != LIMITED_IDOL["id"]
    ]
    for slug in legacy_ids:
        has_comment = (
            db.query(IdolComment).filter(IdolComment.idol_id == slug).first() is not None
        )
        if not has_comment:
            for rank, templates in NEUTRAL_COMMENT_TEMPLATES.items():
                for template in templates:
                    _insert_safely(
                        db, IdolComment(idol_id=slug, rank=rank, template=template)
                    )
            logger.info(
                "[seed] 過去の期間限定推し %s に中立コメント9文を補充しました", slug
            )
        if db.get(IdolLoginLine, slug) is None:
            _insert_safely(db, IdolLoginLine(idol_id=slug, **DEFAULT_LOGIN_LINES))
            logger.info(
                "[seed] 過去の期間限定推し %s に既定のログインボーナス文言を補充しました",
                slug,
            )


def _seed_idols(db: Session) -> None:
    """アイドル6人・キャラ別コメント・キャラ別ログボ文言を upsert する（冪等）。

    【DESIGN_D-4 §8 #2】従来は `if db.query(Idol).count() > 0: return` で初回しか
    通らなかったため、コード側の文言を書き換えても既存 DB（本番・稼働中ローカル）には
    反映されなかった。`_seed_device_types` と同じ upsert 方式にそろえ、
    **再起動するだけで既存 DB も自動的にキャラ別へ切り替わる**ようにしている。

    - 純 ORM 操作のため SQLite / PostgreSQL 両対応・冪等（2回目以降は無変更）。
    - ユーザーのランク・pt・特典には一切触らない（変わるのは表示文言だけ）。
    """
    for data in IDOLS_DATA:
        slug = data["id"]
        existing = db.get(Idol, slug)
        if existing is None:
            # 【R-4 M-1】並行 seed での主キー競合を savepoint で吸収する
            _insert_safely(db, Idol(**data, is_limited=False))
            existing = db.get(Idol, slug)
        if existing is not None:
            existing.name = data["name"]
            existing.theme_color = data["theme_color"]
            existing.catchphrase = data["catchphrase"]
            existing.is_limited = False  # 通常名簿の6人は必ず通常枠
        db.flush()  # 子テーブル（コメント・文言）の FK 解決のため先に確定させる

        # コード側の定数も同じ検証を通す（将来の編集ミスで一部ランクが0件になるのを防ぐ）
        _sync_idol_comments(
            db,
            slug,
            _normalize_comments(
                slug, IDOL_COMMENT_TEMPLATES.get(slug), NEUTRAL_COMMENT_TEMPLATES
            ),
        )
        _sync_login_lines(
            db, slug, _normalize_login_lines(slug, IDOL_LOGIN_LINES.get(slug))
        )


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
