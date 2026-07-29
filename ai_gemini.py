"""
ai_gemini.py — طبقة Gemini مع Function Calling
=================================================
المتطلبات:  pip install google-genai
المفتاح:    GOOGLE_API_KEY (متغير بيئة)
"""

import os
import google.genai as genai
from google.genai import types
from ai_tools import get_users_count, get_orders_today, get_bot_status
from ai_audit import log_action, log_skipped

# ─────────────────────────────────────────────
# TOOL_REGISTRY — المصدر الوحيد لتعريف الأدوات
# لإضافة أداة: أضف مدخلاً واحداً هنا فقط.
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

    # ── أمثلة لأدوات مستقبلية ─────────────────
    # "change_price":   { "fn": change_price,   "permission": "admin", "requires_confirm": True,  ... },
    # "send_broadcast": { "fn": send_broadcast, "permission": "owner", "requires_confirm": True,  ... },
    # "ban_user":       { "fn": ban_user,       "permission": "owner", "requires_confirm": True,  ... },
    # "restart_bot":    { "fn": restart_bot,    "permission": "owner", "requires_confirm": True,  ... },

}

_PERMISSION_LEVELS = {"admin": 1, "owner": 2}


def _has_permission(user_id: int | None, required: str) -> bool:
    if user_id is None:
        return False
    # TODO: ربط بقائمة owner_ids من settings.json
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _build_tools() -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=name,
            description=info["description"],
            parameters=types.Schema(type=types.Type.OBJECT, properties={}),
        )
        for name, info in TOOL_REGISTRY.items()
    ]
    return [types.Tool(function_declarations=declarations)]


_SYSTEM_INSTRUCTION = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "استخدم الأدوات المتاحة لجلب البيانات الحقيقية دائماً. "
    "لا تخمّن الأرقام."
)

_client = None
_config  = None


def _get_client():
    global _client, _config
    if _client is not None:
        return _client
    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None
    _client = genai.Client(api_key=api_key)
    _config  = types.GenerateContentConfig(
        system_instruction=_SYSTEM_INSTRUCTION,
        tools=_build_tools(),
        max_output_tokens=8192,
    )
    return _client


_MODEL = "gemini-2.0-flash"


def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة دخول Gemini — تُستدعى من ai_manager.py فقط.
    لا يوقف البوت عند أي خطأ.
    """
    if not question or not question.strip():
        return "❗ السؤال فارغ."

    client = _get_client()
    if client is None:
        log_skipped(user_id=user_id, question=question,
                    reason="GOOGLE_API_KEY غير موجود")
        return (
            "⚠️ المساعد الذكي غير مفعّل حالياً.\n"
            "السبب: GOOGLE_API_KEY غير موجود في الإعدادات.\n"
            "تواصل مع المطوّر لتفعيله."
        )

    try:
        contents = [types.Content(role="user",
                                  parts=[types.Part(text=question)])]

        response  = client.models.generate_content(
            model=_MODEL, contents=contents, config=_config)
        candidate = response.candidates[0]

        function_calls = [
            p.function_call for p in candidate.content.parts
            if p.function_call is not None
        ]

        if not function_calls:
            log_skipped(user_id=user_id, question=question,
                        reason="Gemini أجاب بدون أداة")
            return _extract_text(candidate)

        contents.append(candidate.content)
        tool_parts = []
        warnings   = []

        for fc in function_calls:
            tool_info = TOOL_REGISTRY.get(fc.name)
            args      = dict(fc.args) if fc.args else {}

            if tool_info is None:
                log_action(user_id=user_id, question=question,
                           tool_name=fc.name, arguments=args,
                           executed=False, success=False,
                           error="أداة غير موجودة في TOOL_REGISTRY")
                warnings.append(f"⚠️ أداة غير معروفة: {fc.name}")
                continue

            needs_confirm = tool_info["requires_confirm"]

            if not _has_permission(user_id, tool_info["permission"]):
                log_action(user_id=user_id, question=question,
                           tool_name=fc.name, arguments=args,
                           requires_confirm=needs_confirm, executed=False,
                           success=False,
                           error=f"صلاحية مرفوضة — مطلوب: {tool_info['permission']}")
                warnings.append(f"🚫 لا تملك صلاحية تنفيذ `{fc.name}`.")
                continue

            if needs_confirm:
                log_action(user_id=user_id, question=question,
                           tool_name=fc.name, arguments=args,
                           requires_confirm=True, executed=False,
                           success=False, error="في انتظار تأكيد الأدمن")
                warnings.append(
                    f"⚠️ الأداة `{fc.name}` تحتاج تأكيداً صريحاً قبل التنفيذ.")
                continue

            try:
                result  = tool_info["fn"]()
                success, err_msg = True, None
            except Exception as exc:
                result  = {"error": str(exc)}
                success, err_msg = False, str(exc)

            log_action(user_id=user_id, question=question,
                       tool_name=fc.name, arguments=args,
                       executed=True, success=success, error=err_msg)

            tool_parts.append(types.Part(
                function_response=types.FunctionResponse(
                    name=fc.name, response={"result": result})))

        if not tool_parts:
            return "\n\n".join(warnings)

        contents.append(types.Content(role="tool", parts=tool_parts))
        final = client.models.generate_content(
            model=_MODEL, contents=contents, config=_config)
        text  = _extract_text(final.candidates[0])
        return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ:\n{e}"


def _extract_text(candidate) -> str:
    parts = [p.text for p in candidate.content.parts if getattr(p, "text", None)]
    return "\n".join(parts).strip() if parts else "⚠️ لم يرجع Gemini نصاً."
