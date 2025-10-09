# main.py
import os, json, uuid, requests, time
from threading import Thread
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ====== إعدادات ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 6365858942)
DEPOSIT_NUMBER = os.getenv("DEPOSIT_NUMBER") or "97675410"

# ====== ملفات JSON ======
GOODS_FILE = "goods.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
BALANCE_FILE = "balance.json"
PENDING_FILE = "pending.json"

# ====== صفحة keep-alive (Flask على المنفذ 5000) ======
app = Flask("")
@app.route("/")
def home():
    return "✅ البوت شغال تمام!"

def run_web():
    app.run(host="0.0.0.0", port=5000)

def ping_self():
    url = f"https://{os.getenv('REPLIT_DOMAINS', '').split(',')[0]}" if os.getenv('REPLIT_DOMAINS') else None
    while True:
        try:
            if url:
                requests.get(url, timeout=5)
                print("🔁 Ping sent to keep alive.")
        except Exception as e:
            print(f"⚠️ Ping failed: {e}")
        time.sleep(60)

def keep_alive():
    t1 = Thread(target=run_web)
    t1.daemon = True
    t1.start()
    t2 = Thread(target=ping_self)
    t2.daemon = True
    t2.start()

# ====== مساعدات قراءة/حفظ JSON ======
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ====== البيانات الافتراضية للسلع (تضم كل الفئات مع صور افتراضية) ======
goods = load_json(GOODS_FILE, [
    {"id":1,"name":"فري فاير 110","price":12000,"image":"https://i.imgur.com/1.png"},
    {"id":2,"name":"فري فاير 231","price":38000,"image":"https://i.imgur.com/2.png"},
    {"id":3,"name":"فري فاير 583","price":60000,"image":"https://i.imgur.com/3.png"},
    {"id":4,"name":"فري فاير 1188","price":120000,"image":"https://i.imgur.com/4.png"},
    {"id":5,"name":"فري فاير 2420","price":240000,"image":"https://i.imgur.com/5.png"},
    {"id":6,"name":"ببجي 60","price":12000,"image":"https://i.imgur.com/6.png"},
    {"id":7,"name":"ببجي 320","price":60000,"image":"https://i.imgur.com/7.png"},
    {"id":8,"name":"ببجي 660","price":120000,"image":"https://i.imgur.com/8.png"},
    {"id":9,"name":"ببجي 1800","price":280000,"image":"https://i.imgur.com/9.png"},
    {"id":10,"name":"ببجي 3850","price":560000,"image":"https://i.imgur.com/10.png"}
])

users = load_json(USERS_FILE, {})
orders = load_json(ORDERS_FILE, [])
balance = load_json(BALANCE_FILE, {})
pending = load_json(PENDING_FILE, {})

# ====== دوال بناء الـ keyboards ======
def build_main_keyboard():
    kb = []
    kb.append([InlineKeyboardButton("🛍️ عرض السلع", callback_data="show_goods")])
    kb.append([InlineKeyboardButton("📥 إيداع", callback_data="deposit")])
    kb.append([InlineKeyboardButton("💳 رصيدك", callback_data="check_balance")])
    return InlineKeyboardMarkup(kb)

