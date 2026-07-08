"""
画像判定（OpenAIVisionClassifier）の精度検証ハーネス（Phase 1）。

test_images/{正解ラベル}/*.jpg|png の構造を走査し、各画像を classifier に
直接渡して判定する（uvicorn 不要）。集計結果を results/ に CSV / Markdown で保存する。

正解ラベル = device_types の code 6種（smartphone / feature_phone / tablet /
camera / portable_game / other）＋ negative（回収対象外）。

使い方（backend/ をカレントにして venv で実行）:

    cd backend
    source /path/to/openai.env          # Azure OpenAI の環境変数を読み込む
    venv/bin/python eval/eval_classifier.py

DB は既定で backend/data/rinaresu.db を使う。存在しない/テーブルが無い場合は
一時 DB を作って seed を投入する（--fresh-db で常に一時 DB を使う）。

主なオプション:
    --repeat-stability N SPEC  安定性チェック。SPEC で指定した画像を N 回ずつ
                               判定し Top-1 のブレを記録する。SPEC はカンマ区切りの
                               「label/filename」（例: smartphone/a.jpg,tablet/b.png）。
                               省略時は各ラベル先頭1枚から最大3枚を自動選択。
"""
import argparse
import csv
import hashlib
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# backend/ をインポートパスに追加（app パッケージを読むため）
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import DeviceType  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.services import classifier as classifier_module  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
IMAGES_DIR = EVAL_DIR / "test_images"
RESULTS_DIR = EVAL_DIR / "results"

# 対応する画像拡張子
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 端末クラス（negative 以外の正解ラベルとして許容する code）。
# other は「その他小型家電」でありマスタ上の code だが、
# 正解率の分母（端末クラス）には含めつつ、混同行列では通常クラスとして扱う。
NEGATIVE_LABEL = "negative"

# negative 誤検知の判定に使う confidence 閾値
NEGATIVE_FP_THRESHOLD = 0.7


def prompt_version_hash() -> str:
    """
    classifier.py のプロンプト該当部分（_build_prompt / _parse_candidates /
    classify_with_source の本文）のハッシュを返す。改善前後の比較用の
    「プロンプトバージョン識別子」として結果に埋め込む。
    """
    import inspect

    cls = classifier_module.OpenAIVisionClassifier
    parts = []
    for name in ("_build_prompt", "_parse_candidates", "classify_with_source"):
        try:
            parts.append(inspect.getsource(getattr(cls, name)))
        except (OSError, TypeError):
            parts.append("")
    joined = "\n".join(parts).encode("utf-8")
    return hashlib.sha256(joined).hexdigest()[:12]


