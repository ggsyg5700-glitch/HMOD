import requests
import os
import sys
import json
import uuid
import datetime
import zipfile
import io
import time
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory, send_file
from functools import wraps
from threading import Thread

# --- تهيئة المتغيرات الأساسية ---
BOT_START_TIME = time.time() # استخدام timestamp لحساب الوقت بدقة
user_message_counts = defaultdict(list)
spam_warned_users = set()

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        MessageHandler,
        CallbackQueryHandler,
        ContextTypes,
        filters
    )
except ImportError:
    print("ERROR: python-telegram-bot غير مثبت بشكل صحيح.")
    sys.exit(1)

app = Flask(__name__)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_ID = int((os.getenv("ADMIN_ID") or "0").strip())
DEPOSIT_NUMBER = (os.getenv("DEPOSIT_NUMBER") or "97675410").strip()
PORT = int((os.getenv("PORT") or "8081").strip())
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "admin123").strip()
API_TOKEN = (os.getenv("API_TOKEN") or "admin_token_secure_123").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip().rstrip("/")
USE_WEBHOOK = bool(WEBHOOK_URL)

_explicit_url = (os.getenv("WEBAPP_URL") or os.getenv("PUBLIC_URL") or WEBHOOK_URL or "").strip().rstrip("/")
if _explicit_url:
    WEBAPP_URL = _explicit_url + "/"
else:
    REPLIT_DOMAIN = os.getenv("REPLIT_DEV_DOMAIN") or os.getenv("REPLIT_DOMAINS", "").split(",")[0]
    WEBAPP_URL = f"https://{REPLIT_DOMAIN}/" if REPLIT_DOMAIN else ""

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN غير معرّف في متغيرات البيئة.")
    sys.exit(1)

if ADMIN_ID == 0:
    print("ERROR: ADMIN_ID غير معرّف أو قيمته 0.")
    sys.exit(1)

# --- ملفات البيانات ---
GOODS_FILE = "goods.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
BALANCE_FILE = "balance.json"
SETTINGS_FILE = "settings.json"
VIOLATIONS_FILE = "violations.json"

# --- تخزين البيانات: PostgreSQL إن وُجد، وإلا ملفات JSON ---
from threading import Lock

_DB_URL = (os.getenv("DATABASE_URL") or "").strip()
_db_lock = Lock()
_USE_DB = False

