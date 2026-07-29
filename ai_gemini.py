"""
ai_gemini.py — طبقة Hugging Face Inference API (ذكاء اصطناعي حقيقي)
=====================================================================
المزود:    Hugging Face Router → hf-inference provider
النموذج:   Qwen/Qwen2.5-7B-Instruct  (مجاني، يفهم العربية، يدعم Function Calling)
           Fallback: mistralai/Mistral-7B-Instruct-v0.3
المتطلبات: requests  (مثبّتة مسبقاً)
المفتاح:   HF_TOKEN  (متغير بيئة — لا يُضاف للكود أبداً)

الواجهة الخارجية لم تتغيّر:
    ai_gemini_handler(question, user_id) -> str

────────────────────────────────────────────────────────────────
تغييرات v2 (إصلاح HTTP 400):
  1. تغيير النموذج من Qwen2.5-72B (يتطلب PRO) إلى Qwen2.5-7B (مجاني).
  2. حذف tool_choice من الـ payload — يسبب 400 مع بعض نماذج hf-inference.
  3. إضافة debug كامل وآمن عند أي خطأ HTTP.
  4. إضافة fallback تلقائي: إذا فشل النموذج الأساسي، يجرّب النموذج الاحتياطي.
  5. إضافة fallback ثانٍ: إذا فشل طلب tools، يُعيد المحاولة بدون tools.
────────────────────────────────────────────────────────────────
"""

import os
import json
import logging
import requests

from ai_tools import get_users_count, get_orders_today, get_bot_status
from ai_audit import log_action, log_skipped

logger = logging.getLogger(__name__)

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

# ── إعدادات HF ───────────────────────────────
# النموذج الأساسي: Qwen2.5-7B مجاني ويدعم Function Calling
# (الـ 72B يتطلب اشتراك PRO على HF وكان يسبب HTTP 400)
_MODEL_PRIMARY  = "Qwen/Qwen2.5-7B-Instruct"
_MODEL_FALLBACK = "mistralai/Mistral-7B-Instruct-v0.3"
_API_URL        = "https://router.huggingface.co/hf-inference/v1/chat/completions"

_SYSTEM_INSTRUCTION = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "استخدم الأدوات المتاحة لجلب البيانات الحقيقية دائماً. "
    "لا تخمّن الأرقام أبداً."
)


# ─────────────────────────────────────────────
# دوال مساعدة داخلية
# ─────────────────────────────────────────────

def _has_permission(user_id: int | None, required: str) -> bool:
    """التحقق من صلاحية المستخدم. حالياً كل أدمن يملك صلاحية admin."""
    if user_id is None:
        return False
    # في المستقبل: ابحث في قاعدة البيانات عن دور user_id الفعلي
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _build_tools() -> list[dict]:
    """بناء قائمة الأدوات بصيغة OpenAI-compatible."""
    return [
        {
            "type": "function",
            "function": {
                "name":        name,
                "description": info["description"],
                "parameters": {
                    "type":       "object",
                    "properties": {},
                    "required":   [],
                },
            },
        }
        for name, info in TOOL_REGISTRY.items()
    ]


def _log_debug_safe(model: str, messages: list, tools: list,
                    status_code: int, headers: dict, body: str) -> None:
    """
    يطبع معلومات Debug كاملة وآمنة عند حدوث خطأ.
    لا يكشف HF_TOKEN أبداً.
    """
    # بناء الـ payload المُرسل (بدون token)
    sent_payload = {
        "model":    model,
        "messages": messages,
        "tools":    tools,
        "max_tokens":  1024,
        "temperature": 0.1,
        # tool_choice: محذوف (كان يسبب 400)
    }
    print("=" * 60)
    print(f"[DEBUG] HTTP Error {status_code}")
    print("-" * 60)
    print("[DEBUG] Request Payload (بدون HF_TOKEN):")
    print(json.dumps(sent_payload, ensure_ascii=False, indent=2))
    print("-" * 60)
    print("[DEBUG] Response Headers:")
    for k, v in headers.items():
        print(f"  {k}: {v}")
    print("-" * 60)
    print("[DEBUG] Response Body:")
    print(body)
    print("=" * 60)

    # سجّل في logger أيضاً
    logger.error(
        "HF API error %s | model=%s | body_preview=%s",
        status_code, model, body[:200]
    )


def _hf_chat(messages: list, tools: list | None,
             hf_token: str, model: str) -> dict:
    """
    يُرسل طلب chat إلى HF Inference API.

    تغييرات مهمة عن النسخة السابقة:
    - tool_choice محذوف (كان يسبب HTTP 400 مع بعض النماذج)
    - model يُمرَّر كمعامل لدعم الـ fallback
    - يُطبع debug كامل عند أي خطأ HTTP
    """
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type":  "application/json",
    }
    payload: dict = {
        "model":       model,
        "messages":    messages,
        "max_tokens":  1024,
        "temperature": 0.1,
    }
    # أضف tools فقط إذا كانت موجودة وغير فارغة
    if tools:
        payload["tools"] = tools
        # لا نُضيف tool_choice — كان يسبب HTTP 400 مع hf-inference

    resp = requests.post(_API_URL, headers=headers,
                         json=payload, timeout=60)

    # --- Debug عند أي خطأ HTTP ---
    if not resp.ok:
        _log_debug_safe(
            model       = model,
            messages    = messages,
            tools       = tools or [],
            status_code = resp.status_code,
            headers     = dict(resp.headers),
            body        = resp.text,
        )

    resp.raise_for_status()
    return resp.json()


