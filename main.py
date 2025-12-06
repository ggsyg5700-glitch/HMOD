import os
import sys
import json
import uuid
import datetime
import zipfile
import shutil
import signal
import time
from typing import Dict
from collections import defaultdict
from flask import Flask, request, jsonify, send_from_directory
import hashlib
import hmac
from urllib.parse import parse_qs, unquote
import asyncio
from threading import Thread

BOT_START_TIME = datetime.datetime.now()
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
        filters,
    )
except ImportError:
    print("ERROR: python-telegram-bot غير مثبت بشكل صحيح.")
    print("يرجى تشغيل: pip install python-telegram-bot")
    sys.exit(1)

app = Flask(__name__)

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_ID = int((os.getenv("ADMIN_ID") or "0").strip())
DEPOSIT_NUMBER = (os.getenv("DEPOSIT_NUMBER") or "97675410").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()
PORT = int((os.getenv("PORT") or "8080").strip())
REPLIT_DOMAIN = os.getenv("REPLIT_DEV_DOMAIN") or os.getenv("REPLIT_DOMAINS", "").split(",")[0]
WEBAPP_URL = f"https://{REPLIT_DOMAIN}/dashboard" if REPLIT_DOMAIN else ""

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN غير معرّف في متغيرات البيئة.")
    sys.exit(1)

GOODS_FILE = "goods.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
BALANCE_FILE = "balance.json"
PENDING_FILE = "pending.json"
WELCOME_IMAGE = "attached_assets/IMG_20251020_170014_439_1761349945506.jpg"
BACKUPS_DIR = "backups"
ALL_LOGS_FILE = "all_logs.txt"

if not os.path.exists(BACKUPS_DIR):
    os.makedirs(BACKUPS_DIR)

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

users: Dict[str, Dict] = load_json(USERS_FILE, {})
orders = load_json(ORDERS_FILE, [])
balance = load_json(BALANCE_FILE, {})
pending = load_json(PENDING_FILE, {})

import random

def clear_user_state(context):
    """حذف جميع البيانات المؤقتة للمستخدم لتجنب تداخل العمليات"""
    keys_to_clear = [
        "expecting_account_id_for_purchase",
        "pending_purchase",
        "expecting_deposit",
        "awaiting_deposit",
        "editing_price",
        "expecting_price_item",
        "awaiting_broadcast",
        "confirming_clear_logs"
    ]
    for key in keys_to_clear:
        context.user_data.pop(key, None)

def check_spam(user_id):
    """التحقق من الإغراق - تنبيه الأدمن إذا أرسل المستخدم أكثر من 50 رسالة في الدقيقة"""
    now = datetime.datetime.now()
    one_minute_ago = now - datetime.timedelta(minutes=1)
    
    user_message_counts[user_id] = [
        t for t in user_message_counts[user_id] 
        if t > one_minute_ago
    ]
    
    user_message_counts[user_id].append(now)
    
    message_count = len(user_message_counts[user_id])
    
    if message_count > 50 and user_id not in spam_warned_users:
        spam_warned_users.add(user_id)
        return True, message_count
    
    if message_count <= 10:
        spam_warned_users.discard(user_id)
    
    return False, message_count

def get_bot_status():
    """الحصول على معلومات حالة البوت"""
    now = datetime.datetime.now()
    uptime = now - BOT_START_TIME
    
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        uptime_str = f"{days} يوم، {hours} ساعة، {minutes} دقيقة"
    elif hours > 0:
        uptime_str = f"{hours} ساعة، {minutes} دقيقة، {seconds} ثانية"
    else:
        uptime_str = f"{minutes} دقيقة، {seconds} ثانية"
    
    source = "Replit" if os.getenv("REPL_ID") else ("Render" if os.getenv("RENDER") else "سيرفر خاص")
    
    return {
        "uptime": uptime_str,
        "start_time": BOT_START_TIME.strftime("%Y-%m-%d | %I:%M:%S %p"),
        "users_count": len(users),
        "total_balance": sum(balance.values()),
        "orders_count": len(orders),
        "source": source
    }

def create_customers_zip():
    """إنشاء ملف مضغوط يحتوي على ملفات الزبائن والأرصدة"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    zip_filename = os.path.join(BACKUPS_DIR, f"customers_data_{timestamp}.zip")
    
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.exists(USERS_FILE):
            zipf.write(USERS_FILE, os.path.basename(USERS_FILE))
        if os.path.exists(BALANCE_FILE):
            zipf.write(BALANCE_FILE, os.path.basename(BALANCE_FILE))
        if os.path.exists(ORDERS_FILE):
            zipf.write(ORDERS_FILE, os.path.basename(ORDERS_FILE))
        if os.path.exists(PENDING_FILE):
            zipf.write(PENDING_FILE, os.path.basename(PENDING_FILE))
    
    return zip_filename

def log_operation(operation_type, user_id, username, item_name=None, price=None, status=None, operation_number=None):
    """حفظ العملية في ملف all_logs.txt بتنسيق موحد مع نظام 12 ساعة"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%I:%M:%S %p")
    
    log_entry = "=" * 60 + "\n"
    
    if operation_type == "purchase":
        log_entry += f"🛒 نوع العملية: شراء\n"
        log_entry += f"👤 المستخدم: @{username} (ID: {user_id})\n"
        log_entry += f"💎 السلعة: {item_name}\n"
        log_entry += f"💰 السعر: {price} ل.س\n"
        log_entry += f"📄 الحالة: {status}\n"
        log_entry += f"⏰ الوقت: {date_str} | {time_str}\n"
    elif operation_type == "deposit":
        log_entry += f"🏦 نوع العملية: إيداع\n"
        log_entry += f"👤 المستخدم: @{username} (ID: {user_id})\n"
        log_entry += f"🔢 رقم العملية: {operation_number}\n"
        log_entry += f"📄 الحالة: {status}\n"
        log_entry += f"⏰ الوقت: {date_str} | {time_str}\n"
    
    log_entry += "-" * 60 + "\n\n"
    
    with open(ALL_LOGS_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)