if _DB_URL:
    try:
        import psycopg2
        from psycopg2.extras import Json
        from psycopg2 import pool as psycopg2_pool

        _db_pool = psycopg2_pool.ThreadedConnectionPool(1, 10, _DB_URL)

        def _db_conn():
            return _db_pool.getconn()

        def _db_release(conn):
            _db_pool.putconn(conn)

        with _db_conn() as _c, _c.cursor() as _cur:
            _cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_kv (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            _c.commit()
        _db_release(_c)
        _USE_DB = True
        print("INFO: Storage = PostgreSQL (pool)")
    except Exception as _e:
        print(f"WARNING: PostgreSQL not available ({_e}); falling back to JSON files")
        _USE_DB = False
else:
    print("INFO: DATABASE_URL not set; using JSON files for storage")

def load_json(path, default):
    if _USE_DB:
        with _db_lock:
            conn = _db_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM bot_kv WHERE key = %s", (path,))
                    row = cur.fetchone()
                    if row is not None:
                        return row[0]
                    seed = default
                    if os.path.exists(path):
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                seed = json.load(f)
                        except Exception:
                            seed = default
                    cur.execute(
                        "INSERT INTO bot_kv (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                        (path, Json(seed)),
                    )
                    conn.commit()
                    return seed
            finally:
                _db_release(conn)
    # ملفات JSON
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
    if _USE_DB:
        with _db_lock:
            conn = _db_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bot_kv (key, value, updated_at) VALUES (%s, %s, NOW())
                        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
                        """,
                        (path, Json(data)),
                    )
                    conn.commit()
            finally:
                _db_release(conn)
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_ar_time():
    now = datetime.datetime.now() + datetime.timedelta(hours=3)
    return now.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً") + " " + now.strftime("%Y-%m-%d")

# تحميل البيانات
goods = load_json(GOODS_FILE, [])
users = load_json(USERS_FILE, {})
orders = load_json(ORDERS_FILE, [])
balance = load_json(BALANCE_FILE, {})
settings = load_json(SETTINGS_FILE, {"welcome_message": "🎮 أهلاً بك في البوت!", "profit_percentage": 10, "deposit_numbers": ["97675410"]})
violations = load_json(VIOLATIONS_FILE, {})
user_states = {}

# --- منطق البوت (Commands & Handlers) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.effective_user or not update.message:
        return
    
    uid = str(update.effective_user.id)
    user_states[uid] = None
    actual_username = update.effective_user.username
    is_dev = actual_username == "mhama1kjokbi"
    display_username = "المطور" if is_dev else actual_username
    
    if uid not in users:
        role = "admin" if is_dev else "user"
        users[uid] = {"username": display_username, "registered_at": (datetime.datetime.now() + datetime.timedelta(hours=3)).isoformat(), "role": role}
        balance[uid] = 0
        save_json(USERS_FILE, users)
        save_json(BALANCE_FILE, balance)
    
    keyboard = [
        [KeyboardButton("🛍️ السلع"), KeyboardButton("💰 رصيدي")],
        [KeyboardButton("📦 طلباتي"), KeyboardButton("➕ شحن رصيد")],
        [KeyboardButton("⚙️ الإعدادات"), KeyboardButton("👨‍💻 الدعم")],
        [KeyboardButton("🏁 Start")]
    ]
    
    is_admin = users.get(uid, {}).get("role") == "admin" or str(uid) == str(ADMIN_ID)
    if is_admin:
        keyboard.append([KeyboardButton("📊 لوحة الإدارة", web_app=WebAppInfo(url=WEBAPP_URL))])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    welcome_text = "أهلاً بك يا مطور! 🕵️‍♂️\nلوحة التحكم جاهزة تحت تصرفك." if is_dev else settings.get("welcome_message", "أهلاً بك!")
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def goods_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    if not goods:
        await update.message.reply_text("عذراً، لا توجد سلع متوفرة حالياً.")
        return

    keyboard = [
        [InlineKeyboardButton("🔥 فري فاير", callback_data="cat_ff"),
         InlineKeyboardButton("🎯 ببجي",     callback_data="cat_pubg")]
    ]
    await update.message.reply_text(
        "🛍️ اختر اللعبة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    uid = str(update.effective_user.id)
    ubalance = balance.get(uid, 0)
    await update.message.reply_text(f"💰 رصيدك الحالي هو: {ubalance} ليرة")

async def add_balance_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    uid = str(update.effective_user.id)
    user_states[uid] = "awaiting_recharge_proof"
    
    nums = settings.get("deposit_numbers", ["97675410"])
    nums_text = "\n".join([f"{i+1}. `{n}`" for i, n in enumerate(nums)])
    text = f"💳 لشحن رصيدك عبر سيرتيل كاش:\n\n" \
           f"1. افتح تطبيق سيرتيل كاش\n" \
           f"2. اختر التحويل اليدوي\n" \
           f"3. اختر أحد الأرقام:\n{nums_text}\n\n" \
           f"📩 بعد إتمام التحويل، أرسل رقم العملية هنا فقط:"
    await update.message.reply_text(text, parse_mode="Markdown")

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    await update.message.reply_text("👨‍💻 للدعم الفني والاستفسارات، يرجى التواصل مع المطور مباشرة عبر المعرف التالي:\n\n@mhama1kjokbi")

async def settings_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    keyboard = [
        [InlineKeyboardButton("🔔 الإشعارات", callback_data="settings_notif")],
        [InlineKeyboardButton("🌐 اللغة", callback_data="settings_lang")],
        [InlineKeyboardButton("🔄 تحديث البيانات", callback_data="settings_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⚙️ **إعدادات الحساب:**\nاختر أحد الخيارات التالية لتعديله:", reply_markup=reply_markup, parse_mode="Markdown")

async def orders_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    uid = str(update.effective_user.id)
    
    purchase_orders = [o for o in orders if str(o.get('user_id')) == uid and "شحن رصيد" not in o.get('item_name', '')]
    deposit_orders = [o for o in orders if str(o.get('user_id')) == uid and "شحن رصيد" in o.get('item_name', '')]
    
    text = "📦 **طلباتي:**\n\n"
    
    text += "🛒 **مشترياتي:**\n"
    if not purchase_orders: text += "لا يوجد\n"
    for o in purchase_orders[-5:]:
        icon = "✅" if o['status'] == "مكتمل" else "❌" if o['status'] == "مرفوض" else "⏳"
        text += f"{icon} {o['item_name']} | {o['status']}\n"
    
    text += "\n💳 **عمليات الشحن:**\n"
    if not deposit_orders: text += "لا يوجد\n"
    for o in deposit_orders[-5:]:
        icon = "✅" if o['status'] == "مكتمل" else "❌" if o['status'] == "مرفوض" else "⏳"
        text += f"{icon} {o['item_name']} | {o['status']}\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update or not update.message: return
    uid = str(update.effective_user.id)
    text = update.message.text
    if not text: return
    
    if uid in users:
        users[uid]["last_seen"] = get_ar_time()
        save_json(USERS_FILE, users)

    if text.startswith('/') or text in ["🛍️ السلع", "💰 رصيدي", "📦 طلباتي", "➕ شحن رصيد", "⚙️ الإعدادات", "👨‍💻 الدعم", "🏁 Start", "📊 لوحة الإدارة"]:
        return

    if user_states.get(uid) == "awaiting_recharge_proof":
        if not text.isdigit():
            await update.message.reply_text("⚠️ رقم العملية يجب أن يتكون من أرقام فقط. يرجى إرسال الرقم مجدداً:")
            return
        # إنشاء طلب شحن ليظهر في لوحة الأدمن
        recharge_order_id = str(uuid.uuid4())
        orders.append({
            "id": recharge_order_id, "user_id": uid,
            "username": update.effective_user.username or "N/A",
            "item_name": "شحن رصيد", "price": 0, "game_id": text,
            "status": "قيد الانتظار",
            "timestamp": (datetime.datetime.now() + datetime.timedelta(hours=3)).isoformat(),
            "timestamp_formatted": get_ar_time(), "transaction_id": text
        })
        save_json(ORDERS_FILE, orders)
        user_states[f"recharge_order_{uid}"] = recharge_order_id

        admin_msg = (
            f"💳 **طلب شحن جديد**\n\n"
            f"👤 المستخدم: @{update.effective_user.username}\n"
            f"🆔 ID: `{uid}`\n"
            f"🔢 رقم العملية: `{text}`\n\n"
            f"اضغط الزر أدناه لتحديد المبلغ وإتمام الشحن:"
        )
        user_states[f"admin_wait_{uid}"] = text
        charge_kb = [[
            InlineKeyboardButton("💰 تحديد المبلغ وشحن", callback_data=f"charge_ask_{uid}_{text}"),
            InlineKeyboardButton("❌ رفض الطلب",         callback_data=f"reject_{uid}")
        ]]
        await context.bot.send_message(
            chat_id=ADMIN_ID, text=admin_msg,
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(charge_kb)
        )
        await update.message.reply_text("✅ تم إرسال رقم العملية للإدارة، سيتم مراجعته قريباً.")
        user_states[uid] = None
        return

    if user_states.get(uid, "").startswith("awaiting_game_id_"):
        if not text.isdigit():
            await update.message.reply_text("⚠️ يرجى إدخال ID مكون من أرقام فقط (لا يسمح بالحروف).")
            return

        idx = int(user_states[uid].split("_")[3])
        item = goods[idx]
        price = item['price'] + (item['price'] * settings.get('profit_percentage', 0) / 100)
        u_bal = balance.get(uid, 0)
        
        if u_bal < price:
            await update.message.reply_text("❌ رصيدك غير كافٍ.")
            user_states[uid] = None
            return
            
        balance[uid] = u_bal - price
        save_json(BALANCE_FILE, balance)
        
        order_id = str(uuid.uuid4())
        orders.append({
            "id": order_id, "user_id": uid, "username": update.effective_user.username or "N/A",
            "item_name": item['name'], "price": price, "game_id": text, "status": "قيد الانتظار",
            "timestamp": (datetime.datetime.now() + datetime.timedelta(hours=3)).isoformat(),
            "timestamp_formatted": get_ar_time()
        })
        save_json(ORDERS_FILE, orders)
        
        receipt_user = f"🧾 **فاتورة شراء**\n\n📦 السلعة: {item['name']}\n🎮 ID اللعبة: `{text}`\n💰 السعر: {price} ليرة\n🆔 رقم الطلب: `{order_id[:8]}`\n\n⏳ طلبك قيد المراجعة حالياً."
        await update.message.reply_text(receipt_user, parse_mode="Markdown")

        admin_txt = f"🛍️ **طلب شراء جديد (فاتورة)**\n\n👤 الزبون: @{update.effective_user.username}\n📦 السلعة: {item['name']}\n🎮 ID اللعبة: `{text}`\n💰 المبلغ المدفوع: {price} ليرة\n🆔 كود الطلب: `{order_id}`"
        kb = [[InlineKeyboardButton("✅ قبول", callback_data=f"approve_ord_{order_id}"),
               InlineKeyboardButton("❌ رفض", callback_data=f"reject_ord_{order_id}")]]
        await context.bot.send_message(chat_id=ADMIN_ID, text=admin_txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
        user_states[uid] = None
        return

    if str(uid) == str(ADMIN_ID):
        # الحل الثاني: معالجة الشحن المرتبط بمستخدم محدد عبر الزر
        for key in list(user_states.keys()):
            if key.startswith(f"charging_{ADMIN_ID}_"):
                target_uid = key.split(f"charging_{ADMIN_ID}_")[1]
                trans_id = user_states[key]
                try:
                    amount = float(text)
                    kb = [[
                        InlineKeyboardButton(f"✅ تأكيد شحن {amount} ل.س", callback_data=f"confirm_{amount}_{target_uid}_{trans_id}"),
                        InlineKeyboardButton("❌ إلغاء", callback_data=f"reject_{target_uid}")
                    ]]
                    await update.message.reply_text(
                        f"❓ **تأكيد الشحن**\n\n"
                        f"👤 المستخدم: `{target_uid}`\n"
                        f"💰 المبلغ: **{amount} ل.س**\n"
                        f"🔢 رقم العملية: `{trans_id}`",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(kb)
                    )
                    del user_states[key]
                    return
                except ValueError:
                    await update.message.reply_text("⚠️ يرجى إرسال رقم صحيح للمبلغ فقط.")
                    return

        if update.message.reply_to_message:
            reply_text = update.message.reply_to_message.text
            if "ID: `" in reply_text and ("رقم العملية: `" in reply_text or "🔢 رقم العملية:" in reply_text):
                try:
                    target_uid = ""
                    if "ID: `" in reply_text:
                        target_uid = reply_text.split("ID: `")[1].split("`")[0]
                    elif "🆔 ID:" in reply_text:
                        target_uid = reply_text.split("🆔 ID:")[1].split("\n")[0].strip().replace("`", "")
                    
                    trans_id = ""
                    if "رقم العملية: `" in reply_text:
                        trans_id = reply_text.split("رقم العملية: `")[1].split("`")[0]
                    elif "🔢 رقم العملية:" in reply_text:
                        trans_id = reply_text.split("🔢 رقم العملية:")[1].split("\n")[0].strip().replace("`", "")
                    
                    if target_uid and trans_id:
                        amount = float(text)
                        kb = [[InlineKeyboardButton(f"✅ تأكيد إضافة {amount} ل.س", callback_data=f"confirm_{amount}_{target_uid}_{trans_id}")],
                              [InlineKeyboardButton("❌ إلغاء", callback_data=f"reject_deposit")]]
                        await update.message.reply_text(f"❓ هل تريد إضافة {amount} ليرة للمستخدم @{target_uid}؟\nرقم العملية: {trans_id}", reply_markup=InlineKeyboardMarkup(kb))
                        return
                except (ValueError, IndexError):
                    pass

        # الكود القديم كخيار احتياطي
        for key in list(user_states.keys()):
            if key.startswith("admin_wait_"):
                target_uid = key.replace("admin_wait_", "")
                transaction_id = user_states[key]
                try:
                    amount = float(text)
                    kb = [[InlineKeyboardButton(f"✅ تأكيد {amount}", callback_data=f"confirm_{amount}_{target_uid}_{transaction_id}")],
                          [InlineKeyboardButton("❌ إلغاء", callback_data=f"reject_{target_uid}")]]
                    await update.message.reply_text(f"❓ تأكيد إضافة {amount} للعملية {transaction_id}؟", reply_markup=InlineKeyboardMarkup(kb))
                    del user_states[key]
                    return
                except ValueError: pass

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = str(update.effective_user.id)
    
    if data in ("cat_ff", "cat_pubg"):
        is_ff = data == "cat_ff"
        keyword = "فري فاير" if is_ff else "ببجي"
        title   = "🔥 فري فاير" if is_ff else "🎯 ببجي"
        profit  = settings.get('profit_percentage', 0)
        filtered = [(idx, item) for idx, item in enumerate(goods)
                    if keyword in item.get('name', '')]
        if not filtered:
            await query.message.reply_text(f"لا توجد سلع متوفرة لـ {title} حالياً.")
            return
        text = f"{title} — السلع المتوفرة:\n\n"
        kb   = []
        for idx, item in filtered:
            price       = item.get('price', 0)
            total_price = price + (price * profit / 100)
            text += f"• {item['name']} — {total_price:.0f} ل.س\n"
            kb.append([InlineKeyboardButton(f"🛒 شراء {item['name']}", callback_data=f"buy_{idx}")])
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("buy_"):
        idx = int(data.split("_")[1])
        user_states[uid] = f"awaiting_game_id_{idx}"
        await query.message.reply_text(f"🎮 يرجى إدخال ID اللعبة (أرقام فقط):")
    elif data == "settings_notif":
        await query.message.reply_text("🔔 **الإشعارات:** ستتوفر خدمة تخصيص الإشعارات قريباً في التحديث القادم.")
    elif data == "settings_lang":
        await query.message.reply_text("🌐 **اللغة:** يدعم البوت حالياً اللغة العربية فقط، وسيتم إضافة لغات أخرى قريباً.")
    elif data == "settings_refresh":
        await query.message.reply_text("🔄 **تحديث البيانات:** جاري تحديث بيانات حسابك من الخادم... تم التحديث بنجاح.")
    elif data.startswith("approve_ord_"):
        order_id = data.replace("approve_ord_", "")
        for o in orders:
            if o['id'] == order_id:
                if o['status'] != "قيد الانتظار":
                    await query.answer(f"⚠️ هذا الطلب تمت معالجته مسبقاً ({o['status']})", show_alert=True)
                    return
                o['status'] = "مكتمل"
                save_json(ORDERS_FILE, orders)
                await query.edit_message_text(f"✅ تم قبول الطلب بنجاح (عبر تيليغرام).")
                try:
                    invoice_msg = (
                        f"🧾 **فاتورة شراء - محدّثة**\n\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"📦 السلعة: {o.get('item_name', 'N/A')}\n"
                        f"🎮 ID اللعبة: `{o.get('game_id', 'N/A')}`\n"
                        f"💰 السعر المدفوع: {o.get('price', 0)} ليرة\n"
                        f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                        f"🕐 التاريخ: {o.get('timestamp_formatted', get_ar_time())}\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"✅ **الحالة: تمت الموافقة**\n\n"
                        f"🎉 تهانينا! طلبك تم قبوله وسيتم تنفيذه في أقرب وقت."
                    )
                    await context.bot.send_message(chat_id=int(o['user_id']), text=invoice_msg, parse_mode="Markdown")
                except: pass
                break
    elif data.startswith("reject_ord_"):
        order_id = data.replace("reject_ord_", "")
        for o in orders:
            if o['id'] == order_id:
                if o['status'] != "قيد الانتظار":
                    await query.answer(f"⚠️ هذا الطلب تمت معالجته مسبقاً ({o['status']})", show_alert=True)
                    return
                o['status'] = "مرفوض"
                save_json(ORDERS_FILE, orders)
                await query.edit_message_text(f"❌ تم رفض الطلب بنجاح (عبر تيليغرام).")
                try:
                    invoice_msg = (
                        f"🧾 **فاتورة شراء - محدّثة**\n\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"📦 السلعة: {o.get('item_name', 'N/A')}\n"
                        f"🎮 ID اللعبة: `{o.get('game_id', 'N/A')}`\n"
                        f"💰 السعر: {o.get('price', 0)} ليرة\n"
                        f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                        f"🕐 التاريخ: {o.get('timestamp_formatted', get_ar_time())}\n"
                        f"━━━━━━━━━━━━━━━━\n"
                        f"❌ **الحالة: مرفوض**\n\n"
                        f"⚠️ للأسف تم رفض طلبك. للاستفسار تواصل مع الدعم: @mhama1kjokbi"
                    )
                    await context.bot.send_message(chat_id=int(o['user_id']), text=invoice_msg, parse_mode="Markdown")
                except: pass
                break
    elif data.startswith("confirm_"):
        parts = data.split("_")
        amount = float(parts[1])
        target_uid = parts[2]
        trans_id = "_".join(parts[3:])
        balance[target_uid] = balance.get(target_uid, 0) + amount
        save_json(BALANCE_FILE, balance)
        new_balance = balance[target_uid]
        # تحديث الطلب المعلق إن وجد، وإلا إنشاء جديد
        pending_order_id = user_states.pop(f"recharge_order_{target_uid}", None)
        updated = False
        if pending_order_id:
            for o in orders:
                if o['id'] == pending_order_id and o['status'] == "قيد الانتظار":
                    o['status'] = "مكتمل"
                    o['price'] = amount
                    o['item_name'] = f"شحن رصيد ({trans_id})"
                    updated = True
                    break
        if not updated:
            orders.append({
                "id": str(uuid.uuid4()), "user_id": target_uid,
                "item_name": f"شحن رصيد ({trans_id})", "price": amount,
                "status": "مكتمل",
                "timestamp": (datetime.datetime.now() + datetime.timedelta(hours=3)).isoformat(),
                "timestamp_formatted": get_ar_time()
            })
        save_json(ORDERS_FILE, orders)
        await query.edit_message_text(f"✅ تم إضافة {amount} ليرة بنجاح للزبون وتم إبلاغه.")
        try:
            receipt_msg = (
                f"🧾 **إيصال شحن رصيد**\n\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💳 رقم العملية: `{trans_id}`\n"
                f"💰 المبلغ المشحون: {amount} ليرة\n"
                f"🏦 رصيدك الحالي: {new_balance} ليرة\n"
                f"🕐 التاريخ: {get_ar_time()}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"✅ **الحالة: تم الشحن بنجاح**\n\n"
                f"🎉 تم إضافة رصيدك، بالتوفيق في مشترياتك!"
            )
            await context.bot.send_message(chat_id=int(target_uid), text=receipt_msg, parse_mode="Markdown")
        except: pass
    elif data.startswith("charge_ask_"):
        # مثال: charge_ask_{uid}_{trans_id}
        rest = data[len("charge_ask_"):]
        parts = rest.split("_", 1)
        target_uid = parts[0]
        trans_id   = parts[1] if len(parts) > 1 else ""
        # حفظ الحالة مرتبطة بالمستخدم المحدد
        user_states[f"charging_{ADMIN_ID}_{target_uid}"] = trans_id
        await query.edit_message_text(
            f"💰 **تحديد مبلغ الشحن**\n\n"
            f"👤 المستخدم: `{target_uid}`\n"
            f"🔢 رقم العملية: `{trans_id}`\n\n"
            f"أرسل الآن المبلغ المراد إضافته (أرقام فقط):",
            parse_mode="Markdown"
        )
    elif data.startswith("reject_deposit"):
        await query.edit_message_text("❌ تم إلغاء عملية الشحن.")
    elif data.startswith("reject_"):
        target_uid_rej = data.replace("reject_", "")
        # تحديث الطلب المعلق إلى مرفوض
        pending_order_id = user_states.pop(f"recharge_order_{target_uid_rej}", None)
        if pending_order_id:
            for o in orders:
                if o['id'] == pending_order_id:
                    o['status'] = "مرفوض"
                    save_json(ORDERS_FILE, orders)
                    break
        await query.edit_message_text("❌ تم إلغاء عملية الشحن.")
        try:
            await context.bot.send_message(
                chat_id=int(target_uid_rej),
                text="❌ **إشعار شحن رصيد**\n\nللأسف تم رفض طلب شحن رصيدك.\nللاستفسار تواصل مع الدعم: @mhama1kjokbi",
                parse_mode="Markdown"
            )
        except: pass

# --- Flask Server ---
@app.after_request
def add_cors_headers(response):
    allowed_origins = (os.getenv("ALLOWED_ORIGINS") or "").strip()
    origin = request.headers.get("Origin", "")
    if allowed_origins:
        if origin in allowed_origins.split(","):
            response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization') or request.args.get('token')
        if token != API_TOKEN:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route('/health')
@app.route('/ping')
def health():
    return "OK", 200


@app.route('/')
@app.route('/dashboard')
def index():
    response = send_from_directory('static', 'dashboard.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/auth', methods=['POST'])
def api_auth():
    data = request.get_json()
    if data and data.get('password') == ADMIN_PASSWORD:
        return jsonify({"success": True, "token": API_TOKEN})
    return jsonify({"success": False}), 401

@app.route('/api/status')
@require_admin
def api_status():
    total_bal = sum(float(v) for v in balance.values() if v is not None)
    active_users = []
    now_ts = time.time()
    for uid, data in users.items():
        ls = data.get("last_seen")
        if ls:
            # تحويل الوقت العربي إلى timestamp للمقارنة
            try:
                # التنسيق: 09:35 PM 2026-02-14
                ls_clean = ls.replace("صباحاً", "AM").replace("مساءً", "PM")
                ls_dt = datetime.datetime.strptime(ls_clean, "%I:%M %p %Y-%m-%d")
                # تعديل التوقيت (البوت يضيف 3 ساعات)
                ls_ts = ls_dt.timestamp() - (3 * 3600)
                
                # إذا كان آخر ظهور خلال أقل من 19 دقيقة
                if (now_ts - ls_ts) < (19 * 60):
                    active_users.append({"username": data.get("username", "Unknown"), "last_seen": ls})
            except:
                # في حال فشل التحليل، نعتبره غير متصل
                pass
    
    stats = {
        "pending": len([o for o in orders if o['status'] == "قيد الانتظار"]),
        "completed": len([o for o in orders if o['status'] == "مكتمل"]),
        "rejected": len([o for o in orders if o['status'] == "مرفوض"])
    }
    
    # حساب الوقت بدقة
    elapsed = int(time.time() - BOT_START_TIME)
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{hours}س {minutes}د {seconds}ث"

    return jsonify({
        "success": True, 
        "data": {
            "uptime": uptime_str,
            "users_count": len(users), 
            "total_balance": total_bal, 
            "orders_count": len(orders), 
            "active_users": active_users[:6],
            "order_stats": stats
        }
    })

@app.route('/api/goods', methods=['GET', 'POST', 'DELETE'])
@require_admin
def api_goods():
    if request.method == 'GET': return jsonify({"success": True, "data": goods})
    if request.method == 'DELETE':
        item_id = request.args.get('id')
        if not item_id: return jsonify({"success": False, "message": "Missing ID"}), 400
        for i, item in enumerate(goods):
            if str(item.get('id')) == str(item_id):
                goods.pop(i)
                save_json(GOODS_FILE, goods)
                return jsonify({"success": True})
        return jsonify({"success": False, "message": "Not found"}), 404
        
    data = request.get_json()
    try: price = float(data.get("price", 0))
    except: return jsonify({"success": False, "message": "Invalid price"}), 400
    item_id = data.get('id')
    
    # تحسين التعديل لضمان الحفظ
    if item_id:
        found = False
        for i, item in enumerate(goods):
            if str(item.get('id')) == str(item_id):
                goods[i].update({
                    "name": data.get("name"), 
                    "price": price, 
                    "description": data.get("description", "")
                })
                found = True
                break
        if found:
            save_json(GOODS_FILE, goods)
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Item not found"}), 404
    else:
        new_item = {
            "id": str(uuid.uuid4()), 
            "name": data.get("name"), 
            "price": price, 
            "description": data.get("description", "")
        }
        goods.append(new_item)
        save_json(GOODS_FILE, goods)
        return jsonify({"success": True, "data": new_item})

@app.route('/api/orders/<order_id>/status', methods=['PUT'])
@require_admin
def api_order_status(order_id):
    data = request.get_json()
    new_status = data.get("status")
    credit_amount = data.get("credit_amount")
    if not new_status:
        return jsonify({"success": False, "message": "Missing status"}), 400

    for o in orders:
        if str(o.get('id')) == str(order_id):
            # منع المعالجة المزدوجة
            if o['status'] != "قيد الانتظار":
                return jsonify({"success": False, "message": f"الطلب تمت معالجته مسبقاً ({o['status']})"}), 400

            o['status'] = new_status

            # إضافة الرصيد للزبون عند الموافقة إذا كان مبلغ محدد
            credited = 0
            new_balance = None
            if new_status == "مكتمل" and credit_amount is not None:
                try:
                    credited = float(credit_amount)
                    if credited > 0:
                        uid = str(o.get('user_id', ''))
                        if uid:
                            balance[uid] = balance.get(uid, 0) + credited
                            save_json(BALANCE_FILE, balance)
                            new_balance = balance[uid]
                            o['price'] = credited
                except (ValueError, TypeError):
                    pass

            save_json(ORDERS_FILE, orders)

            tg_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            try:
                # إشعار الأدمن في تيليغرام
                source_label = "✅ تمت الموافقة" if new_status == "مكتمل" else "❌ تم الرفض"
                credit_line = f"💸 الرصيد المضاف: {int(credited)} ليرة\n" if credited > 0 else ""
                admin_notif = (
                    f"🖥️ **إجراء من لوحة الإدارة**\n\n"
                    f"{source_label} على الطلب التالي:\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📦 السلعة: {o.get('item_name', 'N/A')}\n"
                    f"👤 الزبون: @{o.get('username', 'N/A')}\n"
                    f"💰 المبلغ: {o.get('price', 0)} ليرة\n"
                    f"{credit_line}"
                    f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                    f"━━━━━━━━━━━━━━━━\n"
                    f"📍 المصدر: لوحة الإدارة (الويب)"
                )
                requests.post(tg_url, json={"chat_id": ADMIN_ID, "text": admin_notif, "parse_mode": "Markdown"}, timeout=10)
            except: pass

            try:
                uid = str(o.get('user_id', ''))
                if uid:
                    if new_status == "مكتمل" and credited > 0:
                        balance_line = f"🏦 رصيدك الحالي: {int(new_balance)} ليرة\n" if new_balance is not None else ""
                        customer_msg = (
                            f"🧾 **إيصال شحن رصيد**\n\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"💰 المبلغ المشحون: {int(credited)} ليرة\n"
                            f"{balance_line}"
                            f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                            f"🕐 التاريخ: {o.get('timestamp_formatted', '')}\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"✅ **الحالة: تم الشحن بنجاح**\n\n"
                            f"🎉 تم إضافة رصيدك، بالتوفيق في مشترياتك!"
                        )
                    elif new_status == "مكتمل":
                        customer_msg = (
                            f"🧾 **فاتورة - محدّثة**\n\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"📦 السلعة: {o.get('item_name', 'N/A')}\n"
                            f"🎮 ID اللعبة: `{o.get('game_id', 'N/A')}`\n"
                            f"💰 السعر المدفوع: {o.get('price', 0)} ليرة\n"
                            f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                            f"🕐 التاريخ: {o.get('timestamp_formatted', '')}\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"✅ **الحالة: تمت الموافقة**\n\n"
                            f"🎉 تهانينا! طلبك تم قبوله وسيتم تنفيذه في أقرب وقت."
                        )
                    else:
                        customer_msg = (
                            f"🧾 **فاتورة - محدّثة**\n\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"📦 السلعة: {o.get('item_name', 'N/A')}\n"
                            f"🎮 ID اللعبة: `{o.get('game_id', 'N/A')}`\n"
                            f"💰 السعر: {o.get('price', 0)} ليرة\n"
                            f"🆔 رقم الطلب: `{o['id'][:8]}`\n"
                            f"🕐 التاريخ: {o.get('timestamp_formatted', '')}\n"
                            f"━━━━━━━━━━━━━━━━\n"
                            f"❌ **الحالة: مرفوض**\n\n"
                            f"⚠️ للأسف تم رفض طلبك. للاستفسار تواصل مع الدعم: @mhama1kjokbi"
                        )
                    requests.post(tg_url, json={"chat_id": int(uid), "text": customer_msg, "parse_mode": "Markdown"}, timeout=10)
            except: pass

            return jsonify({"success": True, "credited": credited})
    return jsonify({"success": False, "message": "Order not found"}), 404

@app.route('/api/settings/deposit-numbers', methods=['GET', 'POST', 'DELETE'])
@require_admin
def api_deposit_numbers():
    if request.method == 'GET': return jsonify({"success": True, "data": settings.get("deposit_numbers", [])})
    data = request.get_json()
    nums = settings.get("deposit_numbers", [])
    if request.method == 'POST':
        num = data.get("number")
        if num and num not in nums: nums.append(num)
    elif request.method == 'DELETE':
        num = data.get("number")
        if len(nums) > 1:
            if num in nums: nums.remove(num)
        else:
            return jsonify({"success": False, "message": "يجب وجود رقم إيداع واحد على الأقل"}), 400
    settings["deposit_numbers"] = nums
    save_json(SETTINGS_FILE, settings)
    return jsonify({"success": True, "data": nums})

@app.route('/api/orders', methods=['GET'])
@require_admin
def api_orders(): return jsonify({"success": True, "data": orders})

@app.route('/api/users', methods=['GET'])
@require_admin
def api_users():
    return jsonify({"success": True, "data": [{"id": k, "username": v.get("username"), "balance": balance.get(k, 0), "last_seen": v.get("last_seen")} for k, v in users.items()]})

@app.route('/api/users/<uid>/balance', methods=['PUT'])
@require_admin
def api_user_balance(uid):
    data = request.get_json()
    try:
        new_bal = float(data.get("balance", 0))
        balance[uid] = new_bal
        save_json(BALANCE_FILE, balance)
        return jsonify({"success": True})
    except: return jsonify({"success": False}), 400

@app.route('/api/backup/send-to-bot', methods=['POST'])
@require_admin
def api_send_backup_to_bot():
    zip_path = "bot_files_backup.zip"
    try:
        files_to_include = [
            'main.py', 'replit.md', 'README.md', 'requirements.txt',
            'runtime.txt', 'goods.json', 'users.json', 'orders.json',
            'balance.json', 'settings.json', 'violations.json',
            'offers.json', 'pending.json'
        ]
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files_list in os.walk('static'):
                for file in files_list:
                    zipf.write(os.path.join(root, file))
            for f in files_to_include:
                if os.path.exists(f):
                    zipf.write(f)

        if not os.path.exists(zip_path):
            return jsonify({"success": False, "message": "فشل إنشاء الملف"}), 500

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
        with open(zip_path, 'rb') as f:
            resp = requests.post(
                url,
                data={'chat_id': str(ADMIN_ID), 'caption': '✅ نسخة احتياطية كاملة حسب طلبك.'},
                files={'document': ('backup.zip', f, 'application/zip')},
                timeout=60
            )
        
        result = resp.json()
        if os.path.exists(zip_path):
            os.remove(zip_path)

        if result.get('ok'):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": result.get('description', 'خطأ من تيليغرام')}), 500

    except Exception as e:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        return jsonify({"success": False, "message": str(e)}), 500

def _keep_alive():
    url = (WEBHOOK_URL or "").rstrip("/")
    if not url:
        return
    while True:
        time.sleep(840)
        try:
            requests.get(url + "/ping", timeout=10)
        except Exception:
            pass

Thread(target=_keep_alive, daemon=True).start()

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# متغير عالمي للـ application
bot_application = None

def build_application():
    global bot_application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    async def error_handler(update, context):
        from telegram.error import Conflict, NetworkError, TimedOut
        if isinstance(context.error, Conflict):
            import asyncio
            await asyncio.sleep(5)
        elif isinstance(context.error, (NetworkError, TimedOut)):
            pass
        else:
            print(f"Bot error: {context.error}")

    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))

    async def menu_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text == "🛍️ السلع": await goods_handler(update, context)
        elif text == "💰 رصيدي": await balance_handler(update, context)
        elif text == "📦 طلباتي": await orders_handler(update, context)
        elif text == "➕ شحن رصيد": await add_balance_handler(update, context)
        elif text == "⚙️ الإعدادات": await settings_handler(update, context)
        elif text == "👨‍💻 الدعم": await support_handler(update, context)
        elif text == "🏁 Start": await start(update, context)

    application.add_handler(MessageHandler(filters.Text(["🛍️ السلع", "💰 رصيدي", "📦 طلباتي", "➕ شحن رصيد", "⚙️ الإعدادات", "👨‍💻 الدعم", "🏁 Start"]), menu_root))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    bot_application = application
    return application

# --- Webhook endpoint لـ Render ---
@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    import asyncio
    if bot_application is None:
        return "Bot not ready", 503
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, bot_application.bot)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot_application.process_update(update))
        loop.close()
    except Exception as e:
        print(f"Webhook error: {e}")
    return "OK", 200

def run_bot_polling(application):
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=True")
    application.run_polling(drop_pending_updates=True)

def run_bot_webhook(application):
    import asyncio
    webhook_path = f"/webhook/{BOT_TOKEN}"
    full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
    print(f"Setting webhook: {full_webhook_url}")
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        json={"url": full_webhook_url, "drop_pending_updates": True},
        timeout=15
    )
    print(f"Webhook set: {resp.json()}")

    async def init_app():
        await application.initialize()
        await application.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_app())
    print(f"Bot running in Webhook mode on port {PORT}")
    # Flask يستقبل الـ updates — لا نحتاج loop هنا
    run_flask()

if __name__ == "__main__":
    application = build_application()
    if USE_WEBHOOK:
        print("▶ Webhook mode (Render)")
        run_bot_webhook(application)
    else:
        print("▶ Polling mode (Replit/local)")
        Thread(target=run_flask, daemon=True).start()
        run_bot_polling(application)
