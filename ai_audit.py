"""
ai_audit.py — سجل عمليات المساعد الذكي
=========================================
يُسجّل كل عملية ينفّذها AI بشكل مستقل.
لا يستورد من main.py ولا من ai_gemini.py.

الاستخدام:
    from ai_audit import log_action, log_skipped
"""

import json
import os
import datetime
from threading import Lock

AUDIT_FILE = "ai_audit.json"
_lock      = Lock()


def _now() -> str:
    """الوقت الحالي بتوقيت +3 — صيغة 24 ساعة."""
    return (datetime.datetime.now() + datetime.timedelta(hours=3)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _load() -> list:
    if not os.path.exists(AUDIT_FILE):
        return []
    with open(AUDIT_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def _save(records: list) -> None:
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def log_action(
    *,
    user_id:          int | None,
    question:         str,
    tool_name:        str,
    arguments:        dict = None,
    requires_confirm: bool = False,
    executed:         bool = True,
    success:          bool = True,
    error:            str  = None,
) -> None:
    """يُسجّل عملية نفّذها AI."""
    entry = {
        "time":             _now(),
        "user_id":          user_id,
        "question":         question,
        "tool":             tool_name,
        "arguments":        arguments or {},
        "requires_confirm": requires_confirm,
        "executed":         executed,
        "success":          success,
        "error":            error,
    }
    with _lock:
        records = _load()
        records.append(entry)
        _save(records)


def log_skipped(
    *,
    user_id:  int | None,
    question: str,
    reason:   str,
) -> None:
    """يُسجّل حالة لم تُستدعَ فيها أي أداة."""
    entry = {
        "time":             _now(),
        "user_id":          user_id,
        "question":         question,
        "tool":             None,
        "arguments":        {},
        "requires_confirm": False,
        "executed":         False,
        "success":          False,
        "error":            reason,
    }
    with _lock:
        records = _load()
        records.append(entry)
        _save(records)


def get_recent(limit: int = 20) -> list:
    """يُعيد آخر N سجلاً."""
    with _lock:
        records = _load()
    return records[-limit:]
