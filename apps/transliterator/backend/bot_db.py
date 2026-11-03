"""
Database storage & management for Transliterator Telegram Bot.
Uses SQLite for zero-config persistence.
"""

import os
import sqlite3
import datetime
from typing import Dict, Any, Optional, List

DB_PATH = os.path.join(os.path.dirname(__file__), "transliterator_bot.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # User Preferences
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_prefs (
            user_id INTEGER PRIMARY KEY,
            input_script TEXT DEFAULT 'auto',
            output_script TEXT DEFAULT 'ka',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Bot Settings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Telemetry Log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS translit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            from_script TEXT,
            to_script TEXT,
            char_count INTEGER,
            source TEXT DEFAULT 'direct',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# --- User Preferences ---
def get_user_pref(user_id: int) -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT input_script, output_script FROM user_prefs WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'input_script': row['input_script'], 'output_script': row['output_script']}
    return {'input_script': 'auto', 'output_script': 'ka'}

def set_user_pref(user_id: int, input_script: Optional[str] = None, output_script: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    current = get_user_pref(user_id)
    in_s = input_script if input_script is not None else current['input_script']
    out_s = output_script if output_script is not None else current['output_script']

    cursor.execute("""
        INSERT INTO user_prefs (user_id, input_script, output_script, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            input_script = excluded.input_script,
            output_script = excluded.output_script,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, in_s, out_s))
    conn.commit()
    conn.close()

# --- Settings ---
def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row['value'] is not None:
        return row['value']
    return default

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bot_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, value))
    conn.commit()
    conn.close()

# --- Logging & Telemetry ---
def log_transliteration(user_id: int, from_script: str, to_script: str, char_count: int, source: str = 'direct'):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO translit_logs (user_id, from_script, to_script, char_count, source)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, from_script, to_script, char_count, source))
        conn.commit()
        conn.close()
    except Exception:
        pass

def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as total FROM translit_logs")
    total_conversions = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(DISTINCT user_id) as total_users FROM user_prefs")
    total_users = cursor.fetchone()['total_users']

    cursor.execute("""
        SELECT from_script, to_script, COUNT(*) as count
        FROM translit_logs
        GROUP BY from_script, to_script
        ORDER BY count DESC LIMIT 5
    """)
    top_pairs = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return {
        'total_conversions': total_conversions,
        'total_users': total_users,
        'top_pairs': top_pairs
    }

init_db()