def ensure_db():
    """
    DB を用意する。既存 DB に device_types が seed 済みならそれを使い、
    無ければ create_all + seed_all を実行する（冪等）。
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(DeviceType).count() == 0:
            seed_all(db)
        codes = [dt.code for dt in db.query(DeviceType).all()]
    finally:
        db.close()
    return codes


def collect_images():
    """
    test_images/{label}/*.ext を走査して (label, path) のリストを返す。
    ラベルフォルダ名がそのまま正解ラベル。
    """
    items = []
    if not IMAGES_DIR.exists():
        return items
    for label_dir in sorted(IMAGES_DIR.iterdir()):
        if not label_dir.is_dir():
            continue
        label = label_dir.name
        for img in sorted(label_dir.iterdir()):
            if img.suffix.lower() in IMAGE_EXTS:
                items.append((label, img))
    return items


def classify_one(path: Path):
    """
    1 画像を classifier に渡して判定する。
    戻り値: (candidates, generated_by, elapsed_sec)
    """
    file_bytes = path.read_bytes()
    db = SessionLocal()
    try:
        t0 = time.perf_counter()
        candidates, generated_by = classifier_module.classifier.classify_with_source(
            file_bytes, path.name, db
        )
        elapsed = time.perf_counter() - t0
    finally:
        db.close()
    return candidates, generated_by, elapsed


def run_evaluation(items):
    """
    全画像を判定し、行レコードのリストを返す。
    各行: dict（filename, label, top1..top3 の code/conf, generated_by, elapsed）
    """
    rows = []
    total = len(items)
    for idx, (label, path) in enumerate(items, 1):
        candidates, generated_by, elapsed = classify_one(path)
        codes = [c["device_type"] for c in candidates]
        confs = [c["confidence"] for c in candidates]
        # 3件に満たない場合は空文字で埋める
        while len(codes) < 3:
            codes.append("")
            confs.append("")

        top1 = codes[0]
        top1_conf = confs[0] if confs[0] != "" else 0.0

        # 正解判定
        if label == NEGATIVE_LABEL:
            top1_correct = ""  # negative は正解率の対象外
            top3_correct = ""
        else:
            top1_correct = top1 == label
            top3_correct = label in [c for c in codes if c]

        rows.append(
            {
                "filename": f"{label}/{path.name}",
                "true_label": label,
                "top1_code": codes[0],
                "top1_conf": confs[0],
                "top2_code": codes[1],
                "top2_conf": confs[1],
                "top3_code": codes[2],
                "top3_conf": confs[2],
                "generated_by": generated_by,
                "elapsed_sec": round(elapsed, 3),
                "top1_correct": top1_correct,
                "top3_correct": top3_correct,
                "_top1_conf_num": top1_conf,
            }
        )
        mark = "OK " if top1_correct is True else ("-  " if top1_correct == "" else "NG ")
        print(
            f"[{idx}/{total}] {mark} {label:>13} -> "
            f"{codes[0] or '(none)'}({confs[0]}) "
            f"[{generated_by}] {elapsed:.2f}s"
        )
    return rows


def summarize(rows, device_codes):
    """行レコードから全指標を集計して dict で返す。"""
    device_rows = [r for r in rows if r["true_label"] != NEGATIVE_LABEL]
    negative_rows = [r for r in rows if r["true_label"] == NEGATIVE_LABEL]

    n_device = len(device_rows)
    top1_hits = sum(1 for r in device_rows if r["top1_correct"] is True)
    top3_hits = sum(1 for r in device_rows if r["top3_correct"] is True)

    top1_rate = top1_hits / n_device if n_device else 0.0
    top3_rate = top3_hits / n_device if n_device else 0.0

    # negative 誤検知: 端末クラスを confidence>閾値 で Top-1 に返したもの
    # （other も「端末クラス扱い」として誤検知に数える＝ negative なのに何かの機器と判定）
    neg_fp = 0
    for r in negative_rows:
        top1 = r["top1_code"]
        conf = r["_top1_conf_num"]
        if top1 and top1 != "other" and conf > NEGATIVE_FP_THRESHOLD:
            neg_fp += 1
    # other も含めた「負例なのに何かを高確信で返した」広義誤検知も別途集計
    neg_fp_incl_other = 0
    for r in negative_rows:
        top1 = r["top1_code"]
        conf = r["_top1_conf_num"]
        if top1 and conf > NEGATIVE_FP_THRESHOLD:
            neg_fp_incl_other += 1
    n_neg = len(negative_rows)
    neg_fp_rate = neg_fp / n_neg if n_neg else 0.0
    neg_fp_rate_incl_other = neg_fp_incl_other / n_neg if n_neg else 0.0

    # 応答時間 p50 / p95
    elapsed_all = [r["elapsed_sec"] for r in rows]
    p50 = statistics.median(elapsed_all) if elapsed_all else 0.0
    if elapsed_all:
        srt = sorted(elapsed_all)
        idx95 = min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))
        p95 = srt[idx95]
    else:
        p95 = 0.0

    # フォールバック（mock）件数
    mock_count = sum(1 for r in rows if r["generated_by"] == "mock")
    ai_count = sum(1 for r in rows if r["generated_by"] == "ai")

    # 混同行列（Top-1 ベース、端末クラス行のみ）。列は device_codes + "(none)"
    col_labels = sorted(device_codes) + ["(none)"]
    matrix = {tl: Counter() for tl in sorted(set(r["true_label"] for r in device_rows))}
    for r in device_rows:
        pred = r["top1_code"] if r["top1_code"] else "(none)"
        if pred not in col_labels:
            col_labels.append(pred)
        matrix[r["true_label"]][pred] += 1

    # クラス別 Top-1 正解率
    per_class = {}
    for tl in matrix:
        cls_rows = [r for r in device_rows if r["true_label"] == tl]
        hits = sum(1 for r in cls_rows if r["top1_correct"] is True)
        per_class[tl] = (hits, len(cls_rows))

    return {
        "n_total": len(rows),
        "n_device": n_device,
        "n_neg": n_neg,
        "top1_hits": top1_hits,
        "top3_hits": top3_hits,
        "top1_rate": top1_rate,
        "top3_rate": top3_rate,
        "neg_fp": neg_fp,
        "neg_fp_rate": neg_fp_rate,
        "neg_fp_incl_other": neg_fp_incl_other,
        "neg_fp_rate_incl_other": neg_fp_rate_incl_other,
        "p50": p50,
        "p95": p95,
        "mock_count": mock_count,
        "ai_count": ai_count,
        "matrix": matrix,
        "col_labels": col_labels,
        "per_class": per_class,
    }


def run_stability(items, spec, repeat):
    """
    安定性チェック。spec で指定した画像を repeat 回ずつ判定し、
    各画像の Top-1 コードの内訳（ブレ）を返す。
    """
    # spec 解決: 指定があればそれ、無ければ各ラベル先頭1枚から最大3枚
    targets = []
    by_path = {r[0] + "/" + r[1].name: r[1] for r in items}
    if spec:
        for key in spec.split(","):
            key = key.strip()
            if key in by_path:
                targets.append((key, by_path[key]))
            else:
                print(f"[stability] 指定画像が見つかりません: {key}")
    else:
        seen_labels = set()
        for label, path in items:
            if label == NEGATIVE_LABEL:
                continue
            if label not in seen_labels:
                seen_labels.add(label)
                targets.append((f"{label}/{path.name}", path))
            if len(targets) >= 3:
                break

    results = {}
    for key, path in targets:
        top1s = []
        for _ in range(repeat):
            candidates, gen, _elapsed = classify_one(path)
            top1 = candidates[0]["device_type"] if candidates else "(none)"
            top1s.append(top1)
        results[key] = Counter(top1s)
        print(f"[stability] {key}: {dict(Counter(top1s))}")
    return results, repeat


def write_outputs(rows, summary, stability, repeat, phash, device_codes):
    """CSV と Markdown サマリを results/ に書き出す。"""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = RESULTS_DIR / f"eval_{ts}.csv"
    md_path = RESULTS_DIR / f"eval_{ts}.md"

    # --- CSV（画像ごとの明細） ---
    fieldnames = [
        "filename", "true_label",
        "top1_code", "top1_conf", "top2_code", "top2_conf",
        "top3_code", "top3_conf",
        "generated_by", "elapsed_sec", "top1_correct", "top3_correct",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    # --- Markdown サマリ ---
    lines = []
    lines.append(f"# 画像判定 精度検証サマリ ({ts})")
    lines.append("")
    lines.append(f"- プロンプトバージョン識別子: `{phash}`")
    lines.append(f"- 判定エンジン: `{type(classifier_module.classifier).__name__}`")
    lines.append(f"- 対象画像: {summary['n_total']}枚"
                 f"（端末クラス {summary['n_device']}枚 / negative {summary['n_neg']}枚）")
    lines.append(f"- AI判定 {summary['ai_count']}件 / mockフォールバック {summary['mock_count']}件")
    lines.append("")
    lines.append("## 合格基準との比較")
    lines.append("")
    lines.append("| 指標 | 実測 | 合格基準 | 判定 |")
    lines.append("|---|---|---|---|")
    t1 = summary["top1_rate"]
    t3 = summary["top3_rate"]
    nf = summary["neg_fp_rate"]
    lines.append(f"| Top-1 正解率 | {t1*100:.1f}% ({summary['top1_hits']}/{summary['n_device']}) "
                 f"| 75%以上 | {'合格' if t1 >= 0.75 else '未達'} |")
    lines.append(f"| Top-3 正解率 | {t3*100:.1f}% ({summary['top3_hits']}/{summary['n_device']}) "
                 f"| 90%以上 | {'合格' if t3 >= 0.90 else '未達'} |")
    lines.append(f"| negative 誤検知率 | {nf*100:.1f}% ({summary['neg_fp']}/{summary['n_neg']}) "
                 f"| 5%以下 | {'合格' if nf <= 0.05 else '未達'} |")
    lines.append("")
    lines.append(f"※ negative 誤検知率は「端末クラス(other除く)を confidence>"
                 f"{NEGATIVE_FP_THRESHOLD} で Top-1 に返した」割合。")
    lines.append(f"参考: other も含めた広義誤検知は "
                 f"{summary['neg_fp_rate_incl_other']*100:.1f}% "
                 f"({summary['neg_fp_incl_other']}/{summary['n_neg']})。")
    lines.append("")
    lines.append("## クラス別 Top-1 正解率")
    lines.append("")
    lines.append("| 正解ラベル | 正解/枚数 | 正解率 |")
    lines.append("|---|---|---|")
    for tl in sorted(summary["per_class"]):
        hits, n = summary["per_class"][tl]
        rate = hits / n * 100 if n else 0.0
        lines.append(f"| {tl} | {hits}/{n} | {rate:.1f}% |")
    lines.append("")
    lines.append("## 混同行列（Top-1・端末クラスのみ / 行=正解, 列=予測）")
    lines.append("")
    cols = summary["col_labels"]
    header = "| 正解＼予測 | " + " | ".join(cols) + " |"
    sep = "|---|" + "|".join(["---"] * len(cols)) + "|"
    lines.append(header)
    lines.append(sep)
    for tl in sorted(summary["matrix"]):
        counter = summary["matrix"][tl]
        cells = [str(counter.get(c, 0)) for c in cols]
        lines.append(f"| {tl} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 応答時間・フォールバック")
    lines.append("")
    lines.append(f"- 応答時間 p50: {summary['p50']:.2f}s / p95: {summary['p95']:.2f}s")
    lines.append(f"- mock フォールバック発生数: {summary['mock_count']} / {summary['n_total']}")
    lines.append("")
    if stability:
        lines.append(f"## 安定性チェック（各 {repeat} 回判定した Top-1 のブレ）")
        lines.append("")
        lines.append("| 画像 | Top-1 内訳 | ブレ |")
        lines.append("|---|---|---|")
        for key, counter in stability.items():
            detail = ", ".join(f"{k}×{v}" for k, v in counter.items())
            stable = "安定" if len(counter) == 1 else "ブレあり"
            lines.append(f"| {key} | {detail} | {stable} |")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, md_path


def main():
    parser = argparse.ArgumentParser(description="画像判定 精度検証ハーネス")
    parser.add_argument("--repeat-stability", nargs="?", const="", default=None,
                        metavar="SPEC",
                        help="安定性チェックを実行。任意で label/filename のカンマ区切り指定")
    parser.add_argument("--stability-repeat", type=int, default=3,
                        help="安定性チェックの繰り返し回数（既定3）")
    parser.add_argument("--fresh-db", action="store_true",
                        help="常に create_all + seed で DB を初期化してから使う")
    args = parser.parse_args()

    if args.fresh_db:
        Base.metadata.create_all(bind=engine)

    device_codes = ensure_db()
    print(f"device_types(codes): {sorted(device_codes)}")
    phash = prompt_version_hash()
    print(f"プロンプトバージョン識別子: {phash}")

    items = collect_images()
    if not items:
        print(f"画像が見つかりません: {IMAGES_DIR} に test_images/{{label}}/*.jpg を配置してください。")
        sys.exit(1)
    print(f"対象画像 {len(items)} 枚を判定します...\n")

    rows = run_evaluation(items)
    summary = summarize(rows, device_codes)

    stability = None
    if args.repeat_stability is not None:
        print("\n--- 安定性チェック ---")
        stability, _ = run_stability(items, args.repeat_stability, args.stability_repeat)

    csv_path, md_path = write_outputs(
        rows, summary, stability, args.stability_repeat, phash, device_codes
    )

    print("\n===== サマリ =====")
    print(f"Top-1 正解率: {summary['top1_rate']*100:.1f}% "
          f"({summary['top1_hits']}/{summary['n_device']})")
    print(f"Top-3 正解率: {summary['top3_rate']*100:.1f}% "
          f"({summary['top3_hits']}/{summary['n_device']})")
    print(f"negative 誤検知率: {summary['neg_fp_rate']*100:.1f}% "
          f"({summary['neg_fp']}/{summary['n_neg']})")
    print(f"応答時間 p50/p95: {summary['p50']:.2f}s / {summary['p95']:.2f}s")
    print(f"mock フォールバック: {summary['mock_count']}/{summary['n_total']}")
    print(f"\n出力: {csv_path}")
    print(f"      {md_path}")


if __name__ == "__main__":
    main()
