"""
ai_tools.py — أدوات قراءة البيانات للمساعد الإداري
=====================================================
هذا الملف مستقل تماماً عن منطق البوت.
- يقرأ عبر database.py (يدعم JSON وPostgreSQL تلقائياً)
- لا يعدل أي بيانات
- لا يستورد من main.py
- لا يتصل بأي AI الآن

الاستخدام اللاحق:
    from ai_tools import get_users_count, get_orders_today, get_bot_status
"""

import json
import datetime
from database import load_json

USERS_FILE    = "users.json"
ORDERS_FILE   = "orders.json"
GOODS_FILE    = "goods.json"
BALANCE_FILE  = "balance.json"
SETTINGS_FILE = "settings.json"


def get_users_count() -> dict:
    """
    يرجع عدد المستخدمين المسجلين في البوت.
    """
    users = load_json(USERS_FILE, {})
    total   = len(users)
    admins  = sum(1 for u in users.values() if u.get("role") == "admin")
    regular = total - admins
    return {
        "total":         total,
        "admins":        admins,
        "regular_users": regular
    }


def get_orders_today() -> dict:
    """
    يرجع إحصائيات طلبات اليوم الحالي.
    """
    orders = load_json(ORDERS_FILE, [])
    today_str = (datetime.datetime.now() + datetime.timedelta(hours=3)).strftime("%Y-%m-%d")
    today_orders = [o for o in orders if o.get("timestamp", "").startswith(today_str)]

    pending   = sum(1 for o in today_orders if o.get("status") == "قيد الانتظار")
    completed = sum(1 for o in today_orders if o.get("status") == "مكتمل")
    rejected  = sum(1 for o in today_orders if o.get("status") == "مرفوض")
    deposits  = sum(1 for o in today_orders if "شحن رصيد" in o.get("item_name", ""))
    purchases = len(today_orders) - deposits

    return {
        "date":      today_str,
        "total":     len(today_orders),
        "pending":   pending,
        "completed": completed,
        "rejected":  rejected,
        "deposits":  deposits,
        "purchases": purchases
    }


def get_bot_status(bot_start_time: float = None) -> dict:
    """
    يرجع حالة البوت العامة.
    """
    goods    = load_json(GOODS_FILE,    [])
    users    = load_json(USERS_FILE,    {})
    balance  = load_json(BALANCE_FILE,  {})
    settings = load_json(SETTINGS_FILE, {})

    if bot_start_time is not None:
        elapsed = int(datetime.datetime.now().timestamp() - bot_start_time)
        hours   = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        uptime  = f"{hours} ساعة و {minutes} دقيقة و {seconds} ثانية"
    else:
        uptime = "غير معروف (سيُفعَّل عند الربط مع البوت)"

    total_balance = sum(v for v in balance.values() if isinstance(v, (int, float)))

    return {
        "uptime":          uptime,
        "goods_count":     len(goods),
        "users_count":     len(users),
        "total_balance":   round(total_balance, 2),
        "deposit_numbers": settings.get("deposit_numbers", []),
        "welcome_message": settings.get("welcome_message", "")
    }


if __name__ == "__main__":
    print("=" * 45)
    print("اختبار ai_tools.py")
    print("=" * 45)

    print("\n[1] get_users_count()")
    print(json.dumps(get_users_count(), ensure_ascii=False, indent=2))

    print("\n[2] get_orders_today()")
    print(json.dumps(get_orders_today(), ensure_ascii=False, indent=2))

    print("\n[3] get_bot_status()")
    print(json.dumps(get_bot_status(), ensure_ascii=False, indent=2))

    print("\n" + "=" * 45)
    print("✅ جميع الأدوات تعمل بدون أخطاء")
