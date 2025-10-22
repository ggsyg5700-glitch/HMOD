import os
import sys
import json
import uuid
import datetime
from typing import Dict
from flask import Flask, request
import asyncio
from threading import Thread

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

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
DEPOSIT_NUMBER = os.getenv("DEPOSIT_NUMBER") or "97675410"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", 10000))

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

import random

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    context.user_data["expecting_account_id"] = True
    
    caption_text = "🎮 أهلاً بك في البوت! اضغط على أي زر للبدء 🔥\n\nأرسل **ID حساب اللعبة** الآن (يجب أن يكون **10 أرقام**) — سيُطلب في كل مرة."
    
    await send_welcome_image(context, update.effective_chat.id, caption_text, build_main_keyboard(for_uid=uid))

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
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        await query.message.reply_text("⚙️ لوحة الأدمن:", reply_markup=build_admin_keyboard())
        return

    if data == "admin_show_goods":
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        await query.message.reply_text("قائمة السلع (عرض خاص بالأدمن):", reply_markup=build_goods_keyboard())
        return

    if data == "admin_broadcast":
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        context.user_data["awaiting_broadcast"] = True
        await query.message.reply_text("📢 اكتب الرسالة التي تريد إرسالها لجميع المستخدمين:")
        return

    if data == "admin_show_users":
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
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        items_text = "\n".join([f"{it['id']}. {it['name']} - {it['price']} ل.س" for it in goods])
        context.user_data["expecting_price_item"] = True
        await query.message.reply_text(f"📋 قائمة السلع:\n{items_text}\n\n📥 أرسل رقم السلعة التي تريد تعديل سعرها:")
        return

    if data == "admin_time":
        if uid != str(ADMIN_ID):
            await query.message.reply_text("❌ هذا الخيار متاح فقط للأدمن.")
            return
        now = datetime.datetime.utcnow()
        time_str = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        await query.message.reply_text(f"🕒 التاريخ والوقت الحالي:\n{time_str}")
        return

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

async def setup_and_run_bot():
    global app_bot, bot_loop
    bot_loop = asyncio.get_running_loop()
    
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
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

if WEBHOOK_URL:
    bot_thread = Thread(target=run_bot_in_thread, daemon=True)
    bot_thread.start()
    import time
    time.sleep(2)
    print(f"🤖 البوت جاهز لاستقبال webhooks على المنفذ {PORT}...")

def main():
    if not WEBHOOK_URL:
        app_bot_local = ApplicationBuilder().token(BOT_TOKEN).build()
        app_bot_local.add_handler(CommandHandler("start", start))
        app_bot_local.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        app_bot_local.add_handler(CallbackQueryHandler(callback_handler))
        app_bot_local.add_error_handler(error_handler)
        print("🤖 البوت يعمل محلياً بوضع polling...")
        app_bot_local.run_polling(allowed_updates=Update.ALL_TYPES)
    else:
        print(f"🚀 بدء خادم Flask على المنفذ {PORT}...")
        app.run(host='0.0.0.0', port=PORT)

if __name__ == "__main__":
    main()