def generate_all_logs_file():
    """إرجاع مسار ملف السجلات (إنشاء ملف فارغ إذا لم يكن موجوداً)"""
    if not os.path.exists(ALL_LOGS_FILE):
        with open(ALL_LOGS_FILE, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("📋 سجل جميع الطلبات والإيداعات\n")
            f.write("=" * 60 + "\n\n")
            f.write("ℹ️ لا توجد عمليات مسجلة بعد.\n")
            f.write("\n")
    return ALL_LOGS_FILE

def create_backup_zip():
    """إنشاء نسخة احتياطية من جميع الملفات"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_filename = os.path.join(BACKUPS_DIR, f"backup_{timestamp}.zip")
    
    files_to_backup = [
        "main.py",
        GOODS_FILE, USERS_FILE, ORDERS_FILE, BALANCE_FILE, PENDING_FILE,
        "requirements.txt", "runtime.txt", "render.yaml",
        "replit.md", "README.md", "DEPLOY_GUIDE.md"
    ]
    
    if os.path.exists(ALL_LOGS_FILE):
        files_to_backup.append(ALL_LOGS_FILE)
    
    with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files_to_backup:
            if os.path.exists(file):
                zipf.write(file, os.path.basename(file))
        
        if os.path.exists("attached_assets"):
            for root, dirs, files in os.walk("attached_assets"):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, ".")
                    zipf.write(file_path, arcname)
    
    return backup_filename

def auto_backup_thread():
    """مهمة خلفية للنسخ الاحتياطي التلقائي كل 24 ساعة"""
    import time
    while True:
        time.sleep(24 * 60 * 60)
        try:
            create_backup_zip()
            print(f"✅ تم إنشاء نسخة احتياطية تلقائية في {datetime.datetime.now()}")
        except Exception as e:
            print(f"❌ خطأ في النسخ الاحتياطي التلقائي: {e}")

def build_reply_keyboard():
    keyboard = [[KeyboardButton("🏠 Start")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def build_main_keyboard(for_uid=None):
    kb = []
    kb.append([InlineKeyboardButton("🛍️ عرض السلع", callback_data="show_goods")])
    kb.append([InlineKeyboardButton("📥 إيداع", callback_data="deposit")])
    kb.append([InlineKeyboardButton("💳 رصيدك", callback_data="check_balance")])
    kb.append([InlineKeyboardButton("🎮 لعبة (حجر/ورق/مقص)", callback_data="game_rps")])
    kb.append([InlineKeyboardButton("💬 تواصل مع المسؤول", url="https://t.me/mhama1kjokbi")])
    if str(for_uid) == str(ADMIN_ID):
        if WEBAPP_URL:
            kb.append([InlineKeyboardButton("⚙️ لوحة الأدمن", web_app=WebAppInfo(url=WEBAPP_URL))])
        else:
            kb.append([InlineKeyboardButton("⚙️ لوحة الأدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

def build_goods_keyboard():
    kb = []
    for item in goods:
        kb.append([InlineKeyboardButton(f"{item['name']} - {item['price']} ل.س", callback_data=f"buy_{item['id']}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="start_cmd")])
    return InlineKeyboardMarkup(kb)

def build_admin_keyboard():
    kb = []
    kb.append([InlineKeyboardButton("💳 شحن (عرض السلع كما للمستخدم)", callback_data="admin_show_goods")])
    kb.append([InlineKeyboardButton("📋 عرض المستخدمين", callback_data="admin_show_users")])
    kb.append([InlineKeyboardButton("💰 تعديل أسعار", callback_data="admin_edit_price")])
    kb.append([InlineKeyboardButton("📢 إرسال رسالة جماعية", callback_data="admin_broadcast")])
    kb.append([InlineKeyboardButton("📁 تنزيل السجل", callback_data="admin_download_logs")])
    kb.append([InlineKeyboardButton("📦 تحميل ملفات البوت", callback_data="admin_download_backup")])
    kb.append([InlineKeyboardButton("👥 تحميل ملفات الزبائن", callback_data="admin_download_customers")])
    kb.append([InlineKeyboardButton("🗑️ تصفير السجل", callback_data="admin_clear_logs")])
    kb.append([InlineKeyboardButton("📊 حالة البوت", callback_data="admin_bot_status")])
    kb.append([InlineKeyboardButton("🔄 إعادة تشغيل البوت", callback_data="admin_restart_bot")])
    kb.append([InlineKeyboardButton("🕒 التاريخ والوقت", callback_data="admin_time")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="start_cmd")])
    return InlineKeyboardMarkup(kb)

async def send_welcome_image(context, chat_id, caption, inline_markup):
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text="استخدم زر 🏠 Start للرجوع للقائمة الرئيسية في أي وقت",
            reply_markup=build_reply_keyboard(),
            parse_mode="Markdown"
        )
        if os.path.exists(WELCOME_IMAGE):
            with open(WELCOME_IMAGE, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=inline_markup,
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=inline_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"Error sending welcome image: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=inline_markup,
            parse_mode="Markdown"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    
    clear_user_state(context)
    
    if uid not in users:
        users[uid] = {}
    users[uid]["username"] = update.effective_user.username or update.effective_user.full_name or users[uid].get("username","")
    users[uid]["registered_at"] = datetime.datetime.utcnow().isoformat()
    save_json(USERS_FILE, users)
    
    if uid not in balance:
        balance[uid] = 0
        save_json(BALANCE_FILE, balance)
    
    caption_text = "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥"
    
    await send_welcome_image(context, update.effective_chat.id, caption_text, build_main_keyboard(for_uid=uid))

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.full_name or "غير معروف"
    is_admin = str(uid) == str(ADMIN_ID)
    admin_status = "✅ نعم" if is_admin else "❌ لا"
    
    await update.message.reply_text(
        f"📋 معلومات حسابك:\n\n"
        f"🆔 معرفك (User ID): `{uid}`\n"
        f"👤 اسم المستخدم: @{username}\n"
        f"👑 هل أنت أدمن: {admin_status}\n\n"
        f"ℹ️ ADMIN_ID الحالي: `{ADMIN_ID}`",
        parse_mode="Markdown"
    )

def get_user_record(uid_str):
    return users.get(uid_str, {})

async def disable_message_buttons(context, chat_id, message_id, text=None):
    try:
        if text:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
        else:
            await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except Exception as e:
        print("disable_message_buttons error:", e)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()
    
    is_spam, msg_count = check_spam(uid)
    if is_spam:
        try:
            username = users.get(uid, {}).get("username", "غير معروف")
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ **تنبيه إغراق!**\n\n"
                     f"👤 المستخدم: @{username}\n"
                     f"🆔 ID: {uid}\n"
                     f"📨 عدد الرسائل في الدقيقة: {msg_count}\n\n"
                     f"⏰ الوقت: {datetime.datetime.now().strftime('%Y-%m-%d | %I:%M:%S %p')}",
                parse_mode="Markdown"
            )
        except:
            pass

    if text in ["🏠 Start", "Start", "start", "/start"]:
        clear_user_state(context)
        caption_text = "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥"
        await send_welcome_image(context, update.effective_chat.id, caption_text, build_main_keyboard(for_uid=uid))
        return

    if str(uid) == str(ADMIN_ID) and context.user_data.get("confirming_clear_logs"):
        context.user_data.pop("confirming_clear_logs")
        if text.lower() == "yes":
            try:
                if os.path.exists(ALL_LOGS_FILE):
                    os.remove(ALL_LOGS_FILE)
                
                global orders
                orders = []
                save_json(ORDERS_FILE, [])
                
                await update.message.reply_text("✅ تم حذف جميع ملفات السجل بنجاح!\n\n⚠️ ملاحظة: تم الحفاظ على أرصدة المستخدمين وبيانات البوت الأساسية.")
            except Exception as e:
                await update.message.reply_text(f"❌ حدث خطأ أثناء الحذف: {str(e)}")
        elif text.lower() == "no":
            await update.message.reply_text("❌ تم إلغاء عملية الحذف.")
        else:
            context.user_data["confirming_clear_logs"] = True
            await update.message.reply_text("⚠️ يرجى الرد بـ **yes** أو **no** فقط.", parse_mode="Markdown")
        return
    
    if str(uid) == str(ADMIN_ID) and context.user_data.get("awaiting_broadcast"):
        context.user_data.pop("awaiting_broadcast")
        sent_count = 0
        failed_count = 0
        for user_id in users.keys():
            try:
                await context.bot.send_message(chat_id=int(user_id), text=text)
                sent_count += 1
            except:
                failed_count += 1
        await update.message.reply_text(f"✅ تم إرسال الرسالة إلى {sent_count} مستخدم.\n❌ فشل الإرسال لـ {failed_count} مستخدم.")
        return

    if str(uid) == str(ADMIN_ID) and context.user_data.get("awaiting_deposit"):
        deposit_id = context.user_data.pop("awaiting_deposit")
        try:
            amount = int(text.replace(",", "").strip())
        except:
            context.user_data["awaiting_deposit"] = deposit_id
            await update.message.reply_text("❌ ادخل مبلغ صحيح بالأرقام فقط (مثال: 10000).")
            return
        dep = pending.get(deposit_id)
        if not dep:
            await update.message.reply_text("❌ لم أجد عملية الإيداع أو انتهت صلاحيتها.")
            return
        user_id = dep["user_id"]
        balance[user_id] = balance.get(user_id, 0) + amount
        save_json(BALANCE_FILE, balance)
        for ord_ in orders:
            if ord_.get("type") == "deposit" and ord_.get("deposit_id") == deposit_id:
                ord_["status"] = "مقبول"
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

    if str(uid) == str(ADMIN_ID) and context.user_data.get("editing_price"):
        edit_info = context.user_data.pop("editing_price")
        item_id = edit_info.get("item_id")
        try:
            new_price = int(text.replace(",", "").strip())
        except:
            context.user_data["editing_price"] = edit_info
            await update.message.reply_text("❌ ادخل سعر صحيح بالأرقام. مثال: 25000")
            return
        found = False
        for it in goods:
            if it["id"] == item_id:
                it["price"] = new_price
                found = True
                break
        if found:
            save_json(GOODS_FILE, goods)
            await update.message.reply_text(f"✅ تم تعديل سعر السلعة رقم {item_id} إلى {new_price} ل.س.")
        else:
            await update.message.reply_text("❌ لم أجد السلعة المطلوبة.")
        return

    if str(uid) == str(ADMIN_ID) and context.user_data.get("expecting_price_item"):
        context.user_data.pop("expecting_price_item")
        try:
            item_id = int(text.strip())
        except:
            context.user_data["expecting_price_item"] = True
            await update.message.reply_text("❌ ادخل رقم السلعة صحيح (مثال: 3).")
            return
        if not any(it["id"] == item_id for it in goods):
            await update.message.reply_text("❌ ليست هناك سلعة بهذا الرقم. أعد المحاولة.")
            return
        context.user_data["editing_price"] = {"item_id": item_id}
        await update.message.reply_text("📥 الآن أرسل السعر الجديد للسلعة (بالأرقام فقط).")
        return

    if context.user_data.get("expecting_account_id_for_purchase"):
        if not text.isdigit() or len(text) != 10:
            await update.message.reply_text("❌ يجب أن يكون ID الحساب **10 أرقام**. حاول مرة أخرى.", parse_mode="Markdown")
            return
        
        purchase_data = context.user_data.get("pending_purchase")
        if not purchase_data:
            await update.message.reply_text("❌ خطأ: لم أجد بيانات الطلب. يرجى اختيار السلعة مرة أخرى.")
            context.user_data["expecting_account_id_for_purchase"] = False
            return
        
        item = purchase_data["item"]
        item_price = item["price"]
        user_balance = balance.get(uid, 0)
        
        if user_balance < item_price:
            await update.message.reply_text(f"❌ ما معك سعر السلعة.\n\nرصيدك الحالي: {user_balance} ل.س\nسعر السلعة: {item_price} ل.س\n\nقم بإيداع المبلغ أولاً ثم أعد المحاولة.")
            context.user_data["expecting_account_id_for_purchase"] = False
            context.user_data["pending_purchase"] = None
            return
        
        users[uid] = users.get(uid, {})
        users[uid]["username"] = update.effective_user.username or update.effective_user.full_name or users[uid].get("username","")
        users[uid]["account_id"] = text
        save_json(USERS_FILE, users)
        
        order_id = str(uuid.uuid4())
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        orders.append({
            "id": order_id,
            "type": "purchase",
            "user_id": uid,
            "username": users.get(uid,{}).get("username",""),
            "account_id": text,
            "item": item["name"],
            "price": item_price,
            "status": "معلق",
            "timestamp": timestamp
        })
        save_json(ORDERS_FILE, orders)
        
        log_operation("purchase", uid, users.get(uid,{}).get("username",""), 
                     item_name=item['name'], price=item_price, status="معلق")
        
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
                      f"السعر: {item_price} ل.س\n"
                      f"رصيد الزبون الحالي: {user_balance} ل.س\n"
                      f"ID الحساب: {text}"),
                reply_markup=kb_admin)
        except:
            pass
        
        await update.message.reply_text("✅ تم إرسال طلبك للأدمن للمراجعة. سيتم إشعارك بالنتيجة قريباً.")
        context.user_data["expecting_account_id_for_purchase"] = False
        context.user_data["pending_purchase"] = None
        return
    

    if context.user_data.get("expecting_deposit"):
        operation = text
        deposit_id = str(uuid.uuid4())
        pending[deposit_id] = {"user_id": uid, "operation": operation}
        save_json(PENDING_FILE, pending)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        orders.append({
            "id": str(uuid.uuid4()),
            "type": "deposit",
            "deposit_id": deposit_id,
            "user_id": uid,
            "username": users.get(uid,{}).get("username",""),
            "account_id": users.get(uid,{}).get("account_id",""),
            "operation": operation,
            "status": "معلق",
            "timestamp": timestamp
        })
        save_json(ORDERS_FILE, orders)
        
        log_operation("deposit", uid, users.get(uid,{}).get("username",""),
                     operation_number=operation, status="معلق")
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

    await update.message.reply_text(text)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = str(query.from_user.id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if data == "start_cmd":
        clear_user_state(context)
        try:
            await query.message.delete()
        except:
            pass
        caption_text = "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥"
        await send_welcome_image(context, chat_id, caption_text, build_main_keyboard(for_uid=uid))
        return
    
    if data == "back_main":
        clear_user_state(context)
        try:
            await query.message.delete()
        except:
            pass
        await send_welcome_image(context, chat_id, "🔙 رجعنا للقائمة الرئيسية", build_main_keyboard(for_uid=uid))
        return

    if data == "show_goods":
        clear_user_state(context)
        caption_text = "🛍️ اختر السلعة التي تريدها:"
        try:
            await query.message.delete()
        except:
            pass
        await send_welcome_image(context, chat_id, caption_text, build_goods_keyboard())
        return

    if data == "check_balance":
        clear_user_state(context)
        bal = balance.get(uid, 0)
        await query.message.reply_text(f"💳 رصيدك الحالي: {bal} ل.س")
        return

    if data == "deposit":
        clear_user_state(context)
        context.user_data["expecting_deposit"] = True
        await query.message.reply_text(f"📥 للإيداع: حول المبلغ إلى {DEPOSIT_NUMBER} ثم أرسل رقم العملية هنا.")
        return

    if data == "game_rps":
        clear_user_state(context)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✊ حجر", callback_data="rps_rock")],
            [InlineKeyboardButton("🖐️ ورق", callback_data="rps_paper")],
            [InlineKeyboardButton("✌️ مقص", callback_data="rps_scissors")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="start_cmd")]
        ])
        await query.message.reply_text("اختر: حجر، ورق أو مقص", reply_markup=kb)
        return

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

    if data.startswith("buy_"):
        clear_user_state(context)
        item_id = int(data.split("_",1)[1])
        item = next((i for i in goods if i["id"] == item_id), None)
        if not item:
            await query.message.reply_text("❌ خطأ: السلعة غير موجودة.")
            return
        
        text_caption = f"📦 تم اختيار: {item['name']}\nالسعر: {item['price']} ل.س\n\n📝 الآن أرسل ID حساب اللعبة (يجب أن يكون **10 أرقام**)."
        try:
            if item.get("image"):
                await context.bot.send_photo(chat_id=int(uid), photo=item.get("image"), caption=text_caption, parse_mode="Markdown")
            else:
                await query.message.reply_text(text_caption, parse_mode="Markdown")
        except:
            await query.message.reply_text(text_caption, parse_mode="Markdown")
        
        context.user_data["expecting_account_id_for_purchase"] = True
        context.user_data["pending_purchase"] = {"item": item}
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
                await disable_message_buttons(context, ADMIN_ID, message_id)
                await query.message.reply_text(f"✅ تم قبول الطلب: {order['item']}")
            else:
                order["status"] = "مقبول"
                save_json(ORDERS_FILE, orders)
                await disable_message_buttons(context, ADMIN_ID, message_id)
                await query.message.reply_text("✅ تم قبول الطلب.")
            return

        elif action == "reject":
            order["status"] = "مرفوض"
            save_json(ORDERS_FILE, orders)
            try:
                await context.bot.send_message(chat_id=int(order["user_id"]), text=f"❌ تم رفض طلبك ({order.get('item','')}).")
            except:
                pass
            await disable_message_buttons(context, ADMIN_ID, message_id)
            await query.message.reply_text(f"❌ تم رفض الطلب: {order.get('item','')}")
            return

    if data.startswith("deposit_accept_") or data.startswith("deposit_reject_"):
        parts = data.split("_",2)
        if len(parts) < 3:
            await query.message.reply_text("❌ بيانات غير صحيحة.")
            return
        kind = parts[0] + "_" + parts[1]
        deposit_id = parts[2]
        dep = pending.get(deposit_id)
        if not dep:
            await query.message.reply_text("❌ لم يتم العثور على عملية الإيداع.")
            return
        if kind == "deposit_accept":
            clear_user_state(context)
            context.user_data["awaiting_deposit"] = deposit_id
            await query.message.reply_text(f"💰 ادخل المبلغ الذي تريد إضافته لرقم العملية {dep['operation']} (لمستخدم {dep['user_id']})")
            await disable_message_buttons(context, ADMIN_ID, message_id)
            return
        elif kind == "deposit_reject":
            for ord_ in orders:
                if ord_.get("type") == "deposit" and ord_.get("deposit_id") == deposit_id:
                    ord_["status"] = "مرفوض"
            save_json(ORDERS_FILE, orders)
            try:
                await context.bot.send_message(chat_id=int(dep['user_id']), text="❌ تم رفض عملية الإيداع من الأدمن.")
            except:
                pass
            if deposit_id in pending:
                del pending[deposit_id]
                save_json(PENDING_FILE, pending)
            await disable_message_buttons(context, ADMIN_ID, message_id)
            await query.message.reply_text("❌ تم رفض عملية الإيداع.")
            return

    if data == "admin_panel":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        await query.message.reply_text("⚙️ لوحة الأدمن:", reply_markup=build_admin_keyboard())
        return

    if data == "admin_show_goods":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        await query.message.reply_text("قائمة السلع (عرض خاص بالأدمن):", reply_markup=build_goods_keyboard())
        return

    if data == "admin_broadcast":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        context.user_data["awaiting_broadcast"] = True
        await query.message.reply_text("📢 اكتب الرسالة التي تريد إرسالها لجميع المستخدمين:")
        return

    if data == "admin_show_users":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        if not users:
            await query.message.reply_text("لا يوجد مستخدمين مسجلين حالياً.")
            return
        for user_id, info in users.items():
            username = info.get("username", "غير معروف")
            account_id = info.get("account_id", "غير مسجل")
            reg_at = info.get("registered_at", "غير معروف")
            try:
                dt = datetime.datetime.fromisoformat(reg_at)
                reg_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                reg_str = reg_at
            text = (f"👤 المستخدم: @{username}\n"
                    f"🆔 ID الحساب: {account_id}\n"
                    f"💬 رابط التليجرام: https://t.me/{username}\n"
                    f"⏰ تاريخ/وقت التسجيل (UTC): {reg_str}")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ حذف المستخدم", callback_data=f"delete_user_{user_id}")],
            ])
            await query.message.reply_text(text, reply_markup=kb)
        return

    if data.startswith("delete_user_"):
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        del_user_id = data.split("delete_user_")[1]
        if del_user_id in users:
            del users[del_user_id]
            save_json(USERS_FILE, users)
            await query.message.reply_text(f"✅ تم حذف المستخدم {del_user_id}")
        else:
            await query.message.reply_text("❌ المستخدم غير موجود.")
        return

    if data == "admin_edit_price":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        items_text = "\n".join([f"{it['id']}. {it['name']} - {it['price']} ل.س" for it in goods])
        context.user_data["expecting_price_item"] = True
        await query.message.reply_text(f"📋 قائمة السلع:\n{items_text}\n\n📥 أرسل رقم السلعة التي تريد تعديل سعرها:")
        return

    if data == "admin_time":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        now = datetime.datetime.utcnow()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        await query.message.reply_text(f"🕒 التاريخ والوقت الحالي:\n{time_str}")
        return
    
    if data == "admin_download_logs":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        try:
            if not orders:
                await query.message.reply_text("📁 لا توجد سجلات حتى الآن.")
                return
            
            logs_file = generate_all_logs_file()
            with open(logs_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    filename="all_logs.txt",
                    caption="📁 سجل جميع الطلبات والإيداعات"
                )
            
            if os.path.exists(logs_file):
                os.remove(logs_file)
            
            await query.message.reply_text("✅ تم إرسال السجل بنجاح!")
        except Exception as e:
            await query.message.reply_text(f"❌ حدث خطأ أثناء تنزيل السجل: {str(e)}")
        return
    
    if data == "admin_download_backup":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        try:
            await query.message.reply_text("⏳ جاري إنشاء النسخة الاحتياطية...")
            backup_file = create_backup_zip()
            
            with open(backup_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption="📦 نسخة احتياطية من جميع ملفات البوت"
                )
            
            await query.message.reply_text("✅ تم إرسال النسخة الاحتياطية بنجاح!")
        except Exception as e:
            await query.message.reply_text(f"❌ حدث خطأ أثناء إنشاء النسخة الاحتياطية: {str(e)}")
        return
    
    if data == "admin_clear_logs":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        context.user_data["confirming_clear_logs"] = True
        await query.message.reply_text(
            "⚠️ هل أنت متأكد أنك تريد حذف جميع السجلات؟\n\n"
            "أرسل **yes** للحذف أو **no** للإلغاء.",
            parse_mode="Markdown"
        )
        return
    
    if data == "admin_download_customers":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        try:
            await query.message.reply_text("⏳ جاري إنشاء ملف بيانات الزبائن...")
            customers_file = create_customers_zip()
            
            with open(customers_file, 'rb') as f:
                await context.bot.send_document(
                    chat_id=ADMIN_ID,
                    document=f,
                    filename=os.path.basename(customers_file),
                    caption="👥 ملفات الزبائن والأرصدة\n\n"
                            "📁 يحتوي على:\n"
                            "• users.json - بيانات المستخدمين\n"
                            "• balance.json - الأرصدة\n"
                            "• orders.json - الطلبات\n"
                            "• pending.json - العمليات المعلقة"
                )
            
            await query.message.reply_text("✅ تم إرسال ملفات الزبائن بنجاح!")
        except Exception as e:
            await query.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        return
    
    if data == "admin_bot_status":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        
        status = get_bot_status()
        status_text = (
            f"📊 **حالة البوت**\n\n"
            f"🖥️ مصدر التشغيل: {status['source']}\n"
            f"⏱️ وقت التشغيل: {status['uptime']}\n"
            f"🕐 بدء التشغيل: {status['start_time']}\n\n"
            f"👥 عدد المستخدمين: {status['users_count']}\n"
            f"💰 إجمالي الأرصدة: {status['total_balance']} ل.س\n"
            f"📦 عدد الطلبات: {status['orders_count']}\n\n"
            f"✅ البوت يعمل بشكل طبيعي"
        )
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="admin_bot_status")],
            [InlineKeyboardButton("🔙 رجوع للوحة الأدمن", callback_data="admin_panel")]
        ])
        
        await query.message.reply_text(status_text, reply_markup=kb, parse_mode="Markdown")
        return
    
    if data == "admin_restart_bot":
        clear_user_state(context)
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ نعم، أعد التشغيل", callback_data="admin_confirm_restart")],
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")]
        ])
        
        await query.message.reply_text(
            "⚠️ **هل أنت متأكد من إعادة تشغيل البوت؟**\n\n"
            "سيتم إيقاف البوت لبضع ثوانٍ ثم إعادة تشغيله.",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        return
    
    if data == "admin_confirm_restart":
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        
        save_json(USERS_FILE, users)
        save_json(BALANCE_FILE, balance)
        save_json(ORDERS_FILE, orders)
        save_json(PENDING_FILE, pending)
        
        for i in range(5, -1, -1):
            await query.message.reply_text(f"🔄 إعادة التشغيل خلال: {i}")
            await asyncio.sleep(1)
        
        await query.message.reply_text("🔄 جاري إعادة التشغيل...")
        
        os._exit(0)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")

app_bot = None
bot_loop = None

@app.route('/')
def index():
    return "Telegram Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok"}, 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), app_bot.bot)
        asyncio.run_coroutine_threadsafe(app_bot.process_update(update), bot_loop)
    return "ok"

def verify_telegram_webapp(init_data):
    """التحقق من صحة بيانات Telegram WebApp"""
    try:
        parsed_data = dict(parse_qs(init_data))
        data_check_string_parts = []
        hash_value = None
        
        for key in sorted(parsed_data.keys()):
            if key == 'hash':
                hash_value = parsed_data[key][0]
            else:
                data_check_string_parts.append(f"{key}={parsed_data[key][0]}")
        
        if not hash_value:
            return None, "No hash provided"
        
        data_check_string = '\n'.join(data_check_string_parts)
        
        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if calculated_hash != hash_value:
            return None, "Invalid hash"
        
        user_data = parsed_data.get('user', [None])[0]
        if user_data:
            user_info = json.loads(unquote(user_data))
            return user_info, None
        
        return None, "No user data"
    except Exception as e:
        return None, str(e)

def require_admin(f):
    """Decorator للتحقق من صلاحيات الأدمن"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data', '') or request.args.get('initData', '')
        
        if not init_data:
            return jsonify({"error": "Missing init data", "success": False}), 401
        
        user_info, error = verify_telegram_webapp(init_data)
        
        if error:
            return jsonify({"error": f"Auth failed: {error}", "success": False}), 401
        
        if not user_info or str(user_info.get('id')) != str(ADMIN_ID):
            return jsonify({"error": "Access denied - Admin only", "success": False}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def require_admin_for_file(f):
    """Decorator للتحقق من صلاحيات الأدمن للملفات"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.args.get('initData', '') or request.headers.get('X-Telegram-Init-Data', '')
        
        if not init_data:
            return "Unauthorized", 401
        
        user_info, error = verify_telegram_webapp(init_data)
        
        if error or not user_info or str(user_info.get('id')) != str(ADMIN_ID):
            return "Forbidden", 403
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/dashboard')
def dashboard():
    return send_from_directory('static', 'dashboard.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/api/status', methods=['GET'])
@require_admin
def api_status():
    """حالة البوت"""
    try:
        status = get_bot_status()
        return jsonify({
            "success": True,
            "data": status,
            "online": True
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/users', methods=['GET'])
@require_admin
def api_users():
    """عرض المستخدمين"""
    try:
        users_list = []
        for user_id, info in users.items():
            user_balance = balance.get(user_id, 0)
            users_list.append({
                "id": user_id,
                "username": info.get("username", "غير معروف"),
                "account_id": info.get("account_id", "غير مسجل"),
                "registered_at": info.get("registered_at", "غير معروف"),
                "balance": user_balance
            })
        return jsonify({
            "success": True,
            "data": users_list,
            "count": len(users_list)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@require_admin
def api_delete_user(user_id):
    """حذف مستخدم"""
    try:
        if user_id in users:
            del users[user_id]
            save_json(USERS_FILE, users)
            if user_id in balance:
                del balance[user_id]
                save_json(BALANCE_FILE, balance)
            return jsonify({"success": True, "message": f"تم حذف المستخدم {user_id}"})
        else:
            return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/goods', methods=['GET'])
@require_admin
def api_goods():
    """عرض السلع"""
    try:
        return jsonify({
            "success": True,
            "data": goods
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/goods/<int:item_id>/price', methods=['PUT'])
@require_admin
def api_update_price(item_id):
    """تعديل سعر سلعة"""
    try:
        data = request.get_json()
        new_price = data.get('price')
        
        if not new_price:
            return jsonify({"success": False, "error": "السعر مطلوب"}), 400
        
        for item in goods:
            if item['id'] == item_id:
                item['price'] = int(new_price)
                save_json(GOODS_FILE, goods)
                return jsonify({
                    "success": True,
                    "message": f"تم تعديل سعر {item['name']} إلى {new_price} ل.س"
                })
        
        return jsonify({"success": False, "error": "السلعة غير موجودة"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/broadcast', methods=['POST'])
@require_admin
def api_broadcast():
    """إرسال رسالة جماعية"""
    try:
        data = request.get_json()
        message = data.get('message')
        
        if not message:
            return jsonify({"success": False, "error": "الرسالة مطلوبة"}), 400
        
        import requests as req
        sent_count = 0
        failed_count = 0
        
        for user_id in users.keys():
            try:
                req.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={"chat_id": int(user_id), "text": message},
                    timeout=5
                )
                sent_count += 1
            except:
                failed_count += 1
        
        return jsonify({
            "success": True,
            "sent": sent_count,
            "failed": failed_count,
            "message": f"تم إرسال الرسالة إلى {sent_count} مستخدم"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/orders', methods=['GET'])
@require_admin
def api_orders():
    """عرض الطلبات"""
    try:
        return jsonify({
            "success": True,
            "data": orders,
            "count": len(orders)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/pending', methods=['GET'])
@require_admin
def api_pending():
    """عرض العمليات المعلقة"""
    try:
        pending_list = []
        for dep_id, dep_data in pending.items():
            pending_list.append({
                "id": dep_id,
                **dep_data
            })
        return jsonify({
            "success": True,
            "data": pending_list,
            "count": len(pending_list)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/pending/<deposit_id>/approve', methods=['POST'])
@require_admin
def api_approve_deposit(deposit_id):
    """الموافقة على إيداع"""
    try:
        data = request.get_json()
        amount = data.get('amount')
        
        if deposit_id not in pending:
            return jsonify({"success": False, "error": "العملية غير موجودة"}), 404
        
        dep = pending[deposit_id]
        user_id = dep['user_id']
        
        if not amount:
            return jsonify({"success": False, "error": "المبلغ مطلوب"}), 400
        
        amount = int(amount)
        balance[user_id] = balance.get(user_id, 0) + amount
        save_json(BALANCE_FILE, balance)
        
        for ord_ in orders:
            if ord_.get("type") == "deposit" and ord_.get("deposit_id") == deposit_id:
                ord_["status"] = "مقبول"
                ord_["amount"] = amount
        save_json(ORDERS_FILE, orders)
        
        import requests as req
        try:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": int(user_id),
                    "text": f"✅ تمت الموافقة على إيداعك بمبلغ {amount} ل.س\n💰 رصيدك الجديد: {balance[user_id]} ل.س"
                },
                timeout=5
            )
        except:
            pass
        
        del pending[deposit_id]
        save_json(PENDING_FILE, pending)
        
        return jsonify({
            "success": True,
            "message": f"تم الموافقة على الإيداع بمبلغ {amount} ل.س"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/pending/<deposit_id>/reject', methods=['POST'])
@require_admin
def api_reject_deposit(deposit_id):
    """رفض إيداع"""
    try:
        if deposit_id not in pending:
            return jsonify({"success": False, "error": "العملية غير موجودة"}), 404
        
        dep = pending[deposit_id]
        user_id = dep['user_id']
        
        for ord_ in orders:
            if ord_.get("type") == "deposit" and ord_.get("deposit_id") == deposit_id:
                ord_["status"] = "مرفوض"
        save_json(ORDERS_FILE, orders)
        
        import requests as req
        try:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": int(user_id),
                    "text": "❌ تم رفض عملية الإيداع من الأدمن."
                },
                timeout=5
            )
        except:
            pass
        
        del pending[deposit_id]
        save_json(PENDING_FILE, pending)
        
        return jsonify({
            "success": True,
            "message": "تم رفض الإيداع"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logs/clear', methods=['POST'])
@require_admin
def api_clear_logs():
    """تصفير السجل"""
    try:
        global orders
        if os.path.exists(ALL_LOGS_FILE):
            os.remove(ALL_LOGS_FILE)
        orders = []
        save_json(ORDERS_FILE, [])
        return jsonify({
            "success": True,
            "message": "تم حذف جميع السجلات بنجاح"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/time', methods=['GET'])
@require_admin
def api_time():
    """الحصول على الوقت الحالي"""
    try:
        now = datetime.datetime.utcnow()
        return jsonify({
            "success": True,
            "time": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "timestamp": now.timestamp()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/backup/download', methods=['GET'])
@require_admin_for_file
def api_download_backup():
    """تحميل نسخة احتياطية"""
    try:
        backup_file = create_backup_zip()
        return send_from_directory(
            os.path.dirname(backup_file),
            os.path.basename(backup_file),
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/customers/download', methods=['GET'])
@require_admin_for_file
def api_download_customers():
    """تحميل ملفات الزبائن"""
    try:
        customers_file = create_customers_zip()
        return send_from_directory(
            os.path.dirname(customers_file),
            os.path.basename(customers_file),
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logs/download', methods=['GET'])
@require_admin_for_file
def api_download_logs():
    """تحميل السجلات"""
    try:
        if not orders:
            return jsonify({"success": False, "error": "لا توجد سجلات"}), 404
        
        logs_file = generate_all_logs_file()
        return send_from_directory(
            os.path.dirname(logs_file),
            os.path.basename(logs_file),
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logs/send', methods=['POST'])
@require_admin
def api_send_logs():
    """إرسال السجلات عبر تيليجرام"""
    try:
        if not orders:
            return jsonify({"success": False, "error": "لا توجد سجلات"}), 404
        
        logs_file = generate_all_logs_file()
        
        import requests as req
        with open(logs_file, 'rb') as f:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": ADMIN_ID, "caption": "📁 سجل العمليات"},
                files={"document": (os.path.basename(logs_file), f)},
                timeout=30
            )
        
        return jsonify({"success": True, "message": "تم إرسال السجل"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/backup/send', methods=['POST'])
@require_admin
def api_send_backup():
    """إرسال النسخة الاحتياطية عبر تيليجرام"""
    try:
        backup_file = create_backup_zip()
        
        import requests as req
        with open(backup_file, 'rb') as f:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": ADMIN_ID, "caption": "📦 نسخة احتياطية كاملة من ملفات البوت"},
                files={"document": (os.path.basename(backup_file), f)},
                timeout=60
            )
        
        return jsonify({"success": True, "message": "تم إرسال النسخة الاحتياطية"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/customers/send', methods=['POST'])
@require_admin
def api_send_customers():
    """إرسال ملفات الزبائن عبر تيليجرام"""
    try:
        customers_file = create_customers_zip()
        
        import requests as req
        with open(customers_file, 'rb') as f:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={"chat_id": ADMIN_ID, "caption": "👥 ملفات الزبائن (المستخدمين، الأرصدة، الطلبات)"},
                files={"document": (os.path.basename(customers_file), f)},
                timeout=60
            )
        
        return jsonify({"success": True, "message": "تم إرسال ملفات الزبائن"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/restart', methods=['POST'])
@require_admin
def api_restart():
    """إعادة تشغيل البوت"""
    try:
        save_json(USERS_FILE, users)
        save_json(BALANCE_FILE, balance)
        save_json(ORDERS_FILE, orders)
        save_json(PENDING_FILE, pending)
        
        import requests as req
        try:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": "🔄 جاري إعادة التشغيل من لوحة التحكم..."
                },
                timeout=5
            )
        except:
            pass
        
        def delayed_restart():
            time.sleep(2)
            os._exit(0)
        
        Thread(target=delayed_restart, daemon=True).start()
        
        return jsonify({
            "success": True,
            "message": "جاري إعادة التشغيل..."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/balance/<user_id>', methods=['PUT'])
@require_admin
def api_update_balance(user_id):
    """تعديل رصيد مستخدم"""
    try:
        data = request.get_json()
        new_balance = data.get('balance')
        
        if new_balance is None:
            return jsonify({"success": False, "error": "الرصيد مطلوب"}), 400
        
        balance[user_id] = int(new_balance)
        save_json(BALANCE_FILE, balance)
        
        return jsonify({
            "success": True,
            "message": f"تم تعديل رصيد المستخدم {user_id} إلى {new_balance} ل.س"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

async def setup_and_run_bot():
    global app_bot, bot_loop
    bot_loop = asyncio.get_running_loop()
    
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("myid", myid))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_error_handler(error_handler)
    
    await app_bot.initialize()
    await app_bot.start()
    
    print(f"🤖 إعداد webhook على: {WEBHOOK_URL}/{BOT_TOKEN}")
    await app_bot.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print("🤖 البوت يعمل بوضع webhook...")
    
    while True:
        await asyncio.sleep(3600)

def run_bot_in_thread():
    asyncio.run(setup_and_run_bot())

def send_shutdown_notification_sync():
    """إرسال إشعار للأدمن عند إيقاف البوت (نسخة متزامنة)"""
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": "⚠️ **تنبيه: البوت سيتوقف الآن!**\n💾 جاري حفظ البيانات...",
                "parse_mode": "Markdown"
            },
            timeout=5
        )
        
        for i in range(5, -1, -1):
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": f"⏱️ إيقاف البوت خلال: {i}"
                },
                timeout=3
            )
            time.sleep(1)
        
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": ADMIN_ID,
                "text": "🔴 تم إيقاف البوت.\nℹ️ سيتم إعادة التشغيل تلقائياً إذا كنت على Replit/Render.",
                "parse_mode": "Markdown"
            },
            timeout=5
        )
    except Exception as e:
        print(f"Error sending shutdown notification: {e}")

def run_flask():
    """تشغيل Flask server في thread منفصل"""
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def main():
    global app_bot, bot_loop
    
    backup_thread = Thread(target=auto_backup_thread, daemon=True)
    backup_thread.start()
    print("💾 تم تشغيل نظام النسخ الاحتياطي التلقائي (كل 24 ساعة)")
    
    def shutdown_handler(signum, frame):
        """معالج إشارة الإيقاف"""
        print("\n⚠️ تم استلام إشارة إيقاف...")
        
        try:
            save_json(USERS_FILE, users)
            save_json(BALANCE_FILE, balance)
            save_json(ORDERS_FILE, orders)
            save_json(PENDING_FILE, pending)
            print("💾 تم حفظ جميع البيانات بنجاح")
        except Exception as e:
            print(f"❌ خطأ في حفظ البيانات: {e}")
        
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": "⚠️ **تم إيقاف البوت!**\n\n💾 تم حفظ جميع البيانات.\nℹ️ سيتم إعادة التشغيل تلقائياً.",
                    "parse_mode": "Markdown"
                },
                timeout=5
            )
        except:
            pass
        
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    if WEBHOOK_URL:
        print("🌐 Render mode: تشغيل بوضع Webhook")
        print(f"📊 لوحة التحكم: {WEBAPP_URL}")
        
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        
        app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
        app_bot.add_handler(CommandHandler("start", start))
        app_bot.add_handler(CommandHandler("myid", myid))
        app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app_bot.add_handler(CallbackQueryHandler(callback_handler))
        app_bot.add_error_handler(error_handler)
        
        bot_loop.run_until_complete(app_bot.initialize())
        bot_loop.run_until_complete(app_bot.start())
        
        import requests as req
        try:
            req.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": f"{WEBHOOK_URL}/{BOT_TOKEN}"},
                timeout=10
            )
            print(f"🤖 Webhook مُعد على: {WEBHOOK_URL}/{BOT_TOKEN}")
        except Exception as e:
            print(f"❌ خطأ في إعداد webhook: {e}")
        
        def run_loop():
            bot_loop.run_forever()
        
        loop_thread = Thread(target=run_loop, daemon=True)
        loop_thread.start()
        
        PORT = int(os.getenv("PORT", 5000))
        print(f"🌐 Flask server يعمل على المنفذ {PORT}")
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    else:
        print("🏠 Replit mode: تشغيل بوضع Polling")
        
        flask_thread = Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Flask server يعمل على المنفذ 5000")
        print(f"📊 لوحة التحكم: {WEBAPP_URL}")
        
        app_bot_local = ApplicationBuilder().token(BOT_TOKEN).build()
        app_bot_local.add_handler(CommandHandler("start", start))
        app_bot_local.add_handler(CommandHandler("myid", myid))
        app_bot_local.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app_bot_local.add_handler(CallbackQueryHandler(callback_handler))
        app_bot_local.add_error_handler(error_handler)
        
        print("🤖 البوت يعمل محلياً بوضع polling...")
        app_bot_local.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
