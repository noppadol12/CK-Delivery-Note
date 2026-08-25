"""
generator.py — สร้าง PDF ใบส่งสินค้าชั่วคราว
- show_customer=True  → แสดงชื่อลูกค้า
- show_customer=False → ไม่แสดงชื่อผู้ขาย/ลูกค้า
- รองรับภาษาไทย (ฟอนต์ Sarabun จาก Google Fonts)
"""

import urllib.request
from pathlib import Path
from fpdf import FPDF

FONT_DIR = Path(__file__).parent / "fonts"
FONT_URLS = {
    "Sarabun-Regular.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun/Sarabun-Regular.ttf"
    ),
    "Sarabun-Bold.ttf": (
        "https://raw.githubusercontent.com/google/fonts/main/ofl/sarabun/Sarabun-Bold.ttf"
    ),
}


def _ensure_fonts():
    FONT_DIR.mkdir(exist_ok=True)
    for name, url in FONT_URLS.items():
        dest = FONT_DIR / name
        if not dest.exists():
            print(f"[generator] Downloading font: {name}")
            urllib.request.urlretrieve(url, str(dest))


class DeliveryPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("Sarabun", style="", fname=str(FONT_DIR / "Sarabun-Regular.ttf"))
        self.add_font("Sarabun", style="B", fname=str(FONT_DIR / "Sarabun-Bold.ttf"))
        self.set_margins(left=20, top=20, right=20)
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Sarabun", "", 8)
        self.set_text_color(160, 160, 160)
        self.cell(0, 5, "เอกสารนี้ไม่แสดงราคาสินค้า — ใช้เพื่อยืนยันการรับสินค้าเท่านั้น", align="C")
        self.set_text_color(0, 0, 0)


