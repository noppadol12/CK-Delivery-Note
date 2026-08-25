"""
extractor.py — ใช้ Claude API อ่านข้อมูลจาก PDF ใบกำกับภาษี
คืนค่า: (items, doc_info)
  items    = [{"name": "...", "quantity": "1 EA"}, ...]
  doc_info = {
    "doc_number": "INV...",
    "date": "DD/MM/YYYY",
    "customer_name": "...",
    "customer_address": "...",
    "customer_tax_id": "...",
  }
"""

import os
import json
import re
import base64
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")


def extract_items_from_pdf(pdf_path: str) -> tuple[list, dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": """จากเอกสาร PDF ใบกำกับภาษีนี้ ให้ extract ข้อมูลต่อไปนี้:

1. เลขที่เอกสาร (Invoice Number)
2. วันที่
3. ชื่อลูกค้า (ฝั่งผู้ซื้อ)
4. ที่อยู่ลูกค้า (ถ้ามี)
5. เลขประจำตัวผู้เสียภาษีของลูกค้า (ถ้ามี)
6. รายการสินค้า/บริการทุกรายการ พร้อมจำนวนและหน่วย (ไม่ต้องมีราคา)

ตอบกลับเป็น JSON เท่านั้น:
{
  "doc_number": "INVxxxxxxxxx",
  "date": "25/08/2026",
  "customer_name": "บริษัท ...",
  "customer_address": "...",
  "customer_tax_id": "...",
  "items": [
    {"name": "ชื่อสินค้า", "quantity": "1 EA"},
    {"name": "ค่าขนส่ง", "quantity": "1 EA"}
  ]
}

หมายเหตุ: ถ้าไม่มีข้อมูลใดให้ใส่ string ว่างหรือ "-" """,
                    },
                ],
            }
        ],
    )

    text = response.content[0].text.strip()

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"Claude ไม่ส่ง JSON กลับมา: {text[:300]}")

    data = json.loads(match.group())
    items = data.get("items", [])
    doc_info = {
        "doc_number":       data.get("doc_number", "-"),
        "date":             data.get("date", "-"),
        "customer_name":    data.get("customer_name", "-"),
        "customer_address": data.get("customer_address", ""),
        "customer_tax_id":  data.get("customer_tax_id", ""),
    }

    return items, doc_info
