import os
import sys
import json
import uuid
import datetime
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import requests

# =============================
# حذف أي Webhook قديم لتجنب خطأ 409
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN غير معرّف في متغيرات البيئة.")
    sys.exit(1)

# =============================
# ملفات البيانات
GOODS_FILE = "goods.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
BALANCE_FILE = "balance.json"
PENDING_FILE = "pending.json"

# =============================
# روابط الصور
WELCOME_IMAGE_URL = "https://i.imgur.com/3iKcKqC.png"
LOADING_IMAGES = [
    "https://i.imgur.com/3iKcKqC.png",
    "https://i.imgur.com/2h0X6sY.png",
    "https://i.imgur.com/pX1aY0F.png",
]

# =============================
# دوال مساعدة
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def random_loading_image():
    return random.choice(LOADING_IMAGES)

def build_main_keyboard(for_uid=None):
    kb = [
        [InlineKeyboardButton("🛍️ عرض السلع", callback_data="show_goods")],
        [InlineKeyboardButton("📥 إيداع", callback_data="deposit")],
        [InlineKeyboardButton("💳 رصيدك", callback_data="check_balance")],
        [InlineKeyboardButton("🎮 لعبة (حجر/ورق/مقص)", callback_data="game_rps")],
        [InlineKeyboardButton("💬 تواصل مع المسؤول", url="https://t.me/mhama1kjokbi")],
    ]
    if str(for_uid) == str(ADMIN_ID):
        kb.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

