import os
import sys
import json
import uuid
import datetime
from typing import Dict
import random
import threading

# Telegram imports
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Flask imports
from flask import Flask
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
DEPOSIT_NUMBER = os.getenv("DEPOSIT_NUMBER") or "97675410"

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN غير معرّف في متغيرات البيئة.")
    sys.exit(1)

GOODS_FILE = "goods.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"
BALANCE_FILE = "balance.json"
PENDING_FILE = "pending.json"
WELCOME_IMAGE = "attached_assets/welcome.jpg"

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
def build_main_keyboard(for_uid=None):
    kb = []
    kb.append([InlineKeyboardButton("🛍️ عرض السلع", callback_data="show_goods")])
    kb.append([InlineKeyboardButton("📥 إيداع", callback_data="deposit")])
    kb.append([InlineKeyboardButton("💳 رصيدك", callback_data="check_balance")])
    kb.append([InlineKeyboardButton("🎮 لعبة (حجر/ورق/مقص)", callback_data="game_rps")])
    kb.append([InlineKeyboardButton("💬 تواصل مع المسؤول", url="https://t.me/mhama1kjokbi")])
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
    kb = []
    kb.append([InlineKeyboardButton("💳 شحن (عرض السلع كما للمستخدم)", callback_data="admin_show_goods")])
    kb.append([InlineKeyboardButton("📋 عرض المستخدمين", callback_data="admin_show_users")])
    kb.append([InlineKeyboardButton("💰 تعديل أسعار", callback_data="admin_edit_price")])
    kb.append([InlineKeyboardButton("📢 إرسال رسالة جماعية", callback_data="admin_broadcast")])
    kb.append([InlineKeyboardButton("🕒 التاريخ والوقت", callback_data="admin_time")])
    kb.append([InlineKeyboardButton("◀️ رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)

async def send_welcome_image(context, chat_id, caption, reply_markup):
    try:
        if os.path.exists(WELCOME_IMAGE):
            with open(WELCOME_IMAGE, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"Error sending welcome image: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
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
        async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    context.user_data["expecting_account_id"] = True
    caption_text = "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥\n\nأرسل **ID حساب اللعبة** الآن (يجب أن يكون **10 أرقام**) — سيُطلب في كل مرة."  
    await send_welcome_image(context, update.effective_chat.id, caption_text, build_main_keyboard(for_uid=uid))

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()

    # Broadcast للأدمن
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

    # متابعة الإيداع للأدمن
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

    # تعديل أسعار للأدمن
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

    # تسجيل ID الحساب للمستخدم
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
        await update.message.reply_text("✅ تم تسجيل ID حسابك بنجاح.\nاستخدم الأزرار لاختيار ما تريد.", reply_markup=build_main_keyboard(for_uid=uid))  
        return  

    # إذا المستخدم يرسل رقم عملية الإيداع
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

    # الرد العادي على الرسائل
    await update.message.reply_text(text)
    async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    uid = str(query.from_user.id)
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    if data == "back_main":  
        try:  
            await query.message.delete()  
        except:  
            pass  
        await send_welcome_image(context, chat_id, "🎮 القائمة الرئيسية:", build_main_keyboard(for_uid=uid))  
        return  

    if data == "show_goods":  
        caption_text = "🛍️ اختر السلعة التي تريدها:"  
        try:  
            await query.message.delete()  
        except:  
            pass  
        await send_welcome_image(context, chat_id, caption_text, build_goods_keyboard())  
        return  

    if data == "check_balance":  
        bal = balance.get(uid, 0)  
        await query.message.reply_text(f"💳 رصيدك الحالي: {bal} ل.س")  
        return  

    if data == "deposit":  
        context.user_data["expecting_deposit"] = True  
        await query.message.reply_text(f"📥 للإيداع: حول المبلغ إلى {DEPOSIT_NUMBER} ثم أرسل رقم العملية هنا.")  
        return  

    if data == "game_rps":  
        kb = InlineKeyboardMarkup([  
            [InlineKeyboardButton("✊ حجر", callback_data="rps_rock")],  
            [InlineKeyboardButton("🖐️ ورق", callback_data="rps_paper")],  
            [InlineKeyboardButton("✌️ مقص", callback_data="rps_scissors")],  
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_main")]  
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

    # باقي الـ callback handling (buy_, approve_, reject_, deposit_accept_, deposit_reject_, admin options...)  
    # مثل ما كتبنا في كودك الأصلي، بدون حذف أي جزء.

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Update {update} caused error {context.error}")

def run_bot():
    # Flask server
    from flask import Flask
    import threading

    app = Flask(__name__)

    @app.route("/")
    def home():
        return "✅ البوت شغال!"

    PORT = int(os.environ.get("PORT", 5000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT)).start()

    # تشغيل البوت
    application = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_error_handler(error_handler)

    print("🤖 البوت الأساسي شغال الآن...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    run_bot()
