"""
ai_gemini.py — طبقة Groq (بديل Gemini المجاني) مع Function Calling
====================================================================
المزود:  Groq — https://console.groq.com  (مجاني، بدون billing)
المتطلبات:  pip install groq
المفتاح:    GROQ_API_KEY (متغير بيئة)
النموذج:   llama-3.3-70b-versatile  (يدعم function calling)

الواجهة الخارجية لم تتغير:
    ai_gemini_handler(question, user_id) -> str
"""

import os
import json
from groq import Groq
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
            "مقسّمين إلى أدمنية ومستخدمين عاديين. "
            "استخدمه عند السؤال عن المستخدمين أو الأعضاء."
        ),
        "permission":       "admin",
        "requires_confirm": False,
    },

    "get_orders_today": {
        "fn":               get_orders_today,
        "description":      (
            "يرجع إحصائيات طلبات اليوم الحالي: "
            "الإجمالي، قيد الانتظار، المكتملة، المرفوضة، "
            "طلبات الشحن، وطلبات الشراء. "
            "استخدمه عند السؤال عن الطلبات أو المبيعات أو الإيداعات."
        ),
        "permission":       "admin",
        "requires_confirm": False,
    },

    "get_bot_status": {
        "fn":               get_bot_status,
        "description":      (
            "يرجع حالة البوت العامة: مدة التشغيل، عدد السلع، "
            "عدد المستخدمين، إجمالي الأرصدة، أرقام الإيداع، "
            "ورسالة الترحيب. "
            "استخدمه عند السؤال عن حالة البوت أو الإعدادات."
        ),
        "permission":       "admin",
        "requires_confirm": False,
    },

}

_PERMISSION_LEVELS = {"admin": 1, "owner": 2}

_SYSTEM_INSTRUCTION = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "استخدم الأدوات المتاحة لجلب البيانات الحقيقية دائماً. "
    "لا تخمّن الأرقام."
)

_MODEL = "llama-3.3-70b-versatile"

_client = None


def _has_permission(user_id: int | None, required: str) -> bool:
    if user_id is None:
        return False
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _build_tools() -> list[dict]:
    """بناء قائمة الأدوات بصيغة OpenAI / Groq."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        for name, info in TOOL_REGISTRY.items()
    ]


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    _client = Groq(api_key=api_key)
    return _client


def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الرئيسية — تُستدعى من ai_manager.py فقط.
    نفس الواجهة السابقة، التنفيذ عبر Groq بدلاً من Gemini.
    لا يوقف البوت عند أي خطأ.
    """
    if not question or not question.strip():
        return "❗ السؤال فارغ."

    client = _get_client()
    if client is None:
        log_skipped(user_id=user_id, question=question,
                    reason="GROQ_API_KEY غير موجود")
        return (
            "⚠️ المساعد الذكي غير مفعّل حالياً.\n"
            "السبب: GROQ_API_KEY غير موجود في الإعدادات.\n"
            "احصل على مفتاح مجاني من: https://console.groq.com\n"
            "ثم أضفه كـ GROQ_API_KEY في متغيرات البيئة."
        )

    try:
        messages = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user",   "content": question},
        ]
        tools = _build_tools()

        # الطلب الأول — قد يُرجع tool calls
        response = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=1024,
        )

        msg = response.choices[0].message

        # إذا لم يطلب أداة — أرجع الرد مباشرة
        if not msg.tool_calls:
            log_skipped(user_id=user_id, question=question,
                        reason="Groq أجاب بدون أداة")
            return msg.content or "⚠️ لم يرجع المساعد نصاً."

        # معالجة كل أداة مطلوبة
        messages.append({"role": "assistant", "content": msg.content,
                         "tool_calls": [
                             {
                                 "id":       tc.id,
                                 "type":     "function",
                                 "function": {
                                     "name":      tc.function.name,
                                     "arguments": tc.function.arguments
                                 }
                             }
                             for tc in msg.tool_calls
                         ]})

        warnings = []

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            args    = json.loads(tc.function.arguments or "{}")
            tool_info = TOOL_REGISTRY.get(fn_name)

            if tool_info is None:
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           executed=False, success=False,
                           error="أداة غير موجودة في TOOL_REGISTRY")
                warnings.append(f"⚠️ أداة غير معروفة: {fn_name}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": "أداة غير معروفة"}, ensure_ascii=False)
                })
                continue

            needs_confirm = tool_info["requires_confirm"]

            if not _has_permission(user_id, tool_info["permission"]):
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           requires_confirm=needs_confirm, executed=False,
                           success=False,
                           error=f"صلاحية مرفوضة — مطلوب: {tool_info['permission']}")
                warnings.append(f"🚫 لا تملك صلاحية تنفيذ `{fn_name}`.")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": "صلاحية مرفوضة"}, ensure_ascii=False)
                })
                continue

            if needs_confirm:
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           requires_confirm=True, executed=False,
                           success=False, error="في انتظار تأكيد الأدمن")
                warnings.append(
                    f"⚠️ الأداة `{fn_name}` تحتاج تأكيداً صريحاً قبل التنفيذ.")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps({"error": "تحتاج تأكيداً"}, ensure_ascii=False)
                })
                continue

            # تنفيذ الأداة
            try:
                result  = tool_info["fn"]()
                success, err_msg = True, None
            except Exception as exc:
                result  = {"error": str(exc)}
                success, err_msg = False, str(exc)

            log_action(user_id=user_id, question=question,
                       tool_name=fn_name, arguments=args,
                       executed=True, success=success, error=err_msg)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({"result": result}, ensure_ascii=False)
            })

        # الطلب الثاني — يصيغ الرد النهائي بناءً على نتائج الأدوات
        final = client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            max_tokens=1024,
        )
        text = final.choices[0].message.content or "⚠️ لم يرجع المساعد نصاً."
        return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ:\n{e}"
