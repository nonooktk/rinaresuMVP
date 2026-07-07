"""
送付伝票PDF生成サービス。

A5横向き、日本語CIDフォント(HeiseiKakuGo-W5)を使用してreportlabで生成する。
QRコードには送付ID・ユーザーID・デバイス情報をJSON化して埋め込む。
生成物は data/shipments/slip_{id}.pdf に保存する。
"""
import io
import json
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.database import BASE_DIR

# 日本語CIDフォントを登録（初回のみ登録すればよい）
FONT_NAME = "HeiseiKakuGo-W5"
pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

SHIPMENTS_DIR = BASE_DIR / "data" / "shipments"
SHIPMENTS_DIR.mkdir(parents=True, exist_ok=True)


def _make_qr_image(data: dict) -> ImageReader:
    """QRコード用の画像データ(ImageReader)を生成する。"""
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(json.dumps(data, ensure_ascii=False))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def generate_slip_pdf(
    shipment_id: int,
    user_id: int,
    temp_id: str,
    nickname: str,
    devices: list[dict],
) -> str:
    """
    送付伝票PDFを生成し、保存先パスを返す。

    devices: [{"id": int, "device_type": str, "label": str, "points": int}, ...]
    """
    total_points = sum(d["points"] for d in devices)

    pdf_path = SHIPMENTS_DIR / f"slip_{shipment_id}.pdf"
    page_size = landscape(A5)
    page_width, page_height = page_size

    c = canvas.Canvas(str(pdf_path), pagesize=page_size)

    # ---------- タイトル ----------
    c.setFont(FONT_NAME, 18)
    c.drawString(15 * mm, page_height - 15 * mm, "回収キット送付伝票（着払い）")

    # ---------- 着払い枠 ----------
    box_w, box_h = 30 * mm, 14 * mm
    box_x = page_width - box_w - 12 * mm
    box_y = page_height - box_h - 10 * mm
    c.setLineWidth(2)
    c.rect(box_x, box_y, box_w, box_h)
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 - 5, "着払")

    # ---------- お届け先 ----------
    y = page_height - 30 * mm
    c.setFont(FONT_NAME, 10)
    c.drawString(15 * mm, y, "お届け先")
    y -= 7 * mm
    c.setFont(FONT_NAME, 14)
    c.drawString(15 * mm, y, "〒135-0016 東京都江東区")
    y -= 8 * mm
    c.setFont(FONT_NAME, 16)
    c.drawString(15 * mm, y, "りなれす 御中")

    # ---------- 依頼主 ----------
    y -= 12 * mm
    c.setFont(FONT_NAME, 10)
    c.drawString(15 * mm, y, "依頼主")
    y -= 6 * mm
    c.setFont(FONT_NAME, 11)
    c.drawString(15 * mm, y, "〒100-8111 東京都千代田区千代田1-1（仮住所）")
    y -= 6 * mm
    c.drawString(15 * mm, y, f"仮ID: {temp_id}　ニックネーム: {nickname}")

    # ---------- 品名欄 ----------
    y -= 10 * mm
    c.setFont(FONT_NAME, 11)
    c.drawString(15 * mm, y, "品名・想定ポイント")
    y -= 2 * mm
    c.line(15 * mm, y, page_width - 55 * mm, y)
    y -= 6 * mm

    c.setFont(FONT_NAME, 9)
    for d in devices:
        line = f"・{d['label']}（{d['device_type']}）  {d['points']}pt"
        c.drawString(17 * mm, y, line)
        y -= 5.5 * mm
        if y < 20 * mm:
            # 品目が多い場合は以降省略（MVPのため簡易対応）
            c.drawString(17 * mm, y, "…以下略")
            y -= 5.5 * mm
            break

    y -= 3 * mm
    c.setFont(FONT_NAME, 12)
    c.drawString(15 * mm, y, f"合計予定ポイント: {total_points}pt（デバイス数: {len(devices)}）")

    # ---------- QRコード（右下） ----------
    qr_data = {
        "shipment_id": shipment_id,
        "user_id": user_id,
        "devices": [
            {"id": d["id"], "device_type": d["device_type"]} for d in devices
        ],
    }
    qr_img = _make_qr_image(qr_data)
    qr_size = 32 * mm
    qr_x = page_width - qr_size - 12 * mm
    qr_y = 10 * mm
    c.drawImage(qr_img, qr_x, qr_y, width=qr_size, height=qr_size)
    c.setFont(FONT_NAME, 7)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 4 * mm, f"送付ID: {shipment_id}")

    c.showPage()
    c.save()

    return str(pdf_path)
