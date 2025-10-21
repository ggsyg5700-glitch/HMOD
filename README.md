# 🤖 بوت متجر الألعاب - Telegram Bot

بوت تليجرام لبيع شحنات فري فاير وببجي مع نظام إدارة كامل.

## ⚙️ المتطلبات

- Python 3.11+
- حساب تليجرام بوت (من @BotFather)

## 🚀 طرق التشغيل

### 1️⃣ التشغيل على Replit (الطريقة الحالية)

البوت شغال حالياً هنا على Replit. فقط اضغط زر Run!

**ملاحظة**: إذا بدك تشغل البوت في مكان آخر، **لازم توقفه هنا أولاً**.

---

### 2️⃣ التشغيل على Render

#### خطوات النشر:

1. **روح على** [render.com](https://render.com) وسجل دخول

2. **اضغط "New +" → Web Service**

3. **اربط مستودع GitHub**:
   - ارفع الكود لـ GitHub أو استخدم "Public Git Repository"
   - الصق رابط مستودعك

4. **التكوين**:
   - **Name**: `telegram-bot` (أو أي اسم)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`

5. **أضف المتغيرات البيئية** (Environment Variables):
   ```
   BOT_TOKEN = توكن البوت من @BotFather
   ADMIN_ID = رقم حسابك في تليجرام
   DEPOSIT_NUMBER = 97675410
   ```

6. **اضغط "Create Web Service"**

7. **انتظر** حتى ينتهي التنصيب (3-5 دقائق)

8. **✅ البوت شغال!** جرب `/start` في تليجرام

#### حل مشكلة IndentationError:

إذا ظهر خطأ في Render، شغل هذا الأمر قبل رفع الكود:

```bash
# تصحيح المسافات
pip install autopep8
autopep8 --in-place --aggressive main.py
```

---

### 3️⃣ التشغيل على n8n

#### طريقة 1: Telegram Trigger (الأسهل)

1. افتح n8n → Create new workflow
2. أضف **Telegram Trigger** node
3. اختر **On message**
4. أدخل `BOT_TOKEN`
5. Active الـ workflow

**⚠️ ملاحظة**: n8n سيتحكم بالبوت بالكامل، لازم توقف البوت من أي مكان آخر.

#### طريقة 2: Integration مع البوت الموجود

إذا بدك البوت يشتغل هنا + إرسال إشعارات لـ n8n:

```python
# في n8n: أضف Webhook node وانسخ الرابط
# ثم أضف هذا الكود في main.py:

import httpx

N8N_WEBHOOK = "https://your-n8n.com/webhook/xxxxx"

async def send_to_n8n(event_type, data):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(N8N_WEBHOOK, json={
                "event": event_type,
                "data": data
            })
    except Exception as e:
        print(f"n8n error: {e}")

# استخدمه مثلاً عند طلب جديد:
await send_to_n8n("new_order", {
    "user": username,
    "item": item_name,
    "price": price
})
```

---

## 📝 ملاحظات مهمة

### ⚠️ قاعدة مهمة: مكان واحد فقط!

**تليجرام لا يسمح بتشغيل البوت في أكثر من مكان**. لازم توقف البوت من المكان القديم قبل تشغيله في مكان جديد:

| من → إلى | الخطوات |
|---------|---------|
| **Replit → Render** | 1. أوقف البوت في Replit (Stop)<br>2. انشر على Render |
| **Replit → n8n** | 1. أوقف البوت في Replit<br>2. فعّل workflow في n8n |
| **Render → Replit** | 1. Suspend/Delete على Render<br>2. شغّل في Replit |

---

## 🎮 مميزات البوت

- ✅ عرض وبيع شحنات (فري فاير، ببجي)
- ✅ نظام رصيد وإيداع
- ✅ لوحة تحكم للأدمن
- ✅ تعديل الأسعار
- ✅ إرسال رسائل جماعية
- ✅ لعبة حجر/ورق/مقص
- ✅ تتبع الطلبات

---

## 🔧 التطوير المستقبلي

يمكنك إضافة:
- 🔗 Integration مع n8n للإشعارات
- 📊 قاعدة بيانات PostgreSQL
- 💳 بوابة دفع (Stripe)
- 📈 تحليلات وإحصائيات

---

## 📞 الدعم

للمشاكل والاستفسارات، تواصل عبر التليجرام.

---

**صنع بـ ❤️ لمتجر الألعاب**
