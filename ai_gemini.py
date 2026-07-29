"""
ai_gemini.py — طبقة HF Router (ذكاء اصطناعي حقيقي)
======================================================
المزودون (بالترتيب):
  1. featherless-ai  — Qwen/Qwen2.5-7B-Instruct        (مجاني، يدعم tools)
  2. together        — Qwen/Qwen2.5-7B-Instruct-Turbo  (احتياطي، يدعم tools)
  3. nscale          — Qwen/Qwen2.5-7B-Instruct        (احتياطي ثانٍ)

المفتاح:   HF_TOKEN  (متغير بيئة — لا يُضاف للكود أبداً)
المتطلبات: requests

────────────────────────────────────────────────────────────────
سبب HTTP 400 السابق:
  - hf-inference لم يعد يدعم نماذج chat الحديثة (يوليو 2025).
  - الحل: استخدام featherless-ai provider عبر نفس HF Router.

الواجهة الخارجية لم تتغيّر:
  ai_gemini_handler(question, user_id) -> str
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
        "keywords":         ["مستخدم", "عضو", "أعضاء", "مستخدمين", "عدد الناس"],
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
        "keywords":         ["طلب", "طلبات", "مبيع", "مبيعات", "إيداع", "شراء", "شحن", "اليوم"],
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
        "keywords":         ["حالة", "بوت", "إعداد", "رصيد", "سلعة", "ترحيب", "تشغيل"],
    },
}

_PERMISSION_LEVELS = {"admin": 1, "owner": 2}

# ── إعدادات المزودين (بالترتيب) ──────────────
# تحقّق من الدعم: inferenceProviderMapping على huggingface.co/api/models/{model}
_PROVIDERS = [
    {
        "name":  "featherless-ai",
        "url":   "https://router.huggingface.co/featherless-ai/v1/chat/completions",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
    {
        "name":  "together",
        "url":   "https://router.huggingface.co/together/v1/chat/completions",
        "model": "Qwen/Qwen2.5-7B-Instruct-Turbo",
    },
    {
        "name":  "nscale",
        "url":   "https://router.huggingface.co/nscale/v1/chat/completions",
        "model": "Qwen/Qwen2.5-7B-Instruct",
    },
]

_SYSTEM_INSTRUCTION = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "استخدم الأدوات المتاحة لجلب البيانات الحقيقية دائماً. "
    "لا تخمّن الأرقام أبداً."
)

_SYSTEM_INSTRUCTION_NO_TOOLS = (
    "أنت مساعد إداري لبوت Telegram تجاري. "
    "تجيب باللغة العربية فقط. "
    "ستُزوَّد ببيانات حقيقية من الأدوات، قدّم إجابة واضحة ومنظّمة منها."
)


# ─────────────────────────────────────────────
# دوال مساعدة داخلية
# ─────────────────────────────────────────────

def _has_permission(user_id: int | None, required: str) -> bool:
    if user_id is None:
        return False
    caller_level   = _PERMISSION_LEVELS.get("admin", 0)
    required_level = _PERMISSION_LEVELS.get(required, 99)
    return caller_level >= required_level


def _build_tools_schema() -> list[dict]:
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


def _log_debug_safe(provider: str, model: str, messages: list, tools,
                    status_code: int, resp_headers: dict, resp_body: str) -> None:
    """يطبع Debug كامل وآمن بدون كشف HF_TOKEN."""
    payload_preview = {
        "provider":   provider,
        "model":      model,
        "messages":   messages,
        "tools_sent": bool(tools),
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    print("=" * 60)
    print(f"[DEBUG] HTTP {status_code} — provider={provider}")
    print("[DEBUG] Request (بدون HF_TOKEN):")
    print(json.dumps(payload_preview, ensure_ascii=False, indent=2))
    print("[DEBUG] Response Headers:")
    for k, v in resp_headers.items():
        print(f"  {k}: {v}")
    print("[DEBUG] Response Body:")
    print(resp_body)
    print("=" * 60)
    logger.error("HF error %s | provider=%s | model=%s | body=%s",
                 status_code, provider, model, resp_body[:300])


def _post_to_provider(provider: dict, messages: list,
                      tools, hf_token: str) -> dict:
    """
    يُرسل طلب chat إلى provider واحد.
    tools = list[dict] أو None
    يطبع debug ويرفع HTTPError عند الخطأ.
    """
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type":  "application/json",
    }
    payload: dict = {
        "model":       provider["model"],
        "messages":    messages,
        "max_tokens":  1024,
        "temperature": 0.1,
    }
    if tools:
        payload["tools"] = tools
        # لا نُضيف tool_choice — يسبب 400 مع بعض providers

    resp = requests.post(provider["url"], headers=headers,
                         json=payload, timeout=60)

    if not resp.ok:
        _log_debug_safe(
            provider     = provider["name"],
            model        = provider["model"],
            messages     = messages,
            tools        = tools,
            status_code  = resp.status_code,
            resp_headers = dict(resp.headers),
            resp_body    = resp.text,
        )

    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────
# Fallback بدون tool calling
# ─────────────────────────────────────────────

def _detect_tools_by_keyword(question: str) -> list[str]:
    """
    يكتشف الأدوات المطلوبة بناءً على الكلمات المفتاحية في السؤال.
    يُستخدم فقط عند فشل tool calling.
    """
    q = question.lower()
    matched = []
    for name, info in TOOL_REGISTRY.items():
        for kw in info.get("keywords", []):
            if kw in q:
                matched.append(name)
                break
    return matched


def _run_keyword_fallback(question: str, user_id,
                          hf_token: str) -> str:
    """
    Fallback كامل عند عدم دعم tool calling:
    1. كشف الأدوات بالكلمات المفتاحية.
    2. تنفيذها مباشرة.
    3. طلب تلخيص نصي من الـ LLM.
    """
    detected = _detect_tools_by_keyword(question)

    # إذا لم يُكتشف أي أداة → اسأل الـ LLM مباشرة
    if not detected:
        messages = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION_NO_TOOLS},
            {"role": "user",   "content": question},
        ]
        for provider in _PROVIDERS:
            try:
                data = _post_to_provider(provider, messages, None, hf_token)
                return (data["choices"][0]["message"].get("content")
                        or "⚠️ لم يرجع النموذج نصاً.")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (400, 422, 503):
                    continue
                raise
        log_skipped(user_id=user_id, question=question,
                    reason="فشل جميع providers (no-tools)")
        return "⚠️ تعذّر الاتصال بالمساعد. حاول مرة أخرى."

    # تنفيذ الأدوات المكتشفة
    tool_results = []
    warnings     = []
    for name in detected:
        info = TOOL_REGISTRY[name]
        if not _has_permission(user_id, info["permission"]):
            warnings.append(f"🚫 لا تملك صلاحية تنفيذ `{name}`.")
            continue
        if info["requires_confirm"]:
            warnings.append(f"⚠️ الأداة `{name}` تحتاج تأكيداً صريحاً.")
            continue
        try:
            result = info["fn"]()
            tool_results.append(f"نتيجة {name}:\n{json.dumps(result, ensure_ascii=False, indent=2)}")
            log_action(user_id=user_id, question=question,
                       tool_name=name, arguments={},
                       executed=True, success=True)
        except Exception as exc:
            tool_results.append(f"خطأ في {name}: {exc}")
            log_action(user_id=user_id, question=question,
                       tool_name=name, arguments={},
                       executed=True, success=False, error=str(exc))

    if not tool_results:
        return ("⚠️ لا يمكن تنفيذ الأدوات.\n" +
                "\n".join(warnings)).strip()

    # اطلب من الـ LLM تلخيص البيانات
    data_block = "\n\n".join(tool_results)
    messages = [
        {"role": "system",    "content": _SYSTEM_INSTRUCTION_NO_TOOLS},
        {"role": "user",      "content": question},
        {"role": "assistant", "content": f"لديّ البيانات التالية:\n{data_block}"},
        {"role": "user",      "content": "قدّم إجابة واضحة ومنظّمة بناءً على هذه البيانات."},
    ]
    for provider in _PROVIDERS:
        try:
            data = _post_to_provider(provider, messages, None, hf_token)
            text = (data["choices"][0]["message"].get("content")
                    or "⚠️ لم يرجع النموذج نصاً.")
            return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in (400, 422, 503):
                continue
            raise

    # إذا فشل الـ LLM، أرسل البيانات الخام
    log_skipped(user_id=user_id, question=question,
                reason="فشل الـ LLM في التلخيص — إرسال بيانات خام")
    return data_block + ("\n\n" + "\n".join(warnings) if warnings else "")


# ─────────────────────────────────────────────
# محور التنفيذ مع tool calling
# ─────────────────────────────────────────────

def _process_tool_calls(tool_calls: list, messages: list,
                        question: str, user_id) -> tuple[list, list]:
    """ينفّذ tool_calls ويُضيف ردود الأدوات للمحادثة."""
    warnings = []

    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except Exception:
            args = {}

        tool_info = TOOL_REGISTRY.get(fn_name)

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


def _chat_with_tools(messages: list, tools: list,
                     hf_token: str) -> tuple[dict, str]:
    """
    يحاول الاتصال بكل provider بالترتيب.
    يُرجع (response_dict, provider_name).
    يرفع استثناءً إذا فشل الجميع.
    """
    last_exc = None
    for provider in _PROVIDERS:
        try:
            data = _post_to_provider(provider, messages, tools, hf_token)
            return data, provider["name"]
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code
            print(f"[FALLBACK] {provider['name']} → HTTP {status}, جرّب التالي")
            if status in (400, 422, 503):
                last_exc = e
                continue
            raise
        except requests.exceptions.Timeout as e:
            print(f"[FALLBACK] {provider['name']} → Timeout، جرّب التالي")
            last_exc = e
            continue

    raise last_exc


# ─────────────────────────────────────────────
# نقطة الدخول الرئيسية
# ─────────────────────────────────────────────

def ai_gemini_handler(question: str, user_id: int = None) -> str:
    """
    نقطة الدخول الرئيسية — تُستدعى من ai_manager.py فقط.
    استراتيجية التنفيذ:
      1. جرّب tool calling الحقيقي عبر providers المتاحة.
      2. إذا فشل الجميع بـ 400/422/503 → _run_keyword_fallback.
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
        tools    = _build_tools_schema()
        messages = [
            {"role": "system", "content": _SYSTEM_INSTRUCTION},
            {"role": "user",   "content": question},
        ]

        # ── الطلب الأول: اختيار الأدوات ──
        try:
            data, provider_used = _chat_with_tools(messages, tools, hf_token)
        except (requests.exceptions.HTTPError,
                requests.exceptions.Timeout) as e:
            # فشل جميع providers → Keyword fallback
            print(f"[FALLBACK] جميع providers فشلت، نستخدم keyword fallback: {e}")
            log_skipped(user_id=user_id, question=question,
                        reason=f"فشل providers، keyword fallback: {e}")
            return _run_keyword_fallback(question, user_id, hf_token)

        choice     = data["choices"][0]
        msg        = choice["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            log_skipped(user_id=user_id, question=question,
                        reason=f"النموذج ({provider_used}) أجاب بدون أداة")
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
        try:
            final, _ = _chat_with_tools(messages, tools, hf_token)
        except (requests.exceptions.HTTPError,
                requests.exceptions.Timeout):
            # إذا فشل الطلب الثاني، أرسل بيانات الأدوات مباشرة
            tool_contents = [
                m.get("content", "")
                for m in messages
                if m.get("role") == "tool"
            ]
            raw = "\n\n".join(tool_contents)
            return (raw + "\n\n" + "\n".join(warnings)).strip() if warnings else raw

        text = (final["choices"][0]["message"].get("content")
                or "⚠️ لم يرجع النموذج نصاً.")
        return (text + "\n\n" + "\n".join(warnings)).strip() if warnings else text

    except requests.exceptions.Timeout:
        log_skipped(user_id=user_id, question=question,
                    reason="Timeout عام")
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
            return f"⚠️ الوصول مرفوض من HF.\nالتفاصيل: {body[:200]}"
        if status == 429:
            return "⚠️ تجاوزت حصة الطلبات. حاول بعد دقيقة."
        return (
            f"⚠️ خطأ من HF Router (HTTP {status}).\n"
            f"التفاصيل: {body[:300]}"
        )

    except Exception as e:
        log_skipped(user_id=user_id, question=question,
                    reason=f"استثناء غير متوقع: {e}")
        return f"⚠️ حدث خطأ غير متوقع:\n{e}"
