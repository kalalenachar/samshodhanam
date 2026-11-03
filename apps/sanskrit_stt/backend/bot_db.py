import sqlite3
import os
import math
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "samshodhana_bot.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            daily_max_seconds REAL DEFAULT 6000.0,
            daily_used_seconds REAL DEFAULT 0.0,
            total_used_seconds REAL DEFAULT 0.0,
            last_used_date TEXT,
            request_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            allow_ai_clean INTEGER DEFAULT 1,
            allow_ai_assist INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            access_code TEXT NOT NULL,
            preferred_language TEXT DEFAULT 'sa-IN',
            preferred_script TEXT DEFAULT 'devanagari',
            allow_ai_clean INTEGER DEFAULT 1,
            allow_ai_assist INTEGER DEFAULT 1,
            daily_used_seconds REAL DEFAULT 0.0,
            total_used_seconds REAL DEFAULT 0.0,
            request_count INTEGER DEFAULT 0,
            logged_in_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(access_code) REFERENCES access_codes(code)
        );

        CREATE TABLE IF NOT EXISTS admins (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS transcription_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            access_code TEXT,
            language TEXT,
            duration_sec REAL,
            char_count INTEGER,
            transcript_snippet TEXT,
            full_transcript TEXT,
            audio_filename TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()

    # Migration check for existing databases
    cursor.execute("PRAGMA table_info(transcription_logs)")
    existing_cols = [row["name"] for row in cursor.fetchall()]
    if "full_transcript" not in existing_cols:
        cursor.execute("ALTER TABLE transcription_logs ADD COLUMN full_transcript TEXT")
    if "audio_filename" not in existing_cols:
        cursor.execute("ALTER TABLE transcription_logs ADD COLUMN audio_filename TEXT")
    if "cleaned_transcript" not in existing_cols:
        cursor.execute("ALTER TABLE transcription_logs ADD COLUMN cleaned_transcript TEXT")
    if "assisted_transcript" not in existing_cols:
        cursor.execute("ALTER TABLE transcription_logs ADD COLUMN assisted_transcript TEXT")
    
    cursor.execute("PRAGMA table_info(access_codes)")
    existing_code_cols = [row["name"] for row in cursor.fetchall()]
    if "allow_ai_clean" not in existing_code_cols:
        cursor.execute("ALTER TABLE access_codes ADD COLUMN allow_ai_clean INTEGER DEFAULT 1")
    if "allow_ai_assist" not in existing_code_cols:
        cursor.execute("ALTER TABLE access_codes ADD COLUMN allow_ai_assist INTEGER DEFAULT 1")

    cursor.execute("PRAGMA table_info(users)")
    existing_user_cols = [row["name"] for row in cursor.fetchall()]
    if "preferred_script" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN preferred_script TEXT DEFAULT 'devanagari'")
    if "allow_ai_clean" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN allow_ai_clean INTEGER DEFAULT 1")
    if "allow_ai_assist" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN allow_ai_assist INTEGER DEFAULT 1")

    # Update existing codes/users with null/0 allow_ai_assist to enabled by default
    cursor.execute("UPDATE access_codes SET allow_ai_assist = 1 WHERE allow_ai_assist IS NULL OR allow_ai_assist = 0")
    cursor.execute("UPDATE users SET allow_ai_assist = 1 WHERE allow_ai_assist IS NULL OR allow_ai_assist = 0")
    conn.commit()

    # Ensure default admin if specified in env
    admin_id = os.getenv("ADMIN_TELEGRAM_ID")
    if admin_id and admin_id.isdigit():
        add_admin(int(admin_id), "EnvAdmin")

    conn.close()

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO bot_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (key, value))
    conn.commit()
    conn.close()

def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM bot_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row["value"] is not None and str(row["value"]).strip():
        return str(row["value"])
    return default

