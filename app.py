"""
LINE Bot - ใบส่งสินค้าชั่วคราว
รับ PDF ใบกำกับภาษี → ถามว่าแสดงชื่อลูกค้าไหม → สร้าง PDF ใบส่งสินค้าชั่วคราว
"""

import os
import uuid
import threading
import time
from pathlib import Path
from flask import Flask, request, abort, send_file, jsonify
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage, FlexMessage, QuickReply, QuickReplyItem, MessageAction,
)
from linebot.v3.webhooks import MessageEvent, FileMessageContent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError

from extractor import extract_items_from_pdf
from generator import generate_delivery_slip

app = Flask(__name__)

LINE_ACCESS_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = os.environ["LINE_CHANNEL_SECRET"]
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")

configuration = Configuration(access_token=LINE_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

TEMP_DIR = Path("/tmp/delivery_slips")
TEMP_DIR.mkdir(exist_ok=True)

# ── In-memory store: เก็บข้อมูลที่รอคำตอบจากผู้ใช้ ──────────────────────────
# key = user_id, value = {"items": [...], "doc_info": {...}, "expires": timestamp}
pending_jobs: dict[str, dict] = {}
_pending_lock = threading.Lock()


# ── Background cleanup ────────────────────────────────────────────────────────
def _cleanup_loop():
    while True:
        time.sleep(1800)
        now = time.time()
        # ลบไฟล์ PDF เก่า
        for f in TEMP_DIR.glob("*.pdf"):
            try:
                if f.stat().st_mtime < now - 3600:
                    f.unlink(missing_ok=True)
            except Exception:
                pass
        # ลบ pending jobs ที่หมดอายุ (10 นาที)
        with _pending_lock:
            expired = [uid for uid, job in pending_jobs.items()
                       if job.get("expires", 0) < now]
            for uid in expired:
                del pending_jobs[uid]


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ── Helpers ──────────────────────────────────────────────────────────────────
def push_text(user_id: str, text: str):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


def push_flex(user_id: str, alt_text: str, contents: dict):
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(
                to=user_id,
                messages=[FlexMessage(alt_text=alt_text, contents=contents)],
            )
        )


def _build_result_flex(doc_info: dict, item_count: int, download_url: str) -> dict:
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1D4ED8",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ ใบส่งสินค้าชั่วคราว",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "md",
                }
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "เลขที่:", "size": "sm", "color": "#6B7280", "flex": 2},
                        {"type": "text", "text": doc_info.get("doc_number", "-"), "size": "sm", "flex": 5, "wrap": True},
                    ],
                },
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "วันที่:", "size": "sm", "color": "#6B7280", "flex": 2},
                        {"type": "text", "text": doc_info.get("date", "-"), "size": "sm", "flex": 5},
                    ],
                },
                {
                    "type": "box", "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "รายการ:", "size": "sm", "color": "#6B7280", "flex": 2},
                        {"type": "text", "text": f"{item_count} รายการ", "size": "sm", "flex": 5},
                    ],
                },
                {"type": "separator", "margin": "md"},
                {
                    "type": "text",
                    "text": "⏱ ลิงก์หมดอายุใน 1 ชั่วโมง",
                    "size": "xxs", "color": "#9CA3AF", "margin": "md",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "color": "#1D4ED8",
                    "action": {
                        "type": "uri",
                        "label": "📄 ดาวน์โหลด PDF",
                        "uri": download_url,
                    },
                }
            ],
        },
    }


def _generate_and_send(user_id: str, items: list, doc_info: dict, show_customer: bool):
    """สร้าง PDF และส่งกลับให้ผู้ใช้"""
    try:
        output_id = str(uuid.uuid4())
        output_path = TEMP_DIR / f"{output_id}.pdf"
        generate_delivery_slip(items, doc_info, str(output_path), show_customer=show_customer)

        download_url = f"{BASE_URL}/download/{output_id}"
        flex = _build_result_flex(doc_info, len(items), download_url)
        push_flex(user_id, "ใบส่งสินค้าชั่วคราวพร้อมแล้ว", flex)
    except Exception as e:
        print(f"[ERROR] generate: {e}")
        push_text(user_id, f"❌ เกิดข้อผิดพลาดในการสร้าง PDF: {str(e)[:120]}")


# ── Webhook endpoint ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


