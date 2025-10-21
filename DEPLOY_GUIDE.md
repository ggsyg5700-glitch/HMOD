# 📘 دليل النشر - كيف تشغل البوت في أي مكان

## 🎯 القاعدة الذهبية

**⚠️ يمكن تشغيل البوت في مكان واحد فقط في نفس الوقت!**

تليجرام لا يسمح بتشغيل نفس البوت في أكثر من مكان. قبل تشغيله في مكان جديد، **لازم توقفه من المكان القديم**.

---

## 🟢 الخيار 1: Replit (التشغيل الحالي)

### المميزات:
- ✅ سهل جداً - فقط اضغط Run
- ✅ مجاني بالكامل
- ✅ تعديل الكود مباشرة
- ✅ لا يحتاج تكوين معقد

### الخطوات:
1. تأكد من إدخال `BOT_TOKEN` و `ADMIN_ID` في Secrets
2. اضغط زر **Run** أو شغل البوت من Console
3. ✅ تم! البوت شغال

### لإيقافه:
- اضغط **Stop** في Replit

---

## 🔵 الخيار 2: Render (للاستضافة الدائمة)

### المميزات:
- ✅ استضافة مجانية دائمة
- ✅ البوت يعمل 24/7
- ✅ لا ينام ولا يتوقف
- ✅ احترافي للمشاريع الحقيقية

### الخطوات:

#### 1. تجهيز الكود:

الملفات التالية موجودة في المشروع:
- ✅ `main.py` - الكود الرئيسي
- ✅ `requirements.txt` - المكتبات المطلوبة
- ✅ `runtime.txt` - نسخة Python
- ✅ `render.yaml` - تكوين Render (اختياري)

#### 2. رفع الكود على GitHub:

```bash
# إذا ما عندك Git
git init
git add .
git commit -m "Initial commit"

# أنشئ مستودع على GitHub ثم:
git remote add origin https://github.com/username/your-repo.git
git push -u origin main
```

#### 3. النشر على Render:

1. **افتح** [render.com](https://render.com) وسجل دخول
2. **اضغط** "New +" → **Web Service**
3. **اربط GitHub** أو استخدم Public Git URL
4. **التكوين**:
   - **Name**: `telegram-bot`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Instance Type**: `Free`

5. **Environment Variables** (مهم جداً!):
   اضغط "Advanced" ثم أضف:
   ```
   BOT_TOKEN = التوكن من @BotFather
   ADMIN_ID = رقم حسابك في تليجرام
   DEPOSIT_NUMBER = 97675410
   ```

6. **Create Web Service**

7. **انتظر** 3-5 دقائق حتى يكتمل النشر

8. **✅ جاهز!** جرب `/start` في بوتك

#### حل مشكلة IndentationError:

إذا ظهر خطأ `IndentationError`:

```bash
# في terminal:
pip install autopep8
autopep8 --in-place --aggressive --aggressive main.py
git add main.py
git commit -m "Fix indentation"
git push
```

Render سيعيد النشر تلقائياً.

### لإيقافه:
1. افتح Dashboard في Render
2. اختر الـ service
3. اضغط **Suspend** أو **Delete**

---

## 🟣 الخيار 3: n8n (للأتمتة المتقدمة)

### المميزات:
- ✅ واجهة مرئية سهلة
- ✅ ربط مع خدمات أخرى (Gmail, Sheets, إلخ)
- ✅ منطق معقد بدون كود

### طريقة التشغيل:

#### أ) تشغيل البوت من n8n (التحكم الكامل):

1. **في n8n**:
   - New Workflow
   - أضف **Telegram Trigger** node
   - Operation: **On message**
   - Credentials: أدخل `BOT_TOKEN`

2. **أضف nodes** للمنطق المطلوب:
   - مثال: Send Message node للرد على المستخدم
   - يمكن إضافة AI، Database، إلخ

3. **Active** الـ workflow

4. **⚠️ مهم**: أوقف البوت من Replit أو Render!

#### ب) إرسال إشعارات من البوت إلى n8n:

إذا بدك البوت يشتغل هنا/Render + إشعارات لـ n8n:

1. **في n8n**:
   - أضف **Webhook** node
   - انسخ الـ URL (مثال: `https://n8n.example.com/webhook/abc123`)

2. **في `main.py`** أضف:

```python
import httpx

N8N_WEBHOOK = "https://n8n.example.com/webhook/abc123"

async def send_to_n8n(event, data):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(N8N_WEBHOOK, json={
                "event": event,
                "data": data
            }, timeout=5.0)
    except Exception as e:
        print(f"n8n notification failed: {e}")

# استخدمه عند الطلبات الجديدة:
# في دالة callback_handler عند "buy_":
await send_to_n8n("new_order", {
    "user_id": uid,
    "username": users.get(uid, {}).get("username", ""),
    "item": item["name"],
    "price": item["price"]
})
```

3. **في n8n**: أضف nodes للتعامل مع البيانات:
   - إرسال Email
   - حفظ في Google Sheets
   - إشعار WhatsApp
   - إلخ

---

## 🔄 جدول المقارنة

| المنصة | التكلفة | السهولة | الاستقرار | الأفضل لـ |
|--------|---------|---------|-----------|-----------|
| **Replit** | مجاني | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | التطوير والتجربة |
| **Render** | مجاني | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | الإنتاج 24/7 |
| **n8n** | مجاني* | ⭐⭐⭐ | ⭐⭐⭐⭐ | الأتمتة المعقدة |

*n8n يحتاج سيرفر خاص أو يمكن استخدام n8n Cloud (مدفوع)

---

## 🎯 التوصية

### للمشاريع الصغيرة والتجربة:
→ **استخدم Replit** - سريع وسهل

### لمتجر حقيقي يعمل 24/7:
→ **استخدم Render** - استقرار عالي

### لأتمتة معقدة (إشعارات، AI، تكاملات):
→ **Replit/Render + n8n webhooks**

---

## ⚠️ ملاحظات مهمة

1. **البوت في مكان واحد فقط**:
   - إذا شغلت البوت في Render، أوقفه في Replit
   - إذا فعلت webhook في n8n، أوقف polling في الأماكن الأخرى

2. **المتغيرات البيئية**:
   - **لا ترفع** `BOT_TOKEN` على GitHub (خطر!)
   - استخدم Environment Variables في كل منصة

3. **الملفات JSON**:
   - `goods.json`, `users.json` إلخ تحفظ البيانات
   - لا ترفعها على Git إذا فيها معلومات حساسة
   - لاستخدام أفضل، استخدم قاعدة بيانات حقيقية (PostgreSQL)

4. **التحديثات**:
   - إذا عدلت الكود في Replit، لازم ترفع التحديثات لـ GitHub ثم Render يعيد النشر
   - أو استخدم Render Dashboard → Manual Deploy

---

## 🆘 حل المشاكل الشائعة

### البوت لا يستجيب:
- ✅ تأكد أنه شغال في مكان واحد فقط
- ✅ تحقق من `BOT_TOKEN` صحيح
- ✅ شوف اللوجات (Logs) في المنصة

### IndentationError في Render:
```bash
autopep8 --in-place main.py
```

### Conflict Error:
- يعني البوت شغال في مكانين
- أوقفه من المكان الآخر

### Bot not found:
- تأكد من username البوت صحيح
- جرب `/start` أو @BotFather → /mybots

---

**بالتوفيق! 🚀**
