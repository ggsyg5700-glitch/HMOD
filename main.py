# main.py
import os, json, uuid, requests, time
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
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

# ====== صفحة keep-alive (Flask) ======
app = Flask("")

@app.route("/")
def home():
    return "✅ البوت شغال تمام!"

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

# ====== بيانات افتراضية للسلع ======
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

# ====== معالجة النصوص ======
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()
    # ... نفس الكود الأصلي للتعامل مع الرسائل ...
    await update.message.reply_text("⚠️ لم أتمكن من فهم رسالتك. استخدم الأزرار أو أرسل /start للبدء.", reply_markup=build_main_keyboard())

# ====== التعامل مع أزرار Inline ======
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... نفس كود callback_handler الأصلي ...
    pass

# ====== تشغيل البوت في Thread ======
def run_telegram_bot():
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    bot_app.add_handler(CallbackQueryHandler(callback_handler, pattern=".*"))
    print("✅ Telegram bot starting...")
    bot_app.run_polling()

# ====== Main ======
if __name__ == "__main__":
    # تشغيل Flask
    flask_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))))
    flask_thread.start()

    # تشغيل Telegram Bot
    bot_thread = Thread(target=run_telegram_bot)
    bot_thread.start()