# ── File message: รับ PDF ──────────────────────────────────────────────────
@handler.add(MessageEvent, message=FileMessageContent)
def handle_file(event):
    user_id = event.source.user_id
    message_id = event.message.id
    filename = event.message.file_name or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="❌ กรุณาส่งไฟล์ PDF เท่านั้น")],
                )
            )
        return

    # ดาวน์โหลดไฟล์ก่อน (ต้องทำก่อน reply_token หมดอายุ)
    with ApiClient(configuration) as api_client:
        content = MessagingApiBlob(api_client).get_message_content(message_id)

    def process():
        input_path = TEMP_DIR / f"input_{uuid.uuid4()}.pdf"
        try:
            with open(input_path, "wb") as f:
                f.write(content)

            # ส่ง "กำลังอ่านเอกสาร..."
            push_text(user_id, "⏳ กำลังอ่านเอกสาร...")

            items, doc_info = extract_items_from_pdf(str(input_path))

            if not items:
                push_text(user_id, "❌ ไม่พบรายการสินค้า กรุณาตรวจสอบไฟล์ PDF")
                return

            # บันทึกข้อมูลรอคำตอบ
            with _pending_lock:
                pending_jobs[user_id] = {
                    "items": items,
                    "doc_info": doc_info,
                    "expires": time.time() + 600,  # หมดอายุใน 10 นาที
                }

            # ถามผู้ใช้ว่าแสดงชื่อลูกค้าไหม (Quick Reply)
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(action=MessageAction(label="✅ แสดงชื่อลูกค้า", text="แสดงชื่อลูกค้า")),
                    QuickReplyItem(action=MessageAction(label="🚫 ไม่แสดงชื่อ", text="ไม่แสดงชื่อลูกค้า")),
                ]
            )
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[
                            TextMessage(
                                text=(
                                    f"📄 พบเอกสาร: {doc_info.get('doc_number', '-')}\n"
                                    f"🗓 วันที่: {doc_info.get('date', '-')}\n"
                                    f"📦 รายการสินค้า: {len(items)} รายการ\n\n"
                                    "ต้องการแสดงชื่อลูกค้าในใบส่งสินค้าหรือไม่?"
                                ),
                                quick_reply=quick_reply,
                            )
                        ],
                    )
                )
        except Exception as e:
            print(f"[ERROR] process: {e}")
            push_text(user_id, f"❌ เกิดข้อผิดพลาด: {str(e)[:120]}")
        finally:
            input_path.unlink(missing_ok=True)

    threading.Thread(target=process, daemon=True).start()


# ── Text message: รับคำตอบจาก Quick Reply ──────────────────────────────────
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):
    user_id = event.source.user_id
    text = event.message.text.strip()

    with _pending_lock:
        job = pending_jobs.get(user_id)

    if not job:
        # ไม่มีงานค้างอยู่ — ให้คำแนะนำ
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text="📎 กรุณาส่งไฟล์ PDF ใบกำกับภาษีเพื่อสร้างใบส่งสินค้าชั่วคราว"
                        )
                    ],
                )
            )
        return

    if text == "แสดงชื่อลูกค้า":
        show_customer = True
    elif text == "ไม่แสดงชื่อลูกค้า":
        show_customer = False
    else:
        # ข้อความอื่น — เตือนให้กดปุ่ม
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="กรุณาเลือกจากปุ่มที่แสดงอยู่ด้านบน")],
                )
            )
        return

    # ลบ pending job ออก
    with _pending_lock:
        pending_jobs.pop(user_id, None)

    items = job["items"]
    doc_info = job["doc_info"]

    # ตอบรับทันที
    with ApiClient(configuration) as api_client:
        MessagingApi(api_client).reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text="⏳ กำลังสร้าง PDF...")],
            )
        )

    threading.Thread(
        target=_generate_and_send,
        args=(user_id, items, doc_info, show_customer),
        daemon=True,
    ).start()


# ── Download endpoint ─────────────────────────────────────────────────────────
@app.route("/download/<file_id>")
def download(file_id):
    try:
        uuid.UUID(file_id)
    except ValueError:
        abort(400)

    path = TEMP_DIR / f"{file_id}.pdf"
    if not path.exists():
        abort(404)

    return send_file(
        str(path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="ใบส่งสินค้าชั่วคราว.pdf",
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