def delete_setting(key: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bot_settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()

DEFAULT_AI_ASSIST_PROMPT = """You are a highly specialized Multimodal Speech-to-Text (STT) Proofreading Assistant for Sanskrit and Indic languages.
You are provided with BOTH an actual recorded Sanskrit audio clip AND a raw Speech-to-Text (STT) text reference.

STRICT INSTRUCTIONS:
1. Listen carefully to the attached Sanskrit audio clip and cross-verify with the provided STT text reference to resolve mishearings, acoustic ambiguities, and phonetic typos.
2. Correct grammatical case endings (vibhakti), verbal tenses/moods (lakāra), gender/number agreements (liṅga/vacana), missing or incorrect visargas (ः), anusvāras (ं), and avagrahas (ऽ) so the text makes syntactic and semantic sense.
3. Apply standard Sanskrit Sandhi rules for smooth reading, while keeping word boundaries clear and readable (avoiding compound overload).
4. Do NOT alter named entities (proper nouns) unless they are clear phonetic mishearings.
5. Preserve standard Sanskrit punctuation (dandas । and ॥) and format verses/ślokas with appropriate line breaks.
6. Cleanly remove stutters, hesitations, and filler sounds (e.g. 'umm', 'aah'). Preserve legitimate non-Sanskrit words if intentionally spoken in mixed speech/lectures.
7. Output ONLY the phonetically verified, grammatically sound text in Devanāgarī script without commentary or markdown codeblocks."""

DEFAULT_AI_CLEAN_PROMPT = """You are a highly specialized Speech-to-Text (STT) Proofreading Assistant for Sanskrit and Indic languages.
The input text was generated by a Speech-to-Text (STT) voice recognition model and contains acoustic mishearings, phonetic typos, missing or incorrect visargas (ः), anusvāras (ं), sandhi boundaries, or grammatical slips.

STRICT INSTRUCTIONS:
1. Proofread and replace words ONLY with phonetically and grammatically correct versions.
2. Correct grammatical case endings (vibhakti), lakāras, missing visargas (ः), anusvāras (ं), and avagrahas (ऽ) so the text is syntactically sound.
3. Apply standard Sanskrit Sandhi rules for smooth reading, keeping words readable and clear.
4. Do NOT change words into non-phonetically similar synonyms or alter named entities unless they are misspellings/mishearings.
5. Preserve standard Sanskrit punctuation (dandas । and ॥) and format verses/ślokas with clean line breaks.
6. Cleanly remove stutters, hesitations, and filler sounds (e.g. 'umm', 'aah'). Preserve legitimate non-Sanskrit words if part of lecture text.
7. Output ONLY the cleaned, corrected text in Devanāgarī script without markdown code blocks, explanations, or commentary."""

def get_ai_assist_prompt() -> str:
    return get_setting("stt_ai_assist_prompt", DEFAULT_AI_ASSIST_PROMPT)

def set_ai_assist_prompt(prompt: str):
    set_setting("stt_ai_assist_prompt", prompt.strip())

def get_ai_clean_prompt() -> str:
    return get_setting("stt_ai_clean_prompt", DEFAULT_AI_CLEAN_PROMPT)

def set_ai_clean_prompt(prompt: str):
    set_setting("stt_ai_clean_prompt", prompt.strip())

def is_ai_prompt_customized(prompt_type: str) -> bool:
    key = f"stt_{prompt_type}_prompt"
    val = get_setting(key, "")
    return bool(val and val.strip())

def reset_ai_prompt(prompt_type: str):
    key = f"stt_{prompt_type}_prompt"
    delete_setting(key)

ALL_LANGUAGES = {
    "sa": "Sanskrit (संस्कृतम्)",
    "hi": "Hindi (हिन्दी)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "te": "Telugu (తెలుగు)",
    "ta": "Tamil (தமிழ்)",
    "ml": "Malayalam (മലയാളം)",
    "mr": "Marathi (मराठी)",
    "bn": "Bengali (বাংলা)",
    "gu": "Gujarati (ગુજરાતી)",
    "pa": "Punjabi (ਪੰਜਾਬੀ)",
    "or": "Odia (ଓଡ଼ିଆ)",
    "as": "Assamese (অসমীয়া)",
    "ur": "Urdu (اردو)",
    "ne": "Nepali (नेपाली)"
}

def get_enabled_languages():
    import json
    val = get_setting("enabled_languages", "")
    if val:
        try:
            codes = json.loads(val)
            if isinstance(codes, list) and len(codes) > 0:
                return [c for c in codes if c in ALL_LANGUAGES]
        except Exception:
            pass
    return list(ALL_LANGUAGES.keys())

def set_enabled_languages(codes_list):
    import json
    valid = [c for c in codes_list if c in ALL_LANGUAGES]
    if not valid:
        valid = ["sa"]
    set_setting("enabled_languages", json.dumps(valid))
    return valid

def is_language_enabled(code: str) -> bool:
    if not code:
        return False
    short_code = code.split("-")[0].lower()
    enabled = get_enabled_languages()
    return short_code in enabled or code in enabled

def get_default_language():
    def_lang = get_setting("default_language", "sa")
    enabled = get_enabled_languages()
    if def_lang in enabled:
        return def_lang
    return enabled[0] if enabled else "sa"

def set_default_language(code: str):
    if not code:
        return get_default_language()
    short_code = code.split("-")[0].lower()
    enabled = get_enabled_languages()
    if short_code in enabled:
        set_setting("default_language", short_code)
    elif code in enabled:
        set_setting("default_language", code)
    return get_default_language()


ALL_SCRIPTS = {
    "devanagari": "Devanagari (संस्कृतम्)",
    "iast": "IAST (Romanized)",
    "tamil": "Tamil (தமிழ் - த² த³ த⁴)",
    "telugu": "Telugu (తెలుగు)",
    "kannada": "Kannada (ಕನ್ನಡ)",
    "malayalam": "Malayalam (മലയാളം)",
    "iso": "ISO 15919",
    "slp1": "SLP1 (ASCII / Computer Code)"
}

def get_enabled_scripts():
    import json
    val = get_setting("enabled_scripts", "")
    if val:
        try:
            codes = json.loads(val)
            if isinstance(codes, list) and len(codes) > 0:
                return [c for c in codes if c in ALL_SCRIPTS]
        except Exception:
            pass
    return list(ALL_SCRIPTS.keys())

def set_enabled_scripts(codes_list):
    import json
    valid = [c for c in codes_list if c in ALL_SCRIPTS]
    if not valid:
        valid = ["devanagari"]
    set_setting("enabled_scripts", json.dumps(valid))
    return valid

def is_script_enabled(code: str) -> bool:
    if not code:
        return False
    c_lower = code.lower()
    enabled = get_enabled_scripts()
    return c_lower in enabled

def get_default_script():
    def_script = get_setting("default_script", "devanagari")
    enabled = get_enabled_scripts()
    if def_script in enabled:
        return def_script
    return enabled[0] if enabled else "devanagari"

def set_default_script(code: str):
    if not code:
        return get_default_script()
    c_lower = code.lower()
    enabled = get_enabled_scripts()
    if c_lower in enabled:
        set_setting("default_script", c_lower)
    return get_default_script()

def create_access_code(code: str, daily_max_minutes: float = 100.0, allow_ai_clean: int = 1, allow_ai_assist: int = 1):
    daily_max_seconds = daily_max_minutes * 60.0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO access_codes (code, daily_max_seconds, daily_used_seconds, status, allow_ai_clean, allow_ai_assist)
        VALUES (?, ?, 0.0, 'active', ?, ?)
        ON CONFLICT(code) DO UPDATE SET
            daily_max_seconds = excluded.daily_max_seconds,
            status = 'active';
    """, (code.strip().upper(), daily_max_seconds, int(allow_ai_clean), int(allow_ai_assist)))
    conn.commit()
    conn.close()
    return get_access_code(code)

def get_access_code(code: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM access_codes WHERE code = ?", (code.strip().upper(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def list_access_codes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM access_codes ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def revoke_access_code(code: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE access_codes SET status = 'revoked' WHERE code = ?", (code.strip().upper(),))
    conn.commit()
    conn.close()

def update_access_code_limit(code: str, daily_max_minutes: float):
    daily_max_seconds = daily_max_minutes * 60.0
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE access_codes SET daily_max_seconds = ? WHERE code = ?", (daily_max_seconds, code.strip().upper()))
    conn.commit()
    conn.close()
    return get_access_code(code)

def update_access_code_permissions(code: str, allow_ai_clean: int = None, allow_ai_assist: int = None):
    code_clean = code.strip().upper()
    conn = get_connection()
    cursor = conn.cursor()
    if allow_ai_clean is not None:
        cursor.execute("UPDATE access_codes SET allow_ai_clean = ? WHERE code = ?", (int(allow_ai_clean), code_clean))
        cursor.execute("UPDATE users SET allow_ai_clean = ? WHERE access_code = ?", (int(allow_ai_clean), code_clean))
    if allow_ai_assist is not None:
        cursor.execute("UPDATE access_codes SET allow_ai_assist = ? WHERE code = ?", (int(allow_ai_assist), code_clean))
        cursor.execute("UPDATE users SET allow_ai_assist = ? WHERE access_code = ?", (int(allow_ai_assist), code_clean))
    conn.commit()
    conn.close()
    return get_access_code(code_clean)

def list_unified_users_and_codes():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            ac.code,
            ac.daily_max_seconds,
            ac.daily_used_seconds,
            ac.total_used_seconds AS code_total_used_seconds,
            ac.request_count AS code_request_count,
            ac.status,
            ac.allow_ai_clean,
            ac.allow_ai_assist,
            ac.created_at,
            u.telegram_id,
            u.username,
            u.first_name,
            u.preferred_language,
            u.preferred_script,
            u.allow_ai_clean AS user_allow_ai_clean,
            u.allow_ai_assist AS user_allow_ai_assist,
            u.total_used_seconds AS user_total_used_seconds,
            u.request_count AS user_request_count,
            u.logged_in_at
        FROM access_codes ac
        LEFT JOIN users u ON ac.code = u.access_code
        ORDER BY ac.created_at DESC, u.logged_in_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def is_admin(telegram_id: int) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM admins WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row)

def add_admin(telegram_id: int, username: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO admins (telegram_id, username)
        VALUES (?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET username = excluded.username;
    """, (telegram_id, username))
    conn.commit()
    conn.close()