def build_goods_keyboard():
    kb = []
    for item in goods:
        kb.append([InlineKeyboardButton(f"{item['name']} - {item['price']} ل.س", callback_data=f"buy_{item['id']}")])
    kb.append([InlineKeyboardButton("◀️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

def build_admin_keyboard():
    kb = [
        [InlineKeyboardButton("💳 شحن (عرض السلع كما للمستخدم)", callback_data="admin_show_goods")],
        [InlineKeyboardButton("📋 عرض المستخدمين", callback_data="admin_show_users")],
        [InlineKeyboardButton("💰 تعديل أسعار", callback_data="admin_edit_price")],
        [InlineKeyboardButton("🕒 التاريخ والوقت", callback_data="admin_time")],
        [InlineKeyboardButton("◀️ رجوع", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(kb)

# =============================
# تحميل البيانات
goods = load_json(GOODS_FILE, [
    {"id":1,"name":"فري فاير 110","price":12000,"image":"https://i.imgur.com/1.png"},
    {"id":2,"name":"فري فاير 231","price":38000,"image":"https://i.imgur.com/2.png"},
    {"id":3,"name":"فري فاير 583","price":60000,"image":"https://i.imgur.com/3.png"},
    {"id":4,"name":"فري فاير 1188","price":120000,"image":"https://i.imgur.com/4.png"},
    {"id":5,"name":"ببجي 60","price":12000,"image":"https://i.imgur.com/6.png"},
    {"id":6,"name":"ببجي 320","price":60000,"image":"https://i.imgur.com/7.png"},
])
users = load_json(USERS_FILE, {})
orders = load_json(ORDERS_FILE, [])
balance = load_json(BALANCE_FILE, {})
pending = load_json(PENDING_FILE, {})
# =============================
# دالة /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    context.user_data["expecting_account_id"] = True
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=WELCOME_IMAGE_URL,
            caption=(
                "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥\n\n"
                "أرسل **ID حساب اللعبة** الآن (يجب أن يكون **10 أرقام**) — سيُطلب في كل مرة."
            ),
            reply_markup=build_main_keyboard(for_uid=uid),
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text(
            "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥\n\n"
            "أرسل **ID حساب اللعبة** الآن (يجب أن يكون **10 أرقام**) — سيُطلب في كل مرة.",
            reply_markup=build_main_keyboard(for_uid=uid),
            parse_mode="Markdown"
        )

# =============================
# MessageHandler
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()

    # تسجيل ID الحساب
    if context.user_data.get("expecting_account_id"):
        if not text.isdigit() or len(text) != 10:
            await update.message.reply_text("❌ يجب أن يكون ID الحساب **10 أرقام**. حاول مرة أخرى.", parse_mode="Markdown")
            return
        users[uid] = users.get(uid, {})
        users[uid]["username"] = update.effective_user.username or update.effective_user.full_name or users[uid].get("username","")
        users[uid]["account_id"] = text
        users[uid]["registered_at"] = datetime.datetime.utcnow().isoformat()
        save_json(USERS_FILE, users)
        if uid not in balance:
            balance[uid] = 0
            save_json(BALANCE_FILE, balance)
        context.user_data["expecting_account_id"] = False
        await update.message.reply_text(
            "✅ تم تسجيل ID حسابك بنجاح.\nاستخدم الأزرار لاختيار ما تريد.",
            reply_markup=build_main_keyboard(for_uid=uid)
        )
        return

    # تعامل الأدمن مع الإيداع
    if str(uid) == str(ADMIN_ID) and context.user_data.get("awaiting_deposit"):
        deposit_id = context.user_data.pop("awaiting_deposit")
        try:
            amount = int(text.replace(",", "").strip())
        except:
            context.user_data["awaiting_deposit"] = deposit_id
            await update.message.reply_text("❌ ادخل مبلغ صحيح بالأرقام فقط.")
            return
        dep = pending.get(deposit_id)
        if not dep:
            await update.message.reply_text("❌ لم أجد عملية الإيداع أو انتهت صلاحيتها.")
            return
        user_id = dep["user_id"]
        balance[user_id] = balance.get(user_id,0)+amount
        save_json(BALANCE_FILE, balance)
        for ord_ in orders:
            if ord_.get("type")=="deposit" and ord_.get("deposit_id")==deposit_id:
                ord_["status"]="مقبول"
        save_json(ORDERS_FILE, orders)
        try:
            await context.bot.send_message(chat_id=int(user_id), text=f"✅ تم قبول الإيداع وإضافة {amount} ل.س إلى رصيدك.")
        except:
            pass
        if deposit_id in pending:
            del pending[deposit_id]
            save_json(PENDING_FILE, pending)
        await update.message.reply_text(f"✅ Added {amount} ل.س to user {user_id}.")
        return

    # تعاملات أخرى (يمكن إضافة وظائف أخرى لاحقاً)
    await update.message.reply_text(text)
    # =============================
# CallbackQueryHandler
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = str(query.from_user.id)
    chat_id = query.message.chat.id
    message_id = query.message.message_id

    # العودة للقائمة الرئيسية
    if data=="back_main":
        await query.message.edit_text("القائمة الرئيسية:", reply_markup=build_main_keyboard(for_uid=uid))
        return

    # عرض السلع
    if data=="show_goods":
        try:
            img = random_loading_image()
            await context.bot.send_photo(chat_id=chat_id, photo=img, caption="جاري التحميل...")
        except:
            pass
        await query.message.reply_text("اختر السلعة:", reply_markup=build_goods_keyboard())
        return

    # التحقق من الرصيد
    if data=="check_balance":
        bal = balance.get(uid, 0)
        await query.message.reply_text(f"💳 رصيدك الحالي: {bal} ل.س")
        return

    # الإيداع
    if data=="deposit":
        context.user_data["expecting_deposit"] = True
        await query.message.reply_text(f"📥 للإيداع: حول المبلغ إلى 97675410 ثم أرسل رقم العملية هنا.")
        return

    # لعبة RPS
    if data=="game_rps":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✊ حجر", callback_data="rps_rock")],
            [InlineKeyboardButton("🖐️ ورق", callback_data="rps_paper")],
            [InlineKeyboardButton("✌️ مقص", callback_data="rps_scissors")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_main")]
        ])
        try:
            img = random_loading_image()
            await context.bot.send_photo(chat_id=chat_id, photo=img, caption="جاري تجهيز اللعبة...")
        except:
            pass
        await query.message.reply_text("اختر: حجر، ورق أو مقص", reply_markup=kb)
        return

    # اختيار حجر/ورق/مقص
    if data.startswith("rps_"):
        choice = data.split("_",1)[1]
        options = ["rock","paper","scissors"]
        bot_choice = random.choice(options)
        map_show = {"rock":"✊ حجر","paper":"🖐️ ورق","scissors":"✌️ مقص"}
        if bot_choice == choice:
            res = "تعادل 🤝"
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            res = "فزت 🎉"
        else:
            res = "خسرت 😞"
        await query.message.reply_text(f"أنت: {map_show[choice]}\nالبوت: {map_show[bot_choice]}\n\nالنتيجة: {res}")
        return

    # شراء سلعة
    if data.startswith("buy_"):
        item_id = int(data.split("_",1)[1])
        item = next((i for i in goods if i["id"] == item_id), None)
        if not item:
            await query.message.reply_text("❌ خطأ: السلعة غير موجودة.")
            return
        if uid not in users or not users.get(uid,{}).get("account_id"):
            await query.message.reply_text("❌ يرجى أولاً إرسال ID حسابك عبر /start ثم إعادة اختيار السلعة.")
            return
        text_caption = f"📦 تم اختيار: {item['name']}\nالسعر: {item['price']} ل.س\n\n⏳ سيتم إرسال الطلب للأدمن للمراجعة."
        try:
            if item.get("image"):
                await context.bot.send_photo(chat_id=int(uid), photo=item.get("image"), caption=text_caption)
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
        # =============================
# التعامل مع طلبات الأدمن والإيداع
async def disable_message_buttons(context, chat_id, message_id, text=None):
    try:
        if text:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        else:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception as e:
        print("disable_message_buttons error:", e)

# =============================
# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")

# =============================
# تشغيل البوت
def main():
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_error_handler(error_handler)

    print("🤖 البوت شغال الآن...")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES)

# =============================
if __name__ == "__main__":
    main()