def _text_lines(pdf: FPDF, text: str, max_width: float) -> list[str]:
    """Word-wrap ข้อความให้พอดีความกว้าง"""
    words = text.split(" ")
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if pdf.get_string_width(candidate) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def generate_delivery_slip(
    items: list,
    doc_info: dict,
    output_path: str,
    show_customer: bool = False,
):
    """
    สร้าง PDF ใบส่งสินค้าชั่วคราว
    items         = [{"name": "...", "quantity": "1 EA"}, ...]
    doc_info      = {"doc_number": "...", "date": "...",
                     "customer_name": "...", "customer_address": "...",
                     "seller_name": "..."}  ← extractor จะ populate ให้
    show_customer = True → แสดงชื่อลูกค้า
    """
    pdf = DeliveryPDF()
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    # ── ชื่อเอกสาร ──────────────────────────────────────────────────────────
    pdf.set_font("Sarabun", "B", 22)
    pdf.cell(W, 10, "ใบส่งสินค้าชั่วคราว", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Header info box ───────────────────────────────────────────────────────
    pdf.ln(2)
    half = W / 2

    if show_customer:
        # มีชื่อลูกค้า → box สูงขึ้น
        customer_name = doc_info.get("customer_name", "-")
        customer_addr = doc_info.get("customer_address", "")
        customer_tax  = doc_info.get("customer_tax_id", "")

        info_lines = []
        if customer_name:
            info_lines.append(f"ลูกค้า: {customer_name}")
        if customer_addr:
            info_lines.append(f"ที่อยู่: {customer_addr}")
        if customer_tax:
            info_lines.append(f"เลขประจำตัวผู้เสียภาษี: {customer_tax}")

        box_h = max(14, len(info_lines) * 6 + 8)
        pdf.set_fill_color(243, 244, 246)
        pdf.rect(pdf.l_margin, pdf.get_y(), W, box_h, style="F")

        y0 = pdf.get_y() + 3
        pdf.set_font("Sarabun", "", 11)

        # ซ้าย: ข้อมูลลูกค้า
        for i, line in enumerate(info_lines):
            pdf.set_xy(pdf.l_margin + 3, y0 + i * 6)
            pdf.cell(half - 3, 5, line)

        # ขวา: เลขที่ + วันที่
        pdf.set_xy(pdf.l_margin + half, y0)
        pdf.cell(half, 5, f"เลขที่อ้างอิง:  {doc_info.get('doc_number', '-')}")
        pdf.set_xy(pdf.l_margin + half, y0 + 6)
        pdf.cell(half, 5, f"วันที่:  {doc_info.get('date', '-')}")

        pdf.set_y(pdf.get_y() + box_h + 2)

    else:
        # ไม่มีชื่อลูกค้า → box เล็ก
        pdf.set_fill_color(243, 244, 246)
        pdf.rect(pdf.l_margin, pdf.get_y(), W, 14, style="F")

        y0 = pdf.get_y() + 3
        pdf.set_font("Sarabun", "", 11)
        pdf.set_xy(pdf.l_margin + 3, y0)
        pdf.cell(half - 3, 5, f"เลขที่อ้างอิง:  {doc_info.get('doc_number', '-')}")
        pdf.set_xy(pdf.l_margin + half, y0)
        pdf.cell(half, 5, f"วันที่:  {doc_info.get('date', '-')}")
        pdf.set_y(pdf.get_y() + 14 + 2)

    pdf.ln(2)

    # ── ตารางสินค้า ───────────────────────────────────────────────────────────
    COL_NO   = 12
    COL_QTY  = 38
    COL_NAME = W - COL_NO - COL_QTY
    PADDING  = 2
    LINE_H   = 7

    # header
    pdf.set_font("Sarabun", "B", 12)
    pdf.set_fill_color(29, 78, 216)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(COL_NO,   9, "#",              border=1, align="C", fill=True)
    pdf.cell(COL_NAME, 9, "รายละเอียดสินค้า", border=1, align="C", fill=True)
    pdf.cell(COL_QTY,  9, "จำนวน",          border=1, align="C", fill=True,
             new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Sarabun", "", 11)

    for idx, item in enumerate(items):
        name = item.get("name", "")
        qty  = item.get("quantity", "")

        name_lines = _text_lines(pdf, name, COL_NAME - PADDING * 2)
        row_h = max(len(name_lines), 1) * LINE_H + PADDING * 2

        bg = (255, 255, 255) if idx % 2 == 0 else (249, 250, 251)
        pdf.set_fill_color(*bg)

        x0 = pdf.l_margin
        y0 = pdf.get_y()

        if pdf.will_page_break(row_h):
            pdf.add_page()
            y0 = pdf.get_y()

        # col #
        pdf.rect(x0, y0, COL_NO, row_h, style="FD")
        pdf.set_xy(x0, y0 + (row_h - LINE_H) / 2)
        pdf.cell(COL_NO, LINE_H, str(idx + 1), align="C")

        # col name
        pdf.rect(x0 + COL_NO, y0, COL_NAME, row_h, style="FD")
        text_y = y0 + PADDING
        for line in name_lines:
            pdf.set_xy(x0 + COL_NO + PADDING, text_y)
            pdf.cell(COL_NAME - PADDING * 2, LINE_H, line)
            text_y += LINE_H

        # col qty
        pdf.rect(x0 + COL_NO + COL_NAME, y0, COL_QTY, row_h, style="FD")
        pdf.set_xy(x0 + COL_NO + COL_NAME, y0 + (row_h - LINE_H) / 2)
        pdf.cell(COL_QTY, LINE_H, qty, align="C")

        pdf.set_xy(x0, y0 + row_h)

    pdf.ln(18)

    # ── ช่องเซ็นรับสินค้า ────────────────────────────────────────────────────
    sig_y = pdf.get_y()
    if sig_y > pdf.h - 60:
        pdf.add_page()
        sig_y = pdf.get_y()

    MARGIN = 20
    LINE_W = half - MARGIN * 2 + 10

    pdf.set_font("Sarabun", "", 11)

    # หัว
    pdf.set_xy(pdf.l_margin, sig_y)
    pdf.cell(half, 6, "ผู้ส่งสินค้า", align="C")
    pdf.set_xy(pdf.l_margin + half, sig_y)
    pdf.cell(half, 6, "ผู้รับสินค้า / ผู้รับมอบ", align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.ln(16)
    line_y = pdf.get_y()

    pdf.line(pdf.l_margin + MARGIN, line_y,
             pdf.l_margin + MARGIN + LINE_W, line_y)
    pdf.line(pdf.l_margin + half + MARGIN, line_y,
             pdf.l_margin + half + MARGIN + LINE_W, line_y)

    pdf.ln(3)
    pdf.set_font("Sarabun", "", 10)
    pdf.set_text_color(100, 100, 100)

    pdf.set_x(pdf.l_margin)
    pdf.cell(half, 5, "(............................................)", align="C")
    pdf.set_x(pdf.l_margin + half)
    pdf.cell(half, 5, "(............................................)", align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.set_x(pdf.l_margin)
    pdf.cell(half, 5, "วันที่ ......... / ......... / ............", align="C")
    pdf.set_x(pdf.l_margin + half)
    pdf.cell(half, 5, "วันที่ ......... / ......... / ............", align="C",
             new_x="LMARGIN", new_y="NEXT")

    pdf.output(output_path)