def register_user(telegram_id: int, username: str, first_name: str, access_code: str):
    code_obj = get_access_code(access_code)
    allow_clean = code_obj.get('allow_ai_clean', 1) if code_obj else 1
    allow_assist = code_obj.get('allow_ai_assist', 1) if code_obj else 1

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (telegram_id, username, first_name, access_code, allow_ai_clean, allow_ai_assist, daily_used_seconds, total_used_seconds, request_count)
        VALUES (?, ?, ?, ?, ?, ?, 0.0, 0.0, 0)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            access_code = excluded.access_code,
            allow_ai_clean = excluded.allow_ai_clean,
            allow_ai_assist = excluded.allow_ai_assist;
    """, (telegram_id, username or "", first_name or "", access_code.strip().upper(), allow_clean, allow_assist))
    conn.commit()
    conn.close()

def get_user(telegram_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def list_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY logged_in_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_user_language(telegram_id: int, lang_code: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET preferred_language = ? WHERE telegram_id = ?", (lang_code, telegram_id))
    conn.commit()
    conn.close()

def check_user_access(telegram_id: int):
    user = get_user(telegram_id)
    if not user:
        return False, "Not registered. Send /start or enter a valid access code."
    
    code = get_access_code(user['access_code'])
    if not code or code['status'] != 'active':
        return False, "Your access code is inactive or revoked. Please contact admin."
    
    today = datetime.now().strftime("%Y-%m-%d")
    if code['last_used_date'] != today:
        # Reset daily counters
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE access_codes SET daily_used_seconds = 0.0, last_used_date = ? WHERE code = ?", (today, code['code']))
        cursor.execute("UPDATE users SET daily_used_seconds = 0.0 WHERE telegram_id = ?", (telegram_id,))
        conn.commit()
        conn.close()
        code['daily_used_seconds'] = 0.0
    
    if code['daily_used_seconds'] >= code['daily_max_seconds']:
        return False, f"Daily audio limit reached ({math.ceil(code['daily_max_seconds'] / 60)} mins). Try again tomorrow."

    return True, "Access granted"

def update_usage(telegram_id: int, duration_sec: float):
    user = get_user(telegram_id)
    if not user:
        return
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Update user stats
    cursor.execute("""
        UPDATE users SET
            daily_used_seconds = daily_used_seconds + ?,
            total_used_seconds = total_used_seconds + ?,
            request_count = request_count + 1
        WHERE telegram_id = ?
    """, (duration_sec, duration_sec, telegram_id))
    
    # Update code stats
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        UPDATE access_codes SET
            daily_used_seconds = daily_used_seconds + ?,
            total_used_seconds = total_used_seconds + ?,
            request_count = request_count + 1,
            last_used_date = ?
        WHERE code = ?
    """, (duration_sec, duration_sec, today, user['access_code']))
    
    conn.commit()
    conn.close()