def build_goods_keyboard():
    kb = []
    for item in goods:
        kb.append([InlineKeyboardButton(f"{item['name']} - {item['price']} ل.س", callback_data=f"buy_{item['id']}")])
    kb.append([InlineKeyboardButton("📥 إيداع", callback_data="deposit")])
    kb.append([InlineKeyboardButton("◀️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

# ====== /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.full_name or ""
    if uid not in users:
        users[uid] = {"username": username, "account_id": ""}
        save_json(USERS_FILE, users)
    if uid not in balance:
        balance[uid] = 0
        save_json(BALANCE_FILE, balance)
    await update.message.reply_text("مرحباً! 👋\nلتسجيل حسابك أرسل ID حساب اللعبة الآن (مثلاً ID فري فاير أو ببجي).", reply_markup=build_main_keyboard())

# ====== معالجة النصوص (ID الحساب أو رقم العملية أو مدخل الأدمن للمبلغ) ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()

    # 1) حالة: الأدمن يكتب مبلغ قبول إيداع (ننتظر في user_data)
    if str(uid) == str(ADMIN_ID) and context.user_data.get("awaiting_deposit"):
        deposit_id = context.user_data.pop("awaiting_deposit")
        try:
            amount = int(text.replace(",", "").strip())
        except:
            await update.message.reply_text("❌ ادخل مبلغ صحيح بالأرقام فقط (مثال: 10000).")
            context.user_data["awaiting_deposit"] = deposit_id
            return
        dep = pending.get(deposit_id)
        if not dep:
            await update.message.reply_text("❌ لم أجد عملية الإيداع أو انتهت صلاحيتها.")
            return
        user_id = dep["user_id"]
        balance[user_id] = balance.get(user_id, 0) + amount
        save_json(BALANCE_FILE, balance)
        for ord in orders:
            if ord.get("type") == "deposit" and ord.get("deposit_id") == deposit_id:
                ord["status"] = "مقبول"
        save_json(ORDERS_FILE, orders)
        try:
            await context.bot.send_message(chat_id=int(user_id), text=f"✅ تم قبول الإيداع وإضافة {amount} ل.س إلى رصيدك.")
        except:
            pass
        del pending[deposit_id]
        save_json(PENDING_FILE, pending)
        await update.message.reply_text(f"✅ Added {amount} ل.س to user {user_id}.")
        return

    # 2) حالة: لو المستخدم لم يسجل account_id بعد => النص يُعتبر ID اللعبة
    if uid not in users or not users[uid].get("account_id"):
        users[uid] = users.get(uid, {})
        users[uid]["username"] = update.effective_user.username or update.effective_user.full_name or users[uid].get("username","")
        users[uid]["account_id"] = text
        save_json(USERS_FILE, users)
        if uid not in balance:
            balance[uid] = 0
            save_json(BALANCE_FILE, balance)
        await update.message.reply_text("✅ تم تسجيل ID حسابك بنجاح.\nالآن اضغط على '🛍️ عرض السلع' لاختيار شحن أو استخدم '📥 إيداع' لإرسال رقم العملية.", reply_markup=build_main_keyboard())
        return

    # 3) حالة: المستخدم أرسل رقم عملية (بعد ضغط زر إيداع)
    if context.user_data.get("expecting_deposit"):
        operation = text
        deposit_id = str(uuid.uuid4())
        pending[deposit_id] = {"user_id": uid, "operation": operation}
        save_json(PENDING_FILE, pending)
        orders.append({
            "id": str(uuid.uuid4()),
            "type": "deposit",
            "deposit_id": deposit_id,
            "user_id": uid,
            "username": users.get(uid,{}).get("username",""),
            "account_id": users.get(uid,{}).get("account_id",""),
            "operation": operation,
            "status": "معلق"
        })
        save_json(ORDERS_FILE, orders)
        bal_user = balance.get(uid, 0)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ قبول الإيداع", callback_data=f"deposit_accept_{deposit_id}"),
            InlineKeyboardButton("❌ رفض الإيداع", callback_data=f"deposit_reject_{deposit_id}")
        ]])
        try:
            await context.bot.send_message(chat_id=ADMIN_ID,
                text=(f"📥 طلب إيداع جديد\n"
                      f"المستخدم: @{users.get(uid,{}).get('username','')}\n"
                      f"Telegram ID: {uid}\n"
                      f"رقم العملية: {operation}\n"
                      f"رصيد الزبون الحالي: {bal_user} ل.س"),
                reply_markup=kb)
        except Exception:
            pass
        context.user_data["expecting_deposit"] = False
        await update.message.reply_text("✅ تم إرسال رقم العملية للأدمن للمراجعة. شكرًا.")
        return

    # 4) الحالة الافتراضية
    await update.message.reply_text("⚠️ لم أتمكن من فهم رسالتك. استخدم الأزرار أو أرسل /start للبدء.", reply_markup=build_main_keyboard())

