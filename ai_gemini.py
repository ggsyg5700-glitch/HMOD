"""
ai_gemini.py — طبقة OpenRouter (ذكاء اصطناعي حقيقي مع Function Calling)
=========================================================================
المزود:    OpenRouter — https://openrouter.ai  (مجاني، بدون billing)
النموذج:   meta-llama/llama-3.3-70b-instruct:free  (يدعم function calling)
المتطلبات: requests  (مثبّتة مسبقاً — لا حاجة لمكتبة إضافية)
المفتاح:   OPENROUTER_API_KEY  (متغير بيئة)

الواجهة الخارجية لم تتغيّر:
    ai_gemini_handler(question, user_id) -> str
"""

import os
import json
import requests

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

}

_PERMISSION_LEVELS = {"admin": 1, "owner": 2}

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL   = "meta-llama/llama-3.3-70b-instruct:free"

_SYSTEM_INSTRUCTION = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "استخدم الأدوات المتاحة لجلب البيانات الحقيقية دائماً. "
    "لا تخمّن الأرقام."
)


def _has_permission(user_id: int | None, required: str) -> bool:
    if user_id is None:
        return False
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _build_tools() -> list[dict]:
    """بناء قائمة الأدوات بصيغة OpenAI / OpenRouter."""
    return [
        {
            "type": "function",
            "function": {
                "name":        name,
                "description": info["description"],
                "parameters": {
                    "type":       "object",
                    "properties": {},
                    "required":   []
                }
            }
        }
        for name, info in TOOL_REGISTRY.items()
    ]


def _get_api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def _chat(messages: list, tools: list, api_key: str) -> dict:
    """يُرسل طلباً إلى OpenRouter ويُرجع الرد الخام."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://telegram-bot-admin",
        "X-Title":       "TelegramBotAdmin",
    }
    payload = {
        "model":      _MODEL,
        "messages":   messages,
        "tools":      tools,
        "tool_choice": "auto",
        "max_tokens": 1024,
    }
    resp = requests.post(_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الرئيسية — تُستدعى من ai_manager.py فقط.
    ذكاء اصطناعي حقيقي عبر OpenRouter مع Function Calling.
    لا تُطلق استثناءات أبداً.
    """
    if not question or not question.strip():
        return "❗ السؤال فارغ."

    api_key = _get_api_key()
    if not api_key:
        log_skipped(user_id=user_id, question=question,
                    reason="OPENROUTER_API_KEY غير موجود")
        return (
            "⚠️ المساعد الذكي غير مفعّل حالياً.\n"
            "السبب: OPENROUTER_API_KEY غير موجود في الإعدادات.\n"
            "احصل على مفتاح مجاني من: https://openrouter.ai\n"
            "ثم أضفه كـ OPENROUTER_API_KEY في متغيرات البيئة."
        )

    try:
        tools    = _build_tools()
        messages = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user",   "content": question},
        ]

        # ── الطلب الأول: قد يُرجع tool_calls ──
        data   = _chat(messages, tools, api_key)
        choice = data["choices"][0]
        msg    = choice["message"]

        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # النموذج أجاب مباشرة بدون أداة
            log_skipped(user_id=user_id, question=question,
                        reason="النموذج أجاب بدون أداة")
            return msg.get("content") or "⚠️ لم يرجع النموذج نصاً."

        # ── معالجة tool_calls ──
        messages.append({
            "role":       "assistant",
            "content":    msg.get("content") or "",
            "tool_calls": tool_calls,
        })

        warnings = []

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}

            tool_info = TOOL_REGISTRY.get(fn_name)

            # أداة غير موجودة
            if tool_info is None:
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           executed=False, success=False,
                           error="أداة غير موجودة في TOOL_REGISTRY")
                warnings.append(f"⚠️ أداة غير معروفة: {fn_name}")
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      json.dumps({"error": "أداة غير معروفة"}, ensure_ascii=False),
                })
                continue

            needs_confirm = tool_info["requires_confirm"]

            # فحص الصلاحية
            if not _has_permission(user_id, tool_info["permission"]):
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           requires_confirm=needs_confirm,
                           executed=False, success=False,
                           error=f"صلاحية مرفوضة — مطلوب: {tool_info['permission']}")
                warnings.append(f"🚫 لا تملك صلاحية تنفيذ `{fn_name}`.")
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      json.dumps({"error": "صلاحية مرفوضة"}, ensure_ascii=False),
                })
                continue

            # فحص requires_confirm
            if needs_confirm:
                log_action(user_id=user_id, question=question,
                           tool_name=fn_name, arguments=args,
                           requires_confirm=True,
                           executed=False, success=False,
                           error="في انتظار تأكيد الأدمن")
                warnings.append(
                    f"⚠️ الأداة `{fn_name}` تحتاج تأكيداً صريحاً قبل التنفيذ.")
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      json.dumps({"error": "تحتاج تأكيداً"}, ensure_ascii=False),
                })
                continue

            # ── تنفيذ الأداة ──
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
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      json.dumps({"result": result}, ensure_ascii=False),
            })

        # ── الطلب الثاني: يصيغ الرد النهائي ──
        final   = _chat(messages, tools, api_key)
        text    = final["choices"][0]["message"].get("content") or "⚠️ لم يرجع النموذج نصاً."
        return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text

    except requests.exceptions.Timeout:
        log_skipped(user_id=user_id, question=question, reason="انتهت مهلة الاتصال")
        return "⚠️ انتهت مهلة الاتصال بالمساعد. حاول مرة أخرى."

    except requests.exceptions.HTTPError as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        return f"⚠️ خطأ من خادم OpenRouter ({e.response.status_code})."

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ:\n{e}"