def log_transcription(telegram_id: int, access_code: str, language: str, duration_sec: float, char_count: int, snippet: str = "", full_transcript: str = "", audio_filename: str = "") -> int:
    # AUD2-01: Verbatim speech transcripts redacted for user privacy (Zero Surveillance)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO transcription_logs (telegram_id, access_code, language, duration_sec, char_count, transcript_snippet, full_transcript, audio_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (telegram_id, access_code, language, duration_sec, char_count, "[REDACTED FOR PRIVACY]", "[REDACTED FOR PRIVACY]", ""))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_recent_logs(limit: int = 50, offset: int = 0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcription_logs ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, max(0, offset)))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_total_logs_count() -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transcription_logs")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0

def get_team_usage_report():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY total_used_seconds DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_user_script(telegram_id: int, script_code: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET preferred_script = ? WHERE telegram_id = ?", (script_code.lower(), telegram_id))
    conn.commit()
    conn.close()

def get_user_transcription_history(telegram_id: int, limit: int = 50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcription_logs WHERE telegram_id = ? ORDER BY timestamp DESC LIMIT ?", (telegram_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_transcription_log_by_id(log_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transcription_logs WHERE id = ?", (log_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_cleaned_transcript(log_id: int, cleaned_text: str):
    # AUD2-01: Verbatim speech transcripts redacted for user privacy (Zero Surveillance)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE transcription_logs SET cleaned_transcript = ? WHERE id = ?", ("[REDACTED FOR PRIVACY]", log_id))
    conn.commit()
    conn.close()

def update_assisted_transcript(log_id: int, assisted_text: str):
    # AUD2-01: Verbatim speech transcripts redacted for user privacy (Zero Surveillance)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE transcription_logs SET assisted_transcript = ? WHERE id = ?", ("[REDACTED FOR PRIVACY]", log_id))
    conn.commit()
    conn.close()

# Initialize database tables on import
init_db()

