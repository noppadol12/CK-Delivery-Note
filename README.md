# LINE Bot — ใบส่งสินค้าชั่วคราว

รับไฟล์ PDF ใบกำกับภาษีผ่าน LINE → อ่านรายการสินค้า → ถามว่าแสดงชื่อลูกค้าไหม → สร้าง PDF ใบส่งสินค้าชั่วคราว (ไม่มีราคา)

---

## Flow การทำงาน

```
ผู้ใช้ส่ง PDF ใบกำกับภาษี
       ↓
Bot อ่านเอกสาร (Claude API)
       ↓
Bot ถาม: "แสดงชื่อลูกค้าไหม?" [✅ แสดง] [🚫 ไม่แสดง]
       ↓
สร้าง PDF ใบส่งสินค้าชั่วคราว (มี/ไม่มีชื่อลูกค้า)
       ↓
ส่งลิงก์ดาวน์โหลด PDF กลับใน LINE
```

---

## โครงสร้างไฟล์

```
├── app.py           # Flask webhook + LINE event handlers
├── extractor.py     # อ่านข้อมูลจาก PDF ด้วย Claude API
├── generator.py     # สร้าง PDF ใบส่งสินค้า (fpdf2 + Sarabun font)
├── requirements.txt
├── Procfile         # สำหรับ Railway / Render
├── .env.example     # ตัวอย่าง environment variables
└── fonts/           # Sarabun font (ดาวน์โหลดอัตโนมัติตอน startup)
```

---

## วิธี Deploy บน Railway (แนะนำ)

### 1. Push ขึ้น GitHub

```bash
git init
git add .
git commit -m "Initial LINE bot"
git remote add origin https://github.com/YOUR_USERNAME/line-delivery-bot.git
git push -u origin main
```

### 2. สร้าง Project บน Railway

1. ไปที่ [railway.app](https://railway.app) → **New Project**
2. เลือก **Deploy from GitHub repo**
3. เลือก repo `line-delivery-bot`
4. Railway จะ detect Python และ build อัตโนมัติ

### 3. ตั้งค่า Environment Variables

ใน Railway → Settings → Variables เพิ่ม:

| Key | Value |
|-----|-------|
| `LINE_CHANNEL_ACCESS_TOKEN` | จาก LINE Developers Console |
| `LINE_CHANNEL_SECRET` | จาก LINE Developers Console |
| `ANTHROPIC_API_KEY` | จาก console.anthropic.com |
| `BASE_URL` | URL ของ Railway app เช่น `https://xxx.railway.app` |

### 4. ตั้งค่า LINE Webhook

1. ไปที่ [LINE Developers Console](https://developers.line.biz)
2. เลือก Channel → **Messaging API**
3. Webhook URL: `https://YOUR_APP.railway.app/webhook`
4. เปิด **Use webhook**
5. ปิด **Auto-reply messages**

---

## วิธีทดสอบ Local

```bash
# ติดตั้ง dependencies
pip install -r requirements.txt

# สร้างไฟล์ .env
cp .env.example .env
# แก้ไข .env ใส่ค่าจริง

# รัน server
python app.py

# ใช้ ngrok expose local server
ngrok http 5000
# แล้วเอา URL จาก ngrok ไปใส่ใน LINE Webhook URL
```

---

## หมายเหตุ

- PDF ที่สร้างจะหมดอายุใน **1 ชั่วโมง** (ลบอัตโนมัติ)
- ถ้า Bot ไม่ตอบภายใน 10 นาทีหลังส่ง PDF จะต้องส่งใหม่
- ใบส่งสินค้าชั่วคราว **ไม่แสดงราคา** ทุกกรณี
- Font Sarabun จะดาวน์โหลดอัตโนมัติตอน startup ครั้งแรก
