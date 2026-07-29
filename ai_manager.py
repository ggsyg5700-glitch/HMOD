"""
ai_manager.py — نقطة الدخول الوحيدة للمساعد الإداري
======================================================
يستقبل السؤال من أي مصدر (Telegram، اختبار مباشر، ...)
ويمرّره لـ ai_gemini.py — لا منطق هنا غير التوجيه.

الاستخدام من main.py لاحقاً:
    from ai_manager import handle_admin_question
    reply = handle_admin_question(question, user_id)
"""

from ai_gemini import ai_gemini_handler


def handle_admin_question(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الوحيدة للمساعد الإداري.

    المعاملات:
        question (str)      — سؤال الأدمن
        user_id  (int|None) — معرف الأدمن في Telegram

    القيمة المُرجعة:
        str — إجابة جاهزة للإرسال، لا تُطلق استثناءات أبداً
    """
    return ai_gemini_handler(question, user_id=user_id)


# ─────────────────────────────────────────────
# اختبار مباشر (python ai_manager.py)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from ai_audit import get_recent

    tests = [
        ("كم عدد المستخدمين؟",           123456789),
        ("كم طلب اليوم وما حالة البوت؟", 123456789),
        ("",                              123456789),   # سؤال فارغ
        ("كم عدد المستخدمين؟",           None),        # user_id مجهول
    ]

    print("=" * 55)
    print("اختبار ai_manager.py ← ai_gemini.py")
    print("=" * 55)

    for question, uid in tests:
        label = repr(question) if not question else question
        print(f"\n❓ {label}  (user_id={uid})")
        print("─" * 55)
        print(handle_admin_question(question, user_id=uid))

    print("\n" + "=" * 55)
    print("آخر سجلات Audit Log:")
    print("─" * 55)
    print(json.dumps(get_recent(5), ensure_ascii=False, indent=2))
