"""
database.py — طبقة التخزين المشتركة
======================================
يستخدم هذا الملف من:
    - main.py
    - ai_tools.py

يدعم وضعين تلقائياً:
    - PostgreSQL إذا كان DATABASE_URL موجوداً في متغيرات البيئة
    - ملفات JSON إذا لم يكن موجوداً (الوضع الافتراضي)

لا يحتوي على أي منطق للبوت أو Flask.
"""

import os
import json
from threading import Lock

_DB_URL  = (os.getenv("DATABASE_URL") or "").strip()
_db_lock = Lock()
_USE_DB  = False

_db_pool    = None
_db_conn    = None
_db_release = None

if _DB_URL:
    try:
        import psycopg2
        from psycopg2.extras import Json
        from psycopg2 import pool as psycopg2_pool

        _db_pool = psycopg2_pool.ThreadedConnectionPool(1, 10, _DB_URL)

        def _db_conn():
            return _db_pool.getconn()

        def _db_release(conn):
            _db_pool.putconn(conn)

        with _db_conn() as _c, _c.cursor() as _cur:
            _cur.execute("""
                CREATE TABLE IF NOT EXISTS bot_kv (
                    key        TEXT PRIMARY KEY,
                    value      JSONB NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            _c.commit()
        _db_release(_c)
        _USE_DB = True
        print("INFO: Storage = PostgreSQL (pool)")

    except Exception as _e:
        print(f"WARNING: PostgreSQL not available ({_e}); falling back to JSON files")
        _USE_DB = False
else:
    print("INFO: DATABASE_URL not set; using JSON files for storage")


def load_json(path, default):
    """
    تحميل بيانات من PostgreSQL أو ملف JSON.
    """
    if _USE_DB:
        with _db_lock:
            conn = _db_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM bot_kv WHERE key = %s", (path,))
                    row = cur.fetchone()
                    if row is not None:
                        return row[0]
                    seed = default
                    if os.path.exists(path):
                        try:
                            with open(path, "r", encoding="utf-8") as f:
                                seed = json.load(f)
                        except Exception:
                            seed = default
                    cur.execute(
                        "INSERT INTO bot_kv (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                        (path, Json(seed)),
                    )
                    conn.commit()
                    return seed
            finally:
                _db_release(conn)

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
    """
    حفظ بيانات في PostgreSQL أو ملف JSON.
    """
    if _USE_DB:
        with _db_lock:
            conn = _db_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO bot_kv (key, value, updated_at)
                        VALUES (%s, %s, NOW())
                        ON CONFLICT (key) DO UPDATE
                            SET value = EXCLUDED.value,
                                updated_at = NOW()
                        """,
                        (path, Json(data)),
                    )
                    conn.commit()
            finally:
                _db_release(conn)
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
