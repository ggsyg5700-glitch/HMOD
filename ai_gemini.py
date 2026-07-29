"""
ai_gemini.py — محرك NLP عربي مدمج (بدون API خارجي)
=====================================================
لا يحتاج مفتاح API ولا حساب خارجي — يعمل مباشرة.
الواجهة الخارجية لم تتغيّر:
    ai_gemini_handler(question, user_id) -> str
"""

from ai_tools import get_users_count, get_orders_today, get_bot_status
from ai_audit import log_action, log_skipped

# ─────────────────────────────────────────────
# TOOL_REGISTRY — المصدر الوحيد لتعريف الأدوات
# ─────────────────────────────────────────────

TOOL_REGISTRY = {

    "get_users_count": {
        "fn":               get_users_count,
        "description":      (
            "يرجع عدد المستخدمين المسجلين في البوت، "
            "مقسّمين إلى أدمنية ومستخدمين عاديين."
        ),
        "permission":       "admin",
        "requires_confirm": False,
        "keywords": [
            "مستخدم", "مستخدمين", "عضو", "أعضاء", "عدد الناس",
            "كم شخص", "كم عضو", "أدمن", "user", "users", "member",
        ],
    },

    "get_orders_today": {
        "fn":               get_orders_today,
        "description":      (
            "يرجع إحصائيات طلبات اليوم: الإجمالي، قيد الانتظار، "
            "المكتملة، المرفوضة، الشحن، الشراء."
        ),
        "permission":       "admin",
        "requires_confirm": False,
        "keywords": [
            "طلب", "طلبات", "اليوم", "مبيعات", "إيداع", "إيداعات",
            "شحن", "شراء", "كم طلب", "order", "orders", "today",
            "مكتمل", "قيد الانتظار", "مرفوض",
        ],
    },

    "get_bot_status": {
        "fn":               get_bot_status,
        "description":      (
            "يرجع حالة البوت: مدة التشغيل، السلع، الأرصدة، الإعدادات."
        ),
        "permission":       "admin",
        "requires_confirm": False,
        "keywords": [
            "حالة", "بوت", "bot", "status", "تشغيل", "وقت", "uptime",
            "سلع", "رصيد", "أرصدة", "إعداد", "إعدادات", "رقم الإيداع",
            "ترحيب", "رسالة",
        ],
    },

    # ── أمثلة لأدوات مستقبلية تحتاج تأكيداً ──────────────────
    # "change_price":   { "fn": change_price,   "permission": "admin", "requires_confirm": True,  ... },
    # "send_broadcast": { "fn": send_broadcast, "permission": "owner", "requires_confirm": True,  ... },
    # "ban_user":       { "fn": ban_user,       "permission": "owner", "requires_confirm": True,  ... },

}

_PERMISSION_LEVELS = {"admin": 1, "owner": 2}


def _has_permission(user_id: int | None, required: str) -> bool:
    if user_id is None:
        return False
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _detect_tools(question: str) -> list[str]:
    """يكشف الأدوات المطلوبة من الكلمات المفتاحية في السؤال."""
    q_lower = question.lower()
    matched = []
    for name, info in TOOL_REGISTRY.items():
        for kw in info.get("keywords", []):
            if kw in q_lower:
                if name not in matched:
                    matched.append(name)
                break
    # إذا لم يُكشف شيء → شغّل الثلاثة (سؤال عام)
    if not matched:
        matched = list(TOOL_REGISTRY.keys())
    return matched


def _format_users(data: dict) -> str:
    return (
        f"👥 **المستخدمون**\n"
        f"• الإجمالي: {data['total']}\n"
        f"• أدمنية: {data['admins']}\n"
        f"• مستخدمون عاديون: {data['regular_users']}"
    )


def _format_orders(data: dict) -> str:
    return (
        f"📦 **طلبات اليوم** ({data['date']})\n"
        f"• الإجمالي: {data['total']}\n"
        f"• قيد الانتظار: {data['pending']}\n"
        f"• مكتملة: {data['completed']}\n"
        f"• مرفوضة: {data['rejected']}\n"
        f"• طلبات شحن: {data['deposits']}\n"
        f"• طلبات شراء: {data['purchases']}"
    )


def _format_status(data: dict) -> str:
    deposits = ", ".join(data["deposit_numbers"]) if data["deposit_numbers"] else "لا يوجد"
    return (
        f"🤖 **حالة البوت**\n"
        f"• مدة التشغيل: {data['uptime']}\n"
        f"• السلع: {data['goods_count']}\n"
        f"• المستخدمون: {data['users_count']}\n"
        f"• إجمالي الأرصدة: {data['total_balance']:,.2f}\n"
        f"• أرقام الإيداع: {deposits}"
    )


_FORMATTERS = {
    "get_users_count":  _format_users,
    "get_orders_today": _format_orders,
    "get_bot_status":   _format_status,
}


def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الرئيسية — تُستدعى من ai_manager.py فقط.
    لا تُطلق استثناءات أبداً.
    """
    if not question or not question.strip():
        return "❗ السؤال فارغ."

    try:
        tool_names = _detect_tools(question)
        results    = []
        warnings   = []

        for name in tool_names:
            tool_info = TOOL_REGISTRY.get(name)
            if tool_info is None:
                continue

            args          = {}
            needs_confirm = tool_info["requires_confirm"]

            # فحص الصلاحية
            if not _has_permission(user_id, tool_info["permission"]):
                log_action(
                    user_id=user_id, question=question,
                    tool_name=name, arguments=args,
                    requires_confirm=needs_confirm,
                    executed=False, success=False,
                    error=f"صلاحية مرفوضة — مطلوب: {tool_info['permission']}",
                )
                warnings.append(f"🚫 لا تملك صلاحية تنفيذ `{name}`.")
                continue

            # فحص requires_confirm
            if needs_confirm:
                log_action(
                    user_id=user_id, question=question,
                    tool_name=name, arguments=args,
                    requires_confirm=True,
                    executed=False, success=False,
                    error="في انتظار تأكيد الأدمن",
                )
                warnings.append(
                    f"⚠️ الأداة `{name}` تحتاج تأكيداً صريحاً قبل التنفيذ."
                )
                continue

            # تنفيذ الأداة
            try:
                data    = tool_info["fn"]()
                success, err_msg = True, None
            except Exception as exc:
                data    = None
                success, err_msg = False, str(exc)

            log_action(
                user_id=user_id, question=question,
                tool_name=name, arguments=args,
                executed=True, success=success, error=err_msg,
            )

            if success and data is not None:
                formatter = _FORMATTERS.get(name)
                results.append(formatter(data) if formatter else str(data))
            else:
                warnings.append(f"⚠️ فشل تنفيذ `{name}`: {err_msg}")

        if not results and not warnings:
            log_skipped(user_id=user_id, question=question,
                        reason="لم يُكشف أي أداة مناسبة")
            return "❓ لم أفهم سؤالك. اسألني عن: المستخدمين، الطلبات، أو حالة البوت."

        parts = results + (["---", *warnings] if warnings else [])
        return "\n\n".join(parts).strip()

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ:\n{e}"