def _process_tool_calls(tool_calls: list, messages: list,
                        question: str, user_id) -> tuple[list, list]:
    """
    ينفّذ tool_calls ويضيف ردود الأدوات للمحادثة.
    يُرجع (messages, warnings).
    """
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
                "content":      json.dumps({"error": "أداة غير معروفة"},
                                           ensure_ascii=False),
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
                "content":      json.dumps({"error": "صلاحية مرفوضة"},
                                           ensure_ascii=False),
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
                "content":      json.dumps({"error": "تحتاج تأكيداً"},
                                           ensure_ascii=False),
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

    return messages, warnings


def _chat_with_fallback(messages: list, tools: list,
                        hf_token: str) -> tuple[dict, str]:
    """
    يحاول الاتصال مع fallback تلقائي:
      1. النموذج الأساسي (Qwen2.5-7B) + tools
      2. النموذج الاحتياطي (Mistral-7B)  + tools  (إذا فشل الأول بـ 400/503)
      3. النموذج الأساسي بدون tools              (إذا فشل الثاني)
    يُرجع (response_dict, model_used)
    """
    attempts = [
        (_MODEL_PRIMARY,  tools),
        (_MODEL_FALLBACK, tools),
        (_MODEL_PRIMARY,  None),   # بدون tools كحل أخير
    ]

    last_exc = None
    for model, t in attempts:
        try:
            data = _hf_chat(messages, t, hf_token, model)
            return data, model
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            print(f"[FALLBACK] {model} tools={'yes' if t else 'no'} → HTTP {status}")
            if status in (400, 422, 503):
                last_exc = e
                continue       # جرّب التالي
            raise              # 401, 403, 429 → أوقف مباشرة
        except requests.exceptions.Timeout as e:
            last_exc = e
            continue

    raise last_exc


# ─────────────────────────────────────────────
# نقطة الدخول الرئيسية
# ─────────────────────────────────────────────

def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الرئيسية — تُستدعى من ai_manager.py فقط.
    ذكاء اصطناعي حقيقي عبر HF Inference API مع Function Calling.
    لا تُطلق استثناءات أبداً.
    """
    if not question or not question.strip():
        return "❗ السؤال فارغ."

    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        log_skipped(user_id=user_id, question=question,
                    reason="HF_TOKEN غير موجود")
        return (
            "⚠️ المساعد الذكي غير مفعّل حالياً.\n"
            "السبب: HF_TOKEN غير موجود في الإعدادات.\n"
            "احصل على مفتاح مجاني من: https://huggingface.co/settings/tokens\n"
            "ثم أضفه كـ HF_TOKEN في متغيرات البيئة على Render."
        )

    try:
        tools    = _build_tools()
        messages = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user",   "content": question},
        ]

        # ── الطلب الأول: اختيار الأدوات ──
        data, model_used = _chat_with_fallback(messages, tools, hf_token)
        choice     = data["choices"][0]
        msg        = choice["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            # النموذج أجاب مباشرة بدون أداة
            log_skipped(user_id=user_id, question=question,
                        reason="النموذج أجاب بدون أداة")
            return msg.get("content") or "⚠️ لم يرجع النموذج نصاً."

        # أضف رد المساعد مع tool_calls للمحادثة
        messages.append({
            "role":       "assistant",
            "content":    msg.get("content") or "",
            "tool_calls": tool_calls,
        })

        # ── تنفيذ الأدوات ──
        messages, warnings = _process_tool_calls(
            tool_calls, messages, question, user_id
        )

        # ── الطلب الثاني: صياغة الرد النهائي ──
        final, _ = _chat_with_fallback(messages, tools, hf_token)
        text      = (final["choices"][0]["message"].get("content")
                     or "⚠️ لم يرجع النموذج نصاً.")

        return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text

    except requests.exceptions.Timeout:
        log_skipped(user_id=user_id, question=question,
                    reason="انتهت مهلة الاتصال بـ HF")
        return "⚠️ انتهت مهلة الاتصال بالمساعد. حاول مرة أخرى."

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        body   = e.response.text[:500]
        log_skipped(user_id=user_id, question=question,
                    reason=f"HTTP {status}: {body}")
        if status == 401:
            return (
                "⚠️ HF_TOKEN غير صالح أو منتهي الصلاحية.\n"
                "تحقق من قيمة HF_TOKEN في إعدادات Render."
            )
        if status == 403:
            return (
                "⚠️ الوصول مرفوض من HF.\n"
                f"تفاصيل: {body[:200]}"
            )
        if status == 429:
            return "⚠️ تجاوزت حصة الطلبات على HF. حاول بعد دقيقة."
        if status == 503:
            return "⚠️ النموذج غير متاح حالياً على HF. حاول بعد 30 ثانية."
        # أي كود آخر (بما فيها 400) — نُظهر التفاصيل الكاملة
        return (
            f"⚠️ خطأ من خادم Hugging Face (HTTP {status}).\n"
            f"التفاصيل: {body[:300]}"
        )

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ غير متوقع:\n{e}"