# ====== تعامل مع أزرار Inline ======
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    from_user = query.from_user
    uid = str(from_user.id)

    if data == "show_goods":
        await query.message.edit_text("اختر السلعة:", reply_markup=build_goods_keyboard())
        return

    if data == "back_main":
        await query.message.edit_text("القائمة الرئيسية:", reply_markup=build_main_keyboard())
        return

    if data == "check_balance":
        bal = balance.get(uid, 0)
        await query.message.reply_text(f"💳 رصيدك الحالي: {bal} ل.س")
        return

    if data == "deposit":
        context.user_data["expecting_deposit"] = True
        await query.message.reply_text(f"📥 للإيداع: حول المبلغ إلى {DEPOSIT_NUMBER} ثم أرسل رقم العملية هنا.")
        return

    if data.startswith("buy_"):
        item_id = int(data.split("_",1)[1])
        item = next((i for i in goods if i["id"] == item_id), None)
        if not item:
            await query.message.reply_text("❌ خطأ: السلعة غير موجودة.")
            return

        if uid not in users or not users.get(uid,{}).get("account_id"):
            await query.message.reply_text("❌ يرجى أولاً إرسال ID حسابك عبر /start ثم إعادة اختيار السلعة.")
            return

        img = item.get("image")
        text_caption = f"📦 تم اختيار: {item['name']}\nالسعر: {item['price']} ل.س\n\n⏳ سيتم إرسال الطلب للأدمن للمراجعة."
        try:
            if img:
                await context.bot.send_photo(chat_id=int(uid), photo=img, caption=text_caption)
            else:
                await query.message.reply_text(text_caption)
        except:
            await query.message.reply_text(text_caption)

        order_id = str(uuid.uuid4())
        orders.append({
            "id": order_id,
            "type": "purchase",
            "user_id": uid,
            "username": users.get(uid,{}).get("username",""),
            "account_id": users.get(uid,{}).get("account_id",""),
            "item": item["name"],
            "price": item["price"],
            "status": "معلق"
        })
        save_json(ORDERS_FILE, orders)

        bal_user = balance.get(uid, 0)
        kb_admin = InlineKeyboardMarkup([[
            InlineKeyboardButton("ID الحساب", callback_data=f"showid_{order_id}"),
            InlineKeyboardButton("✅ قبول", callback_data=f"approve_{order_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{order_id}")
        ]])
        try:
            await context.bot.send_message(chat_id=ADMIN_ID,
                text=(f"📥 طلب شحن جديد\n"
                      f"المستخدم: @{users.get(uid,{}).get('username','')}\n"
                      f"Telegram ID: {uid}\n"
                      f"السلعة: {item['name']}\n"
                      f"السعر: {item['price']} ل.س\n"
                      f"رصيد الزبون الحالي: {bal_user} ل.س"),
                reply_markup=kb_admin)
        except:
            pass
        return

    if data.startswith("showid_"):
        order_id = data.split("_",1)[1]
        order = next((o for o in orders if o["id"] == order_id), None)
        if not order:
            await query.message.reply_text("❌ لم يتم العثور على الطلب.")
            return
        await query.message.reply_text(f"ID الحساب للمستخدم @{order['username']}: {order.get('account_id','')}")
        return

    if data.startswith("approve_") or data.startswith("reject_"):
        action, order_id = data.split("_",1)
        order = next((o for o in orders if o["id"] == order_id), None)
        if not order:
            await query.message.reply_text("❌ لم يتم العثور على الطلب.")
            return

        if order["status"] != "معلق":
            await query.message.reply_text(f"⚠️ الطلب تم التعامل معه مسبقًا ({order['status']}).")
            return

        if action == "approve":
            if order.get("type") == "purchase":
                user_id = order["user_id"]
                price = int(order.get("price",0))
                user_bal = balance.get(user_id, 0)
                if user_bal < price:
                    await query.message.reply_text("⚠️ رصيد المستخدم غير كافٍ لخصم السعر. يمكنك إضافة الرصيد يدوياً ثم إعادة المحاولة.")
                    return
                balance[user_id] = user_bal - price
                order["status"] = "مقبول"
                save_json(BALANCE_FILE, balance)
                save_json(ORDERS_FILE, orders)
                try:
                    await context.bot.send_message(chat_id=int(user_id), text=f"✅ تم قبول طلبك ({order['item']}) وتم خصم {price} ل.س من رصيدك. رصيدك الآن: {balance[user_id]} ل.س")
                except:
                    pass
                await query.message.edit_text(f"✅ تم قبول الطلب: {order['item']}")
            else:
                order["status"] = "مقبول"
                save_json(ORDERS_FILE, orders)
                await query.message.edit_text("✅ تم قبول الطلب.")
            return

        elif action == "reject":
            order["status"] = "مرفوض"
            save_json(ORDERS_FILE, orders)
            try:
                await context.bot.send_message(chat_id=int(order["user_id"]), text=f"❌ تم رفض طلبك ({order['item']}).")
            except:
                pass
            await query.message.edit_text(f"❌ تم رفض الطلب: {order['item']}")
            return

    if data.startswith("deposit_accept_") or data.startswith("deposit_reject_"):
        parts = data.split("_",2)
        kind = parts[0] + "_" + parts[1]
        deposit_id = parts[2]
        dep = pending.get(deposit_id)
        if not dep:
            await query.message.reply_text("❌ لم يتم العثور على عملية الإيداع.")
            return

        if kind == "deposit_accept":
            context.user_data["awaiting_deposit"] = deposit_id
            await query.message.reply_text(f"💰 ادخل المبلغ الذي تريد إضافته لرقم العملية {dep['operation']} (للمستخدم {dep['user_id']})")
            return

        elif kind == "deposit_reject":
            for ord in orders:
                if ord.get("type") == "deposit" and ord.get("deposit_id") == deposit_id:
                    ord["status"] = "مرفوض"
            save_json(ORDERS_FILE, orders)
            try:
                await context.bot.send_message(chat_id=int(dep['user_id']), text="❌ تم رفض عملية الإيداع من الأدمن.")
            except:
                pass
            del pending[deposit_id]
            save_json(PENDING_FILE, pending)
            await query.message.edit_text("❌ تم رفض عملية الإيداع.")
            return

# ====== بدء البوت ======
def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern=".*"))

    print("✅ Handlers added. Bot starting...")
    app.run_polling()

if __name__ == "__main__":
    main()
    # ===== Keep-alive + تشغيل البوت 24/7 =====
from threading import Thread

def start_keep_alive():
    # Flask لازم يكون هو التطبيق الرئيسي لـ Render
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

def start_bot_thread():
    # تأكد من أن run_telegram_bot موجود في كودك الأصلي
    bot_thread = Thread(target=run_telegram_bot)
    bot_thread.daemon = True
    bot_thread.start()

if __name__ == "__main__":
    start_bot_thread()
    start_keep_alive()
