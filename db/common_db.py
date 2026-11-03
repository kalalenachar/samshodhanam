"""
Sanskrit Digital Library - Common Database Module

SQLite database for public user accounts, favourites, booklists, tokens, OTPs, and admins.
"""

import sqlite3
import os
import bcrypt
import base64
import hashlib
import secrets
from datetime import datetime
import json as _json
from cryptography.fernet import Fernet

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'common.db')


# =============================================================================
# DATA ENCRYPTION & HASHING HELPERS (SECURITY & PRIVACY HARDENING)
# =============================================================================

def _get_encryption_cipher():
    """Derive a deterministic 32-byte Fernet key from SECRET_KEY for at-rest encryption."""
    secret = os.environ.get('SECRET_KEY', '')
    if not secret:
        try:
            import config
            secret = getattr(config, 'SECRET_KEY', '')
        except Exception:
            pass
    if not secret:
        secret = 'samsho-default-db-encryption-key-2026'
    key_32 = hashlib.sha256(secret.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(key_32)
    return Fernet(fernet_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt a sensitive string (PII/API keys) before storing in SQLite."""
    if not plain_text:
        return plain_text
    try:
        cipher = _get_encryption_cipher()
        return "enc:" + cipher.encrypt(str(plain_text).encode('utf-8')).decode('utf-8')
    except Exception as e:
        print(f"Error encrypting secret: {e}")
        return plain_text


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt a sensitive string from SQLite. Seamlessly returns plain text for legacy rows."""
    if not cipher_text or not isinstance(cipher_text, str):
        return cipher_text
    if cipher_text.startswith("enc:"):
        try:
            cipher = _get_encryption_cipher()
            return cipher.decrypt(cipher_text[4:].encode('utf-8')).decode('utf-8')
        except Exception as e:
            print(f"Error decrypting secret: {e}")
            return ""
    return cipher_text


def hash_token(token: str) -> str:
    """Cryptographically hash a bearer token using SHA-256 for secure database storage."""
    if not token:
        return ""
    return hashlib.sha256(str(token).strip().encode('utf-8')).hexdigest()


def hash_otp(email: str, otp: str) -> str:
    """Cryptographically hash an OTP bound to email using SHA-256 for secure storage."""
    if not otp:
        return ""
    clean_email = str(email).strip().lower()
    clean_otp = str(otp).strip()
    return hashlib.sha256(f"{clean_email}:{clean_otp}".encode('utf-8')).hexdigest()


# =============================================================================
# SHARED UTILITY HELPERS
# =============================================================================

def normalize_model_name(model_name):
    """Normalize a Gemini model name to the canonical 'models/...' or 'tunedModels/...' format.

    Bug #14 fix: this logic was copy-pasted in 6+ places across sdl.py. Now centralised here.
    """
    if not model_name:
        return model_name
    model_name = model_name.strip().strip('/').strip()
    model_name = model_name.replace('\\', '/')
    while '//' in model_name:
        model_name = model_name.replace('//', '/')
    lower = model_name.lower()
    if lower.startswith('models/'):
        return f"models/{model_name[7:]}"
    elif lower.startswith('tunedmodels/'):
        return f"tunedModels/{model_name[12:]}"
    else:
        return f"models/{model_name}"


def get_any_admin_gemini_key():
    """Return the first non-empty Gemini API key from any admin record, or None."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT gemini_api_key FROM admins WHERE gemini_api_key IS NOT NULL AND gemini_api_key != "" LIMIT 1'
        ).fetchone()
        if row and row['gemini_api_key']:
            return decrypt_secret(row['gemini_api_key'])
        return None
    except Exception as e:
        print(f"Error querying fallback admin gemini key: {e}")
        return None
    finally:
        conn.close()


def _create_tables(conn):
    """Internal helper to create all tables and indexes in the provided connection."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            mobile TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT,
            avatar_idx INTEGER DEFAULT 0,
            profile_pic TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS favourites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_name TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_name)
        );

        CREATE TABLE IF NOT EXISTS booklists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS booklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booklist_id INTEGER NOT NULL,
            book_name TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (booklist_id) REFERENCES booklists(id) ON DELETE CASCADE,
            UNIQUE(booklist_id, book_name)
        );

        CREATE INDEX IF NOT EXISTS idx_favourites_user ON favourites(user_id);
        CREATE INDEX IF NOT EXISTS idx_booklists_user ON booklists(user_id);
        CREATE INDEX IF NOT EXISTS idx_booklist_items_list ON booklist_items(booklist_id);

        CREATE TABLE IF NOT EXISTS user_tokens (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_otps (
            email TEXT PRIMARY KEY,
            otp TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id);

        CREATE TABLE IF NOT EXISTS admins (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            permissions_json TEXT DEFAULT '[]',
            created_at TIMESTAMP,
            last_login TIMESTAMP,
            gemini_api_key TEXT DEFAULT NULL,
            gemini_model TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS sambhashana_modes (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            label TEXT,
            icon TEXT,
            system_prompt TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            gemini_model TEXT DEFAULT NULL,
            suggestions TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );


        CREATE TABLE IF NOT EXISTS user_ai_overrides (
            user_id INTEGER PRIMARY KEY,
            vyakhya_access TEXT DEFAULT 'default',
            sambhashana_access TEXT DEFAULT 'default',
            semantic_search_access TEXT DEFAULT 'default',
            history_limit_override INTEGER DEFAULT NULL,
            use_fallback_allowed TEXT DEFAULT 'default',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS user_ai_usage (
            user_id INTEGER NOT NULL,
            feature TEXT NOT NULL CHECK(feature IN ('vyakhya', 'sambhashana', 'semantic_search')),
            total_calls INTEGER DEFAULT 0,
            total_errors INTEGER DEFAULT 0,
            last_used_at TIMESTAMP DEFAULT NULL,
            PRIMARY KEY (user_id, feature),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS vector_download_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            book_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')),
            decryption_key TEXT NOT NULL,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            approved_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_name)
        );

        CREATE TABLE IF NOT EXISTS community_book_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edit_id TEXT UNIQUE NOT NULL,
            book_name TEXT NOT NULL,
            page_number INTEGER NOT NULL,
            client_token TEXT NOT NULL,
            contributor_name TEXT DEFAULT '',
            contributor_email TEXT DEFAULT '',
            original_text TEXT DEFAULT '',
            edited_text TEXT NOT NULL,
            edit_notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP DEFAULT NULL,
            reviewed_by TEXT DEFAULT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_edits_book_page ON community_book_edits(book_name, page_number);
        CREATE INDEX IF NOT EXISTS idx_edits_client ON community_book_edits(client_token);
        CREATE INDEX IF NOT EXISTS idx_edits_status ON community_book_edits(status);

        CREATE TABLE IF NOT EXISTS lekha_proofreading_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            user_id INTEGER DEFAULT NULL,
            user_name TEXT DEFAULT '',
            user_email TEXT NOT NULL,
            user_phone TEXT NOT NULL,
            submission_type TEXT NOT NULL CHECK(submission_type IN ('text', 'pdf')),
            title TEXT NOT NULL,
            content_text TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            file_name TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'rejected')),
            admin_notes TEXT DEFAULT '',
            proofread_result_text TEXT DEFAULT '',
            result_file_path TEXT DEFAULT '',
            result_file_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NULL,
            completed_at TIMESTAMP DEFAULT NULL,
            completed_by TEXT DEFAULT NULL,
            wants_vector_data INTEGER DEFAULT 0,
            embedding_model TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_lekha_req_id ON lekha_proofreading_requests(request_id);
        CREATE INDEX IF NOT EXISTS idx_lekha_status ON lekha_proofreading_requests(status);
        CREATE INDEX IF NOT EXISTS idx_lekha_email ON lekha_proofreading_requests(user_email);
        CREATE INDEX IF NOT EXISTS idx_lekha_created ON lekha_proofreading_requests(created_at);
    ''')
    conn.commit()

    # Migrate lekha_proofreading_requests table for vector preferences
    try:
        cursor = conn.execute("PRAGMA table_info(lekha_proofreading_requests)")
        lpr_cols = [row[1] for row in cursor.fetchall()]
        lpr_mod = False
        if 'wants_vector_data' not in lpr_cols:
            conn.execute("ALTER TABLE lekha_proofreading_requests ADD COLUMN wants_vector_data INTEGER DEFAULT 0")
            lpr_mod = True
        if 'embedding_model' not in lpr_cols:
            conn.execute("ALTER TABLE lekha_proofreading_requests ADD COLUMN embedding_model TEXT DEFAULT ''")
            lpr_mod = True
        if lpr_mod:
            conn.commit()
    except Exception as e:
        print(f"Error migrating lekha_proofreading_requests table: {e}")

    # Check if avatar_idx, profile_pic, and gemini_api_key columns exist in users table (migration for existing db)
    try:
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        modified = False
        if 'avatar_idx' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN avatar_idx INTEGER DEFAULT 0")
            modified = True
        if 'profile_pic' not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT DEFAULT NULL")
            modified = True
        if modified:
            conn.commit()
            print("Successfully migrated user database columns.")
    except Exception as e:
        print(f"Migration error: {e}")

    # Migrate admins table — add gemini columns if not present
    try:
        cursor = conn.execute("PRAGMA table_info(admins)")
        admin_cols = [row[1] for row in cursor.fetchall()]
        admin_modified = False
        if 'gemini_api_key' not in admin_cols:
            conn.execute("ALTER TABLE admins ADD COLUMN gemini_api_key TEXT DEFAULT NULL")
            admin_modified = True
        if 'gemini_model' not in admin_cols:
            conn.execute("ALTER TABLE admins ADD COLUMN gemini_model TEXT DEFAULT NULL")
            admin_modified = True
        if admin_modified:
            conn.commit()
            print("Successfully migrated admin database columns (gemini).")
    except Exception as e:
        print(f"Admin migration error: {e}")

    # Migrate sambhashana_modes table - add gemini_model column if not present
    try:
        cursor = conn.execute("PRAGMA table_info(sambhashana_modes)")
        sm_cols = [row[1] for row in cursor.fetchall()]
        if 'gemini_model' not in sm_cols:
            conn.execute("ALTER TABLE sambhashana_modes ADD COLUMN gemini_model TEXT DEFAULT NULL")
            conn.execute("UPDATE sambhashana_modes SET gemini_model = 'models/gemini-3.5-flash' WHERE gemini_model IS NULL")
            conn.commit()
            print("Successfully migrated sambhashana_modes database columns (gemini_model).")
        
        # Migrate sambhashana_modes table - add suggestions column if not present
        if 'suggestions' not in sm_cols:
            conn.execute("ALTER TABLE sambhashana_modes ADD COLUMN suggestions TEXT DEFAULT NULL")
            conn.commit()
            print("Successfully migrated sambhashana_modes database columns (suggestions).")
            
            # Populate existing modes with empty string if currently NULL
            conn.execute("UPDATE sambhashana_modes SET suggestions = '' WHERE suggestions IS NULL")
            conn.commit()
            print("Successfully populated default suggestions for existing modes.")
    except Exception as e:
        print(f"Sambhashana modes migration error: {e}")

    # Seed default Sambhashana AI modes if table is empty
    try:
        cursor = conn.execute("SELECT COUNT(*) FROM sambhashana_modes")
        if cursor.fetchone()[0] == 0:
            default_modes = [
                ('guru', 'गुरु-शैली', 'गुरुः', '🧘', 
                 'भवान् एकः प्राचीनः गुरुः अस्ति। भवान् गम्भीरया शैल्या, प्रामाणिकरूपेण, शास्त्रीयपद्धत्या च उत्तरं ददाति। यथा एकः आचार्यः शिष्यं बोधयति तथा भवान् वदतु। गम्भीरतया, विद्वत्तया च संवदतु।', 1, 10, 'models/gemini-3.5-flash',
                 ''),
                ('mitra', 'मित्र-शैली', 'मित्रम्', '🤝', 
                 'भवान् एकः सुहृत् अस्ति। मित्रवत् सरलतया, स्नेहेन, उत्साहेन च संवदतु। प्रोत्साहनं ददातु। सरलं संस्कृतं प्रयोजयतु। मित्रभावेन प्रतिवदतु।', 1, 20, 'models/gemini-3.5-flash',
                 ''),
                ('shishu', 'शिशु-शैली', 'शिशुः', '🌱', 
                 'भवान् बालानां कृते सरलतमं संस्कृतं वदति। अतिसरलैः वाक्यैः, लघुपदैः च वदतु। धैर्येण, कोमलतया च बोधयतु। कठिनशब्दान् परिहरतु। सरलतमं संस्कृतं प्रयोजयतु।', 1, 30, 'models/gemini-3.5-flash',
                 ''),
                ('kavi', 'कवि-शैली', 'कविः', '📜', 
                 'भवान् एकः काव्यप्रियः कविः अस्ति। श्लोकशैल्या, काव्यात्मकपद्धत्या, अलङ्कारयुक्तया भाषया च उत्तरं ददातु। यत्र सम्भवं तत्र श्लोकरूपेण वदतु। रसयुक्तं, सुललितं, काव्यात्मकं च भवतु उत्तरम्।', 1, 40, 'models/gemini-3.5-flash',
                 ''),
                ('tarkika', 'तार्किक-शैली', 'तार्किकः', '⚖️', 
                 'भवान् एकः न्यायशास्त्रज्ञः तार्किकः अस्ति। तर्कपूर्वकं, न्यायशास्त्रीयपद्धत्या, हेतुयुक्तं च उत्तरं ददातु। पक्षं, हेतुं, दृष्टान्तं च प्रदर्शयतु। वादशैल्या संवदतु।', 1, 50, 'models/gemini-3.5-flash',
                 ''),
                ('vyakarana', 'व्याकरण-शैली', 'व्याकरणम्', '📖', 
                 'भवान् एकः पाणिनीयव्याकरणविशेषज्ञः अस्ति। शब्दानां व्युत्पत्तिं, सन्धिविच्छेदं, विभक्तिविश्लेषणं, धातुरूपाणि, समासविग्रहं च विशदयतु। व्याकरणदृष्ट्या सर्वं विश्लेषयतु।', 1, 60, 'models/gemini-3.5-flash',
                 ''),
            ]
            conn.executemany(
                'INSERT INTO sambhashana_modes (key, name, label, icon, system_prompt, is_active, sort_order, gemini_model, suggestions) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                default_modes
            )
            conn.commit()
            print("Successfully seeded default Sambhashana AI modes.")
    except Exception as e:
        print(f"Error seeding Sambhashana AI modes: {e}")

    # Seed default system settings if table is empty or settings missing
    try:
        default_vyakhya_prompt = (
            "You are a knowledgeable assistant for the Sanskrit Digital Library (Samshodhana Mandiram). "
            "You have deep expertise in Sanskrit language, Indian philosophy, Vedic literature, and classical Indian texts.\n\n"
            "Guidelines:\n"
            "1. Base your response strictly on the provided Target Text and Surrounding Context. Do not fabricate information.\n"
            "2. Apply the USER REQUEST directly and specifically to the TARGET TEXT TO PROCESS. The result/answer must be based on processing, translating, explaining, or analyzing this TARGET TEXT.\n"
            "3. The SURROUNDING CONTEXT (including the book metadata, previous page, next page, and the full text of the matching page) is provided ONLY to help you understand the context, background, flow of thoughts, or terminology of the Target Text. Do NOT use content from the surrounding context pages to directly answer the user request or generate results, unless it provides crucial context required to understand the Target Text.\n"
            "4. If the text is in Sanskrit or contains Sanskrit terms, handle them with scholarly care:\n"
            "   - Use standard IAST transliteration or Devanagari for Sanskrit terms when helpful\n"
            "   - Explain technical terms (e.g. dharma, karma, saṃskāra) when they appear\n"
            "5. Structure your response clearly with logical flow. Use line breaks between paragraphs.\n"
            "6. Keep the tone scholarly yet accessible. Be concise but thorough."
        )
        default_quiz_prompt = (
            "You are a knowledgeable assistant for the Sanskrit Digital Library (Samshodhana Mandiram). "
            "You have deep expertise in Sanskrit language, Indian philosophy, Vedic literature, and classical Indian texts."
        )
        default_settings = [
            ('vyakhya_model', 'models/gemini-3.5-flash'),
            ('vyakhya_prompt', default_vyakhya_prompt),
            ('sdl_vyakhya_model', 'models/gemini-3.5-flash'),
            ('sdl_vyakhya_prompt', default_vyakhya_prompt),
            ('quiz_vyakhya_model', 'models/gemini-3.5-flash'),
            ('quiz_vyakhya_prompt', default_quiz_prompt),
            ('gemini_cooldown_minutes', '60'),
            ('kavi_model', 'gemini-3.5-flash'),
            ('kavi_temperature', '0.7'),
            ('kavi_max_tokens', '2048'),
            ('kavi_system_prompt', "You are Kavi AI, a masterful Sanskrit poet and expert grammarian. You specialize in composing flawless Sanskrit verses (Shlokas) adhering to Paninian grammar and Pingala's prosody (Chandas). When analyzing, you break down sentences into deep Navya-Nyaya and Vyakarana structures.\n\nCRITICAL INSTRUCTIONS:\n- If specific section dividers are requested in the prompt, you must ONLY output those sections separated by the specified dividers.\n- Do NOT include any conversational preamble, greetings (like \"अहो प्रयोक्तः...\"), postscript, commentaries, notes, or explanations outside the requested sections.\n- Start your response directly with the requested output format without any introductory sentences.\n- Ensure the output strictly conforms to the requested layout under all circumstances.\n- NEVER prepend a mangalacharana, invocation shloka, or any introductory verse (like 'वागर्थाविव सम्पृक्तौ...' or any other verse) before your answer. Do not add any verse that was not explicitly requested by the user."),
            ('kavi_creator_prompt', "विषयः (Theme): [USER_TOPIC]\nछन्दः (Metrical Meter): [METER]\nरसः (Sentiment): [RASA]\nकाठिन्य-स्तरः (Complexity): [COMPLEXITY]\n\nनिर्देशाः (Instructions):\n१. संस्कृतभाषायाम् एव श्लोकरचनां करोतु। (Compose verses strictly in Sanskrit language).\n२. श्लोकस्य पदच्छेदं करोतु। (Provide word separation / padaccheda).\n३. श्लोकस्य अर्थं/भावार्थं च संस्कृतेन आङ्ग्लभाषया वा लिखतु। (Provide meaning in simple Sanskrit or English translation)."),
            ('kavi_analyzer_prompt', "अधोदत्तस्य श्लोकस्य सम्पूर्णं पाणिनीय-व्याकरण-छन्द-साहित्य-विश्लेषणं करोतु (Analyze the following shloka completely):\n[USER_SHLOKA]\n\nअत्यन्तं महत्त्वपूर्णः निर्देशः (CRITICAL FORMATTING INSTRUCTION):\nभवतः प्रतिवचनं निम्नलिखितचिह्नकविभागेषु एव विभाज्य लिखतु (You MUST output your response precisely split by these markdown dividers):\n\n---काव्यम्---\n[श्लोकः अत्र लिखतु (Rewrite the shloka clearly)]\n---पदच्छेदः---\n[पदच्छेदः अत्र लिखतु]\n---सन्धि-विग्रहः---\n[सन्धि-विग्रहः]\n---समास-विग्रहः---\n[समास-विग्रहः]\n---शब्दरूप-विश्लेषणम्---\n[शब्दानां लिङ्ग-विभक्ति-वचनानि]\n---धातुरूप-विश्लेषणम्---\n[धातूनां लकार-पुरुष-वचनानि]\n---व्याकरण-विशेषाः---\n[पाणिनीयसूत्राणि तद्धित-कृदन्तादयः च]\n---कोश-सन्दर्भः---\n[अमरकोशादि-प्रमाणानि]\n---आकाङ्क्षा-योग्यता-सन्निधि---\n[शाब्दबोध-प्रक्रिया]\n---अन्वयः---\n[अन्वयः अत्र लिखतु]\n---भावार्थः---\n[भावार्थः अत्र लिखतु]\n---छन्दः---\n[छन्दसः नाम लक्षणं च]\n---अलङ्कारः---\n[अलङ्कारः]\n---रसः---\n[रसः]\n---काव्य-गुण-दोषः---\n[काव्यशास्त्रीय-परीक्षा]"),
            ('kavi_brainstorm_prompt', "You are Kavi AI, a master Sanskrit poet. We need to write a Shloka.\nविषयः (Theme): [USER_TOPIC]\nरसः (Sentiment): [RASA]\n\nBRAINSTORMING TASK:\nList 5 to 10 Sanskrit vocabulary words, synonyms, and metaphors that fit this theme and rasa perfectly. Be highly creative. Do NOT write the shloka yet.\n"),
            ('kavi_brainstorm_temp', '0.9'),
            ('kavi_draft_prompt', "You are Kavi AI. Using the following brainstorming concepts, draft a Shloka.\nविषयः (Theme): [USER_TOPIC]\nछन्दः (Metrical Meter): [METER]\nकाठिन्य-स्तरः (Complexity): [COMPLEXITY]\n\n[BRAINSTORM_RESULTS]\n\nDRAFTING TASK:\nDraft the Shloka strictly in Sanskrit. Try your best to adhere to the meter rules.\n"),
            ('kavi_draft_temp', '0.7'),
            ('kavi_critic_prompt', "You are a strict Paninian Grammarian and Pingala Prosody Expert.\nReview the following draft Shloka:\n\n[DRAFT_RESULTS]\n\nCRITIC TASK:\n1. Count the syllables and verify the Laghu/Guru pattern for the meter: [METER]\n2. Fix any Sandhi or Vyakarana errors.\n3. Output the FINAL flawless Shloka, followed by its Padaccheda and Meaning.\n\nअत्यन्तं महत्त्वपूर्णः निर्देशः (CRITICAL FORMATTING INSTRUCTION):\nभवतः प्रतिवचनं निम्नलिखितचिह्नकविभागेषु एव विभाज्य लिखतु:\n\n---काव्यम्---\n[श्लोकः अत्र लिखतु]\n---पदच्छेदः---\n[पदच्छेदः अत्र लिखतु]\n---भावार्थः---\n[भावार्थः अत्र लिखतु]\n"),
            ('kavi_critic_temp', '0.1'),
            ('kavi_meters', '[{"label": "Free Style / अनियमितम्", "value": "अनियमितम् (Free Style)"}, {"label": "Anushtubh / अनुष्टुभ्", "value": "अनुष्टुभ् (Anushtubh - 8 syllables/line)"}, {"label": "Indravajra / इन्द्रवज्रा", "value": "इन्द्रवज्रा (Indravajra - 11 syllables/line)"}, {"label": "Vasantatilaka / वसन्ततिलका", "value": "वसन्ततिलका (Vasantatilaka - 14 syllables/line)"}, {"label": "Shardulavikridita / शार्दूलविक्रीडितम्", "value": "शार्दूलविक्रीडितम् (Shardulavikridita - 19 syllables)"}, {"label": "Mandakranta / मन्दाक्रान्ता", "value": "मन्दाक्रान्ता (Mandakranta - 17 syllables)"}, {"label": "Upajati / उपजाति", "value": "उपजाति (Upajati - 11 syllables)"}]'),
            ('kavi_sentiments', '[{"label": "Any Sentiment / अनियतः", "value": "अनियतः (Any)"}, {"label": "Shringara (Love) / शृङ्गारः", "value": "शृङ्गारः (Love/Beauty)"}, {"label": "Veera (Heroic) / वीरः", "value": "वीरः (Heroic)"}, {"label": "Karuna (Compassion) / करुणः", "value": "करुणः (Compassion/Sadness)"}, {"label": "Shanta (Peace) / शान्तः", "value": "शान्तः (Peace)"}, {"label": "Hasya (Humor) / हास्यः", "value": "हास्यः (Humorous)"}, {"label": "Adbhuta (Wonder) / अद्भुतः", "value": "अद्भुतः (Wonder)"}]'),
            ('kavi_complexities', '[{"label": "सरलः", "value": "सरलः (Simple)"}, {"label": "मध्यमः", "value": "मध्यमः (Medium)"}, {"label": "प्रौढः", "value": "प्रौढः (Ornate)"}]'),
            ('lekha_shodhaka_model', 'models/gemini-3.5-flash'),
            ('lekha_shodhaka_chunker_model', 'models/gemini-3.5-flash'),
            ('lekha_shodhaka_threshold', '3000'),
            ('lekha_shodhaka_temperature', '0.1'),
            ('lekha_shodhaka_system_prompt', 'You are an expert Sanskrit grammarian (Paninian scholar) and proofreader.\nYour task is to analyze the provided Sanskrit text and output the refined version free of grammatical mistakes (Vyakarana Dosha), OCR/printing errors, spelling mistakes, and formatting errors.\n\nContext of this segment (if available for continuity):\n[CHUNK_CONTEXT]\n\nInstructions:\n1. Critically analyze the text and generate a refined, grammatically correct version.\n2. Identify every single correction.\n3. Classify each correction into one of these categories: [OCR / Printing Error, Grammatical Error, Spelling Mistake, Other].\n4. Output:\n   - Relative line number (1-based, relative to this chunk).\n   - Original segment.\n   - Corrected segment.\n   - Classification.\n   - A short, concise explanation of the grammatical error (e.g. mentioning Sandhi, Karaka, or Samasa rules).\n   - If the change is a minor invisible character modification, formatting, or simple OCR correction, output "N/A" for the explanation.\n\nReturn your response strictly in the following JSON format:\n{\n  "refined_text": "Complete corrected Sanskrit text...",\n  "corrections": [\n    {\n      "line_number": 3,\n      "original": "गच्छति स्मः",\n      "corrected": "गच्छति",\n      "type": "Grammatical Error",\n      "explanation": "Verb agreement mismatch (should be singular for singular subject)."\n    }\n  ]\n}'),
            ('lekha_shodhaka_chunker_prompt', 'You are a Sanskrit Grantha Segmentation Agent. Your job is to divide a long Sanskrit text into logically cohesive chunks (such as paragraphs, chapters, or groups of verses) without skipping or losing any characters.\n\nInstructions:\n1. Divide the text into contiguous chunks based on the natural structure of the Grantha (e.g. at double danda "||" or paragraph endings).\n2. Each chunk should ideally be around 1500 to 2500 characters.\n3. For each chunk, provide a brief \'context\' summary describing what is discussed in that segment so the subsequent proofreader understands the flow.\n\nReturn your response strictly in the following JSON format:\n{\n  "chunks": [\n    {\n      "index": 0,\n      "text": "Sanskrit text of chunk 0...",\n      "start_line": 1,\n      "end_line": 12,\n      "context": "Introductory invocation and setting context for the chapter"\n    }\n  ]\n}'),
            ('lekha_shodhaka_mistake_types', '["OCR / Printing Error", "Grammatical Error", "Spelling Mistake", "Other"]')
        ]
        conn.executemany(
            'INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)',
            default_settings
        )
        conn.commit()
        print("Successfully seeded default system, Kavi AI, and Lekha Shodhaka settings.")
    except Exception as e:
        print(f"Error seeding system settings: {e}")

    # Seed default role-based AI settings
    try:
        default_role_settings = [
            ('role_non_logged_in_vyakhya_access', 'allow'),
            ('role_non_logged_in_sambhashana_access', 'allow'),
            ('role_non_logged_in_sambhashana_history_limit', '1'),
            ('role_non_logged_in_semantic_search_access', 'allow'),
            ('role_non_logged_in_semantic_search_fallback_allowed', 'allow'),
            ('role_non_logged_in_use_fallback_allowed', 'allow'),
            ('role_logged_in_vyakhya_access', 'allow'),
            ('role_logged_in_sambhashana_access', 'allow'),
            ('role_logged_in_sambhashana_history_limit_fallback', '1'),
            ('role_logged_in_sambhashana_history_limit_own', '10'),
            ('role_logged_in_semantic_search_access', 'allow'),
            ('role_logged_in_semantic_search_fallback_allowed', 'allow'),
            ('role_logged_in_use_fallback_allowed', 'allow'),
            ('role_admin_vyakhya_access', 'allow'),
            ('role_admin_sambhashana_access', 'allow'),
            ('role_admin_sambhashana_history_limit_fallback', '1'),
            ('role_admin_sambhashana_history_limit_own', '10'),
            ('role_admin_semantic_search_access', 'allow'),
            ('role_admin_semantic_search_fallback_allowed', 'allow'),
            ('role_admin_use_fallback_allowed', 'allow')
        ]
        conn.executemany(
            'INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)',
            default_role_settings
        )
        conn.commit()
        print("Successfully seeded default role AI settings.")
    except Exception as e:
        print(f"Error seeding role AI settings: {e}")

    # Force enable semantic search and vyakhya access for non-logged-in/public users and fallback keys for regular users (migration for existing db)
    try:
        conn.execute("UPDATE system_settings SET value = 'allow' WHERE key = 'role_non_logged_in_semantic_search_access'")
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('role_non_logged_in_semantic_search_fallback_allowed', 'allow')")
        conn.execute("UPDATE system_settings SET value = 'allow' WHERE key = 'role_logged_in_semantic_search_fallback_allowed'")
        conn.execute("UPDATE system_settings SET value = 'allow' WHERE key = 'role_non_logged_in_vyakhya_access'")
        conn.commit()
        print("Successfully migrated system settings for AI search.")
    except Exception as e:
        print(f"System settings migration error: {e}")

    # Migrate Gemini models from 2.5-flash to 3.5-flash
    try:
        conn.execute("UPDATE system_settings SET value = 'models/gemini-3.5-flash' WHERE value = 'models/gemini-2.5-flash'")
        conn.execute("UPDATE system_settings SET value = 'gemini-3.5-flash' WHERE value = 'gemini-2.5-flash'")
        conn.execute("UPDATE sambhashana_modes SET gemini_model = 'models/gemini-3.5-flash' WHERE gemini_model = 'models/gemini-2.5-flash'")
        conn.commit()
        print("Successfully migrated Gemini models from 2.5-flash to 3.5-flash in DB.")
    except Exception as e:
        print(f"Gemini model migration error: {e}")


def get_db():
    """Get a database connection with row_factory for dict-like access. Auto-initializes tables if file is missing/empty."""
    db_exists = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    if not db_exists:
        try:
            _create_tables(conn)
            print(f"Common database auto-initialized at {DB_PATH}")
        except Exception as e:
            print(f"Error auto-initializing database tables: {e}")
            
    return conn


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    try:
        _create_tables(conn)
        print(f"Common database initialized at {DB_PATH}")
    finally:
        conn.close()


def _sanitize_user_dict(user):
    """Internal helper to decrypt PII and set profile_pic to None if the file doesn't exist on disk."""
    if not user:
        return None
    user_dict = dict(user)
    if 'mobile' in user_dict and user_dict['mobile']:
        user_dict['mobile'] = decrypt_secret(user_dict['mobile'])
    profile_pic = user_dict.get('profile_pic')
    if profile_pic:
        pic_dir = os.path.join(os.path.dirname(DB_PATH), '..', 'sdl_web', 'static', 'uploads', 'profile_pics')
        filepath = os.path.join(pic_dir, profile_pic)
        if not os.path.exists(filepath):
            user_dict['profile_pic'] = None
    return user_dict


# =============================================================================
# USER ACCOUNTS
# =============================================================================

def create_user(email, password, mobile, display_name=None):
    """Create a new user account with bcrypt password hashing and encrypted PII (mobile)."""
    email = email.strip().lower()
    mobile = mobile.strip()

    if not email or not password or not mobile:
        return False, "Email, password, and mobile number are required", None

    if len(password) < 8:
        return False, "Password must be at least 8 characters", None

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    enc_mobile = encrypt_secret(mobile)

    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO users (email, mobile, password_hash, display_name) VALUES (?, ?, ?, ?)',
            (email, enc_mobile, password_hash, display_name or email.split('@')[0])
        )
        conn.commit()
        return True, "Account created successfully", cursor.lastrowid
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists", None
    finally:
        conn.close()


def verify_user(email, password):
    """Verify user credentials. Returns user dict or None."""
    email = email.strip().lower()
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if row and bcrypt.checkpw(password.encode('utf-8'), row['password_hash'].encode('utf-8')):
            # Update last login
            conn.execute('UPDATE users SET last_login = ? WHERE id = ?',
                         (get_ist_now().isoformat(), row['id']))
            conn.commit()
            return _sanitize_user_dict(row)
        return None
    except Exception:
        return None
    finally:
        conn.close()


def get_or_create_google_user(email, display_name=None):
    """Get or create user for Google Sign-in. Returns user dict."""
    email = email.strip().lower()
    from time_utils import get_ist_now
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        if row:
            conn.execute('UPDATE users SET last_login = ? WHERE id = ?',
                         (get_ist_now().isoformat(), row['id']))
            conn.commit()
            return _sanitize_user_dict(row)
        
        # If user does not exist, create one with dummy password/mobile
        dummy_pass = os.urandom(24).hex()
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(dummy_pass.encode('utf-8'), salt).decode('utf-8')
        enc_mobile = encrypt_secret("Google User")
        
        cursor = conn.execute(
            'INSERT INTO users (email, mobile, password_hash, display_name) VALUES (?, ?, ?, ?)',
            (email, enc_mobile, password_hash, display_name or email.split('@')[0])
        )
        conn.commit()
        
        new_row = conn.execute('SELECT * FROM users WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return _sanitize_user_dict(new_row)
    except Exception as e:
        print(f"Error in get_or_create_google_user: {e}")
        return None
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Get user by ID. Returns user dict or None."""
    conn = get_db()
    try:
        row = conn.execute('SELECT id, email, mobile, display_name, created_at, last_login, avatar_idx, profile_pic FROM users WHERE id = ?',
                           (user_id,)).fetchone()
        return _sanitize_user_dict(row)
    finally:
        conn.close()


# =============================================================================
# FAVOURITES
# =============================================================================

def toggle_favourite(user_id, book_name):
    """Toggle a book as favourite. Returns {'is_favourite': bool}."""
    conn = get_db()
    try:
        existing = conn.execute(
            'SELECT id FROM favourites WHERE user_id = ? AND book_name = ?',
            (user_id, book_name)
        ).fetchone()

        if existing:
            conn.execute('DELETE FROM favourites WHERE id = ?', (existing['id'],))
            conn.commit()
            return {'is_favourite': False}
        else:
            conn.execute(
                'INSERT INTO favourites (user_id, book_name) VALUES (?, ?)',
                (user_id, book_name)
            )
            conn.commit()
            return {'is_favourite': True}
    finally:
        conn.close()


def get_favourites(user_id):
    """Get list of favourite book names for a user."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT book_name, added_at FROM favourites WHERE user_id = ? ORDER BY added_at DESC',
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def is_favourite(user_id, book_name):
    """Check if a book is favourited by a user."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT id FROM favourites WHERE user_id = ? AND book_name = ?',
            (user_id, book_name)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# =============================================================================
# BOOKLISTS
# =============================================================================

def create_booklist(user_id, name, description=''):
    """Create a new booklist. Returns booklist_id or None."""
    conn = get_db()
    try:
        cursor = conn.execute(
            'INSERT INTO booklists (user_id, name, description) VALUES (?, ?, ?)',
            (user_id, name.strip(), description.strip())
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        return None
    finally:
        conn.close()


def get_booklists(user_id):
    """Get all booklists for a user with book counts."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT b.id, b.name, b.description, b.created_at, b.updated_at,
                   COUNT(bi.id) as book_count
            FROM booklists b
            LEFT JOIN booklist_items bi ON b.id = bi.booklist_id
            WHERE b.user_id = ?
            GROUP BY b.id
            ORDER BY b.updated_at DESC
        ''', (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_booklist_detail(booklist_id, user_id):
    """Get a single booklist with its items. Returns None if not found or not owned."""
    conn = get_db()
    try:
        booklist = conn.execute(
            'SELECT * FROM booklists WHERE id = ? AND user_id = ?',
            (booklist_id, user_id)
        ).fetchone()
        if not booklist:
            return None

        items = conn.execute(
            'SELECT book_name, added_at FROM booklist_items WHERE booklist_id = ? ORDER BY sort_order, added_at',
            (booklist_id,)
        ).fetchall()

        result = dict(booklist)
        result['items'] = [dict(i) for i in items]
        return result
    finally:
        conn.close()


def add_to_booklist(booklist_id, book_name, user_id):
    """Add a book to a booklist. Returns (success, message)."""
    conn = get_db()
    try:
        # Verify ownership
        bl = conn.execute('SELECT id FROM booklists WHERE id = ? AND user_id = ?',
                          (booklist_id, user_id)).fetchone()
        if not bl:
            return False, "Booklist not found"

        conn.execute(
            'INSERT INTO booklist_items (booklist_id, book_name) VALUES (?, ?)',
            (booklist_id, book_name)
        )
        conn.execute('UPDATE booklists SET updated_at = ? WHERE id = ?',
                      (get_ist_now().isoformat(), booklist_id))
        conn.commit()
        return True, "Book added"
    except sqlite3.IntegrityError:
        return False, "Book already in this list"
    finally:
        conn.close()


def is_book_in_booklist(booklist_id, book_name):
    """Check if a book is in a booklist."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT id FROM booklist_items WHERE booklist_id = ? AND book_name = ?',
            (booklist_id, book_name)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def remove_from_booklist(booklist_id, book_name, user_id):
    """Remove a book from a booklist. Returns (success, message)."""
    conn = get_db()
    try:
        bl = conn.execute('SELECT id FROM booklists WHERE id = ? AND user_id = ?',
                          (booklist_id, user_id)).fetchone()
        if not bl:
            return False, "Booklist not found"

        conn.execute(
            'DELETE FROM booklist_items WHERE booklist_id = ? AND book_name = ?',
            (booklist_id, book_name)
        )
        conn.execute('UPDATE booklists SET updated_at = ? WHERE id = ?',
                      (get_ist_now().isoformat(), booklist_id))
        conn.commit()
        return True, "Book removed"
    finally:
        conn.close()


def delete_booklist(booklist_id, user_id):
    """Delete a booklist and all its items. Returns (success, message)."""
    conn = get_db()
    try:
        bl = conn.execute('SELECT id FROM booklists WHERE id = ? AND user_id = ?',
                          (booklist_id, user_id)).fetchone()
        if not bl:
            return False, "Booklist not found"

        conn.execute('DELETE FROM booklist_items WHERE booklist_id = ?', (booklist_id,))
        conn.execute('DELETE FROM booklists WHERE id = ?', (booklist_id,))
        conn.commit()
        return True, "Booklist deleted"
    finally:
        conn.close()


def rename_booklist(booklist_id, user_id, new_name, new_description=None):
    """Rename a booklist. Returns (success, message)."""
    conn = get_db()
    try:
        bl = conn.execute('SELECT id FROM booklists WHERE id = ? AND user_id = ?',
                          (booklist_id, user_id)).fetchone()
        if not bl:
            return False, "Booklist not found"

        if new_description is not None:
            conn.execute('UPDATE booklists SET name = ?, description = ?, updated_at = ? WHERE id = ?',
                          (new_name.strip(), new_description.strip(), get_ist_now().isoformat(), booklist_id))
        else:
            conn.execute('UPDATE booklists SET name = ?, updated_at = ? WHERE id = ?',
                          (new_name.strip(), get_ist_now().isoformat(), booklist_id))
        conn.commit()
        return True, "Booklist updated"
    finally:
        conn.close()



# =============================================================================
# ADMIN USER MANAGEMENT HELPERS
# =============================================================================

def get_all_users():
    """Get all registered public users with counts of favourites and custom booklists."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT u.id, u.email, u.mobile, u.display_name, u.created_at, u.last_login, u.avatar_idx, u.profile_pic,
                   (SELECT COUNT(*) FROM favourites f WHERE f.user_id = u.id) as fav_count,
                   (SELECT COUNT(*) FROM booklists b WHERE b.user_id = u.id) as list_count
            FROM users u
            ORDER BY u.created_at DESC
        ''').fetchall()
        return [_sanitize_user_dict(r) for r in rows]
    except Exception as e:
        print(f"Error in get_all_users: {e}")
        return []
    finally:
        conn.close()


def delete_user(user_id):
    """Permanently delete a user account. Cascades to favourites and booklists."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting user: {e}")
        return False
    finally:
        conn.close()


def reset_user_password(user_id, new_password):
    """Reset a user's password securely using bcrypt hashing."""
    if not new_password or len(new_password) < 8:
        return False, "Password must be at least 8 characters"
    
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    
    conn = get_db()
    try:
        conn.execute('UPDATE users SET password_hash = ? WHERE id = ?', (password_hash, user_id))
        conn.commit()
        return True, "Password reset successfully"
    except Exception as e:
        print(f"Error resetting password: {e}")
        return False, "Failed to update database"
    finally:
        conn.close()


def get_user_by_email(email):
    """Get user by email. Returns user dict or None."""
    email = email.strip().lower()
    conn = get_db()
    try:
        row = conn.execute('SELECT id, email, mobile, display_name, created_at, last_login, avatar_idx, profile_pic FROM users WHERE email = ?',
                           (email,)).fetchone()
        return _sanitize_user_dict(row)
    finally:
        conn.close()


def save_otp(email, otp):
    """Save a cryptographic SHA-256 hash of the OTP for an email address (never stores raw plaintext)."""
    email = email.strip().lower()
    hashed_otp = hash_otp(email, otp)
    conn = get_db()
    try:
        conn.execute(
            'INSERT OR REPLACE INTO user_otps (email, otp, created_at) VALUES (?, ?, ?)',
            (email, hashed_otp, get_ist_now().isoformat())
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving OTP: {e}")
        return False
    finally:
        conn.close()


def verify_otp(email, otp, max_age_seconds=600):
    """Verify if the OTP matches its stored hash and is within expiration limit. Deletes OTP on success."""
    email = email.strip().lower()
    raw_otp = otp.strip()
    hashed_otp = hash_otp(email, raw_otp)
    conn = get_db()
    try:
        row = conn.execute('SELECT otp, created_at FROM user_otps WHERE email = ?', (email,)).fetchone()
        if not row:
            return False
        
        # Verify against SHA-256 hash (or raw plaintext for backwards-compatibility during migration)
        if row['otp'] != hashed_otp and row['otp'] != raw_otp:
            return False
            
        # Check expiration
        try:
            created_at = datetime.fromisoformat(row['created_at'])
            age = (get_ist_now() - created_at).total_seconds()
            if age > max_age_seconds:
                # Expired, clean it up
                conn.execute('DELETE FROM user_otps WHERE email = ?', (email,))
                conn.commit()
                return False
        except Exception:
            return False
            
        # Valid, consume the OTP
        conn.execute('DELETE FROM user_otps WHERE email = ?', (email,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error verifying OTP: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# EXTERNAL APP TOKEN AUTH (CRYPTOGRAPHICALLY HASHED AT REST)
# =============================================================================

from time_utils import get_ist_now

def create_user_token(user_id):
    """Generate a secure random hex token and store its SHA-256 hash. Returns plaintext token to client."""
    token = secrets.token_hex(32)
    stored_hash = hash_token(token)
    conn = get_db()
    try:
        conn.execute('INSERT INTO user_tokens (token, user_id) VALUES (?, ?)', (stored_hash, user_id))
        conn.commit()
        return token
    except Exception as e:
        print(f"Error creating user token: {e}")
        return None
    finally:
        conn.close()


def verify_user_token(token):
    """Validate a token by checking its SHA-256 hash and return the corresponding user_id or None."""
    if not token:
        return None
    raw_token = token.strip()
    token_hashed = hash_token(raw_token)
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT user_id FROM user_tokens WHERE token = ? OR token = ?',
            (token_hashed, raw_token)
        ).fetchone()
        return row['user_id'] if row else None
    except Exception as e:
        print(f"Error verifying user token: {e}")
        return None
    finally:
        conn.close()


def delete_user_token(token):
    """Delete/revoke a user token by its hash. Returns True on success."""
    if not token:
        return False
    raw_token = token.strip()
    token_hashed = hash_token(raw_token)
    conn = get_db()
    try:
        conn.execute('DELETE FROM user_tokens WHERE token = ? OR token = ?', (token_hashed, raw_token))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting user token: {e}")
        return False
    finally:
        conn.close()


def update_user_avatar(user_id, avatar_idx):
    """Update a user's selected avatar index."""
    conn = get_db()
    try:
        conn.execute('UPDATE users SET avatar_idx = ? WHERE id = ?', (avatar_idx, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating user avatar: {e}")
        return False
    finally:
        conn.close()


def update_user_profile_pic(user_id, profile_pic_filename):
    """Update a user's uploaded profile picture filename."""
    conn = get_db()
    try:
        conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (profile_pic_filename, user_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating user profile pic: {e}")
        return False
    finally:
        conn.close()


def update_user_gemini_key(user_id, gemini_api_key, gemini_model=None):
    """Deprecated: User gemini keys are no longer stored in users table. Always returns True."""
    return True


# =============================================================================
# ADMIN MANAGEMENT
# =============================================================================

# Permission Constants
PERM_DOWNLOAD_BOOKS = 'PERM_DOWNLOAD_BOOKS'
PERM_UPLOAD_EXCEL = 'PERM_UPLOAD_EXCEL'
PERM_EDIT_BOOK_NAME = 'PERM_EDIT_BOOK_NAME'
PERM_EDIT_TAGS = 'PERM_EDIT_TAGS'
PERM_EDIT_SUB_BOOK = 'PERM_EDIT_SUB_BOOK'
PERM_EDIT_LINK = 'PERM_EDIT_LINK'
PERM_ADD_BOOK = 'PERM_ADD_BOOK'
PERM_DELETE_BOOK = 'PERM_DELETE_BOOK'
PERM_EDIT_OCR = 'PERM_EDIT_OCR'
PERM_VIEW_FEEDBACK = 'PERM_VIEW_FEEDBACK'
PERM_MANAGE_FEEDBACK = 'PERM_MANAGE_FEEDBACK'
PERM_MANAGE_USERS = 'PERM_MANAGE_USERS'
PERM_MANAGE_QUIZ = 'PERM_MANAGE_QUIZ'
PERM_MANAGE_PLAY = 'PERM_MANAGE_PLAY'
PERM_MANAGE_KATHA = 'PERM_MANAGE_KATHA'
PERM_MANAGE_ARTICLES = 'PERM_MANAGE_ARTICLES'
PERM_MANAGE_AI = 'PERM_MANAGE_AI'

ALL_PERMISSIONS = [
    PERM_DOWNLOAD_BOOKS,
    PERM_UPLOAD_EXCEL,
    PERM_EDIT_BOOK_NAME,
    PERM_EDIT_TAGS,
    PERM_EDIT_SUB_BOOK,
    PERM_EDIT_LINK,
    PERM_ADD_BOOK,
    PERM_DELETE_BOOK,
    PERM_EDIT_OCR,
    PERM_VIEW_FEEDBACK,
    PERM_MANAGE_FEEDBACK,
    PERM_MANAGE_USERS,
    PERM_MANAGE_QUIZ,
    PERM_MANAGE_PLAY,
    PERM_MANAGE_KATHA,
    PERM_MANAGE_ARTICLES,
    PERM_MANAGE_AI
]


def load_admins():
    """Load all admins from SQLite database as a dict. Format matches legacy admins.json:
    { username: { 'password_hash': ..., 'permissions': [...], 'created_at': ..., 'last_login': ... } }
    """
    conn = get_db()
    try:
        rows = conn.execute('SELECT * FROM admins').fetchall()
        admins = {}
        for r in rows:
            perms = _json.loads(r['permissions_json']) if r['permissions_json'] else []
            admins[r['username']] = {
                'password_hash': r['password_hash'],
                'permissions': perms,
                'created_at': r['created_at'],
                'last_login': r['last_login']
            }
        return admins
    except Exception as e:
        print(f"Error loading admins: {e}")
        return {}
    finally:
        conn.close()


def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(password, hashed_password):
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_admin_by_username(username):
    """Get admin username (normalized uppercase) and data dict. Returns (stored_username, data)."""
    if username and '@' in username:
        username = username.split('@')[0]
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM admins WHERE UPPER(username) = UPPER(?)', (username,)).fetchone()
        if row:
            perms = _json.loads(row['permissions_json']) if row['permissions_json'] else []
            data = {
                'password_hash': row['password_hash'],
                'permissions': perms,
                'created_at': row['created_at'],
                'last_login': row['last_login'],
                'gemini_api_key': decrypt_secret(row['gemini_api_key']) if 'gemini_api_key' in row.keys() and row['gemini_api_key'] else None,
                'gemini_model': row['gemini_model'] if 'gemini_model' in row.keys() else None,
            }
            return row['username'], data
        return None, None
    finally:
        conn.close()


def get_admin_gemini_key(username):
    """Return (api_key, model) for the given admin username, or (None, None) if not set."""
    _, data = get_admin_by_username(username)
    if data:
        key = data.get('gemini_api_key')
        return decrypt_secret(key) if key else None, data.get('gemini_model')
    return None, None


def update_admin_gemini_key(username, api_key, gemini_model=None):
    """Save or clear the Gemini API key and model for an admin (encrypts API key before saving)."""
    if username and '@' in username:
        username = username.split('@')[0]
    stored_key = encrypt_secret(api_key.strip()) if api_key and api_key.strip() else None
    conn = get_db()
    try:
        conn.execute(
            'UPDATE admins SET gemini_api_key = ?, gemini_model = ? WHERE UPPER(username) = UPPER(?)',
            (stored_key, gemini_model, username)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating admin gemini key: {e}")
        return False
    finally:
        conn.close()


def create_admin(username, password, permissions):
    if username.upper() == 'SUPERADMIN':
        return False, "Cannot create 'SUPERADMIN' account"
    
    stored_username, _ = get_admin_by_username(username)
    if stored_username:
        return False, "Username already exists"
    
    conn = get_db()
    try:
        perms_json = _json.dumps(permissions)
        conn.execute(
            'INSERT INTO admins (username, password_hash, permissions_json, created_at, last_login) VALUES (?, ?, ?, ?, ?)',
            (username.upper(), hash_password(password), perms_json, get_ist_now().isoformat(), None)
        )
        conn.commit()
        return True, "Admin created successfully"
    except Exception as e:
        print(f"Error creating admin: {e}")
        return False, "Error saving to database"
    finally:
        conn.close()


def delete_admin(username):
    stored_username, _ = get_admin_by_username(username)
    if not stored_username:
        return False, "Admin not found"
    
    if stored_username.upper() == 'SUPERADMIN':
        return False, "Cannot delete the super-admin 'SUPERADMIN' account"
    
    conn = get_db()
    try:
        conn.execute('DELETE FROM admins WHERE UPPER(username) = UPPER(?)', (username,))
        conn.commit()
        return True, "Admin deleted successfully"
    except Exception as e:
        print(f"Error deleting admin: {e}")
        return False, "Error deleting from database"
    finally:
        conn.close()


def update_admin(username, permissions, password=None):
    stored_username, data = get_admin_by_username(username)
    if not stored_username:
        return False, "Admin not found"
    
    conn = get_db()
    try:
        perms_json = _json.dumps(permissions)
        if password:
            conn.execute(
                'UPDATE admins SET permissions_json = ?, password_hash = ? WHERE UPPER(username) = UPPER(?)',
                (perms_json, hash_password(password), username)
            )
        else:
            conn.execute(
                'UPDATE admins SET permissions_json = ? WHERE UPPER(username) = UPPER(?)',
                (perms_json, username)
            )
        conn.commit()
        return True, "Admin updated successfully"
    except Exception as e:
        print(f"Error updating admin: {e}")
        return False, "Error updating database"
    finally:
        conn.close()


def update_last_login(username):
    conn = get_db()
    try:
        conn.execute(
            'UPDATE admins SET last_login = ? WHERE UPPER(username) = UPPER(?)',
            (get_ist_now().isoformat(), username)
        )
        conn.commit()
    except Exception as e:
        print(f"Error updating last login: {e}")
    finally:
        conn.close()


def get_top_favourites(limit=10):
    """Get the most favorited books across all users."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT book_name, COUNT(*) as fav_count
            FROM favourites
            GROUP BY book_name
            ORDER BY fav_count DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# =============================================================================
# SAMBHASHANA AI MODES CRUD
# =============================================================================

def get_sambhashana_modes(only_active=False):
    """Retrieve all Sambhashana AI modes from the database."""
    conn = get_db()
    try:
        if only_active:
            rows = conn.execute('SELECT * FROM sambhashana_modes WHERE is_active = 1 ORDER BY sort_order ASC').fetchall()
        else:
            rows = conn.execute('SELECT * FROM sambhashana_modes ORDER BY sort_order ASC').fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_sambhashana_mode(key):
    """Retrieve a single Sambhashana AI mode by key."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM sambhashana_modes WHERE key = ?', (key,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_sambhashana_mode(key, name, label, icon, system_prompt, is_active=1, sort_order=0, gemini_model=None, suggestions=None):
    """Insert or replace a Sambhashana AI mode."""
    conn = get_db()
    try:
        conn.execute('''
            INSERT OR REPLACE INTO sambhashana_modes (key, name, label, icon, system_prompt, is_active, sort_order, gemini_model, suggestions, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (key.strip().lower(), name.strip(), label.strip() if label else None, icon.strip() if icon else None, system_prompt.strip(), int(is_active), int(sort_order), gemini_model.strip() if gemini_model else None, suggestions.strip() if suggestions else None, get_ist_now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving Sambhashana mode: {e}")
        return False
    finally:
        conn.close()


def get_system_setting(key, default=None):
    """Retrieve a global system setting by key."""
    conn = get_db()
    try:
        row = conn.execute('SELECT value FROM system_settings WHERE key = ?', (key,)).fetchone()
        return row['value'] if row else default
    except Exception as e:
        print(f"Error getting system setting {key}: {e}")
        return default
    finally:
        conn.close()


def set_system_setting(key, value):
    """Insert or replace a global system setting."""
    conn = get_db()
    try:
        conn.execute('INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error setting system setting {key}: {e}")
        return False
    finally:
        conn.close()


def delete_sambhashana_mode(key):
    """Delete a Sambhashana AI mode by key."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM sambhashana_modes WHERE key = ?', (key,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting Sambhashana mode: {e}")
        return False
    finally:
        conn.close()


def get_user_ai_overrides():
    """Retrieve all user AI overrides joined with user display_name and email."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT o.*, u.display_name, u.email
            FROM user_ai_overrides o
            JOIN users u ON o.user_id = u.id
        ''').fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting user AI overrides: {e}")
        return []
    finally:
        conn.close()


def get_user_ai_override(user_id):
    """Retrieve override details for a specific user. Returns dict or None."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM user_ai_overrides WHERE user_id = ?', (user_id,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error getting user AI override for {user_id}: {e}")
        return None
    finally:
        conn.close()


def save_user_ai_override(user_id, vyakhya_access, sambhashana_access, semantic_search_access, history_limit_override, use_fallback_allowed):
    """Insert or update AI overrides for a specific user."""
    conn = get_db()
    try:
        # Validate values
        vyakhya_access = vyakhya_access if vyakhya_access in ('allow', 'block') else 'default'
        sambhashana_access = sambhashana_access if sambhashana_access in ('allow', 'block') else 'default'
        semantic_search_access = semantic_search_access if semantic_search_access in ('allow', 'block') else 'default'
        use_fallback_allowed = use_fallback_allowed if use_fallback_allowed in ('allow', 'block') else 'default'
        
        try:
            history_limit_override = int(history_limit_override) if history_limit_override is not None and str(history_limit_override).strip() != '' else None
            if history_limit_override is not None and history_limit_override < 1:
                history_limit_override = None
        except (ValueError, TypeError):
            history_limit_override = None

        conn.execute('''
            INSERT OR REPLACE INTO user_ai_overrides (user_id, vyakhya_access, sambhashana_access, semantic_search_access, history_limit_override, use_fallback_allowed)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, vyakhya_access, sambhashana_access, semantic_search_access, history_limit_override, use_fallback_allowed))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving user AI override: {e}")
        return False
    finally:
        conn.close()


def delete_user_ai_override(user_id):
    """Delete overrides for a specific user."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM user_ai_overrides WHERE user_id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting user AI override: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# USER AI USAGE LOGGING
# =============================================================================

def log_user_ai_usage(user_id, feature, success=True):
    """Log or increment AI usage metrics for a specific user and feature."""
    if not user_id:
        return False
    conn = get_db()
    try:
        now = get_ist_now().isoformat()
        calls_inc = 1
        errors_inc = 0 if success else 1
        conn.execute('''
            INSERT INTO user_ai_usage (user_id, feature, total_calls, total_errors, last_used_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, feature) DO UPDATE SET
                total_calls = total_calls + ?,
                total_errors = total_errors + ?,
                last_used_at = ?
        ''', (user_id, feature, calls_inc, errors_inc, now, calls_inc, errors_inc, now))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error logging user AI usage for user {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_user_ai_usages():
    """Retrieve individual AI usage statistics for all registered users, aggregated by user."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT u.id as user_id, u.email, u.display_name,
                   SUM(CASE WHEN uu.feature = 'vyakhya' THEN uu.total_calls ELSE 0 END) as vyakhya_calls,
                   SUM(CASE WHEN uu.feature = 'vyakhya' THEN uu.total_errors ELSE 0 END) as vyakhya_errors,
                   SUM(CASE WHEN uu.feature = 'sambhashana' THEN uu.total_calls ELSE 0 END) as sambhashana_calls,
                   SUM(CASE WHEN uu.feature = 'sambhashana' THEN uu.total_errors ELSE 0 END) as sambhashana_errors,
                   SUM(CASE WHEN uu.feature = 'semantic_search' THEN uu.total_calls ELSE 0 END) as semantic_search_calls,
                   SUM(CASE WHEN uu.feature = 'semantic_search' THEN uu.total_errors ELSE 0 END) as semantic_search_errors,
                   MAX(uu.last_used_at) as last_used_at
            FROM users u
            LEFT JOIN user_ai_usage uu ON u.id = uu.user_id
            GROUP BY u.id, u.email, u.display_name
            ORDER BY (CASE WHEN MAX(uu.last_used_at) IS NULL THEN 1 ELSE 0 END), MAX(uu.last_used_at) DESC, u.email ASC
        ''').fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting user AI usages: {e}")
        return []
    finally:
        conn.close()


def reset_user_ai_usage(user_id, feature=None):
    """Reset AI usage metrics for a user. If feature is provided, reset only that feature."""
    conn = get_db()
    try:
        if feature:
            conn.execute('DELETE FROM user_ai_usage WHERE user_id = ? AND feature = ?', (user_id, feature))
        else:
            conn.execute('DELETE FROM user_ai_usage WHERE user_id = ?', (user_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error resetting user AI usage: {e}")
        return False
    finally:
        conn.close()


def create_vector_request(user_id, book_name, decryption_key):
    """Create or update a pending vector download request for a user."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT id, status FROM vector_download_requests WHERE user_id = ? AND book_name = ?',
            (user_id, book_name)
        ).fetchone()
        
        if row:
            conn.execute(
                'UPDATE vector_download_requests SET status = "pending", decryption_key = ?, requested_at = CURRENT_TIMESTAMP, approved_at = NULL WHERE id = ?',
                (decryption_key, row['id'])
            )
        else:
            conn.execute(
                'INSERT INTO vector_download_requests (user_id, book_name, status, decryption_key) VALUES (?, ?, "pending", ?)',
                (user_id, book_name, decryption_key)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error creating vector request: {e}")
        return False
    finally:
        conn.close()


def get_vector_request(user_id, book_name):
    """Get a specific vector download request by user_id and book_name."""
    conn = get_db()
    try:
        row = conn.execute(
            'SELECT * FROM vector_download_requests WHERE user_id = ? AND book_name = ?',
            (user_id, book_name)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error getting vector request: {e}")
        return None
    finally:
        conn.close()


def get_user_vector_requests(user_id):
    """Retrieve all vector download requests for a specific user."""
    conn = get_db()
    try:
        rows = conn.execute(
            'SELECT * FROM vector_download_requests WHERE user_id = ?',
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting user vector requests: {e}")
        return []
    finally:
        conn.close()


def get_all_vector_requests():
    """Retrieve all vector download requests for the admin panel, including user details."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT r.*, u.email as user_email, u.display_name as user_display_name
            FROM vector_download_requests r
            JOIN users u ON r.user_id = u.id
            ORDER BY r.requested_at DESC
        ''').fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting all vector requests: {e}")
        return []
    finally:
        conn.close()


def approve_vector_requests(request_ids):
    """Approve a list of vector download requests and return their details for email notification."""
    conn = get_db()
    approved_details = []
    try:
        for rid in request_ids:
            row = conn.execute('''
                SELECT r.id, r.book_name, r.decryption_key, u.email
                FROM vector_download_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.id = ?
            ''', (rid,)).fetchone()
            
            if row:
                conn.execute(
                    'UPDATE vector_download_requests SET status = "approved", approved_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (rid,)
                )
                approved_details.append(dict(row))
        conn.commit()
        return approved_details
    except Exception as e:
        print(f"Error approving vector requests: {e}")
        return []
    finally:
        conn.close()


def reject_vector_requests(request_ids):
    """Reject a list of vector download requests."""
    conn = get_db()
    try:
        for rid in request_ids:
            conn.execute(
                'UPDATE vector_download_requests SET status = "rejected", approved_at = NULL WHERE id = ?',
                (rid,)
            )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error rejecting vector requests: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# COMMUNITY BOOK EDITS (CROWDSOURCED NOTEPAD PROOFREADING)
# =============================================================================

def submit_community_edit(book_name, page_number, client_token, edited_text, original_text='', contributor_name='', contributor_email='', edit_notes=''):
    """Insert or update a pending community edit for a book page and client token."""
    import uuid
    conn = get_db()
    try:
        # Check if an existing pending edit exists for this client, book, and page
        existing = conn.execute('''
            SELECT id, edit_id, original_text FROM community_book_edits 
            WHERE book_name = ? AND page_number = ? AND client_token = ? AND status = 'pending'
            LIMIT 1
        ''', (book_name, page_number, client_token)).fetchone()

        # Preserve the genuine original baseline from existing record if already recorded
        base_original = (existing['original_text'] if (existing and existing['original_text']) else (original_text or '')).strip()

        # If user manually edited text back to match original official text, cancel the pending edit
        if base_original and edited_text.strip() == base_original:
            if existing:
                conn.execute('DELETE FROM community_book_edits WHERE id = ?', (existing['id'],))
                conn.commit()
            return 'reverted'

        if existing:
            conn.execute('''
                UPDATE community_book_edits
                SET edited_text = ?, contributor_name = ?, contributor_email = ?, edit_notes = ?, original_text = ?, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (edited_text, contributor_name, contributor_email, edit_notes, base_original, existing['id']))
            conn.commit()
            return existing['edit_id']
        else:
            edit_id = str(uuid.uuid4())
            conn.execute('''
                INSERT INTO community_book_edits 
                (edit_id, book_name, page_number, client_token, contributor_name, contributor_email, original_text, edited_text, edit_notes, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ''', (edit_id, book_name, page_number, client_token, contributor_name, contributor_email, base_original, edited_text, edit_notes))
            conn.commit()
            return edit_id
    except Exception as e:
        print(f"Error submitting community edit: {e}")
        return None
    finally:
        conn.close()


def get_user_pending_edit(book_name, page_number, client_token):
    """Retrieve any pending edit for this book, page, and client token."""
    if not client_token:
        return None
    conn = get_db()
    try:
        row = conn.execute('''
            SELECT * FROM community_book_edits
            WHERE book_name = ? AND page_number = ? AND client_token = ? AND status = 'pending'
            ORDER BY created_at DESC LIMIT 1
        ''', (book_name, page_number, client_token)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error fetching user pending edit: {e}")
        return None
    finally:
        conn.close()


def get_pending_edits(status='pending', limit=100, offset=0):
    """Retrieve list of community edits filtered by status."""
    conn = get_db()
    try:
        query = 'SELECT * FROM community_book_edits'
        params = []
        if status and status != 'all':
            query += ' WHERE status = ?'
            params.append(status)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching pending edits: {e}")
        return []
    finally:
        conn.close()


def get_pending_edits_count(status='pending'):
    """Get the total count of pending edits for admin badges and counters."""
    conn = get_db()
    try:
        if status and status != 'all':
            row = conn.execute('SELECT COUNT(*) FROM community_book_edits WHERE status = ?', (status,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) FROM community_book_edits').fetchone()
        return row[0] if row else 0
    except Exception as e:
        print(f"Error fetching pending edits count: {e}")
        return 0
    finally:
        conn.close()


def get_community_edit_by_id(edit_id):
    """Get a single community edit record by edit_id."""
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM community_book_edits WHERE edit_id = ?', (edit_id,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error getting community edit by id: {e}")
        return None
    finally:
        conn.close()


def update_community_edit_status(edit_id, status, reviewed_by=None):
    """Update status of an edit ('approved', 'rejected', 'pending')."""
    conn = get_db()
    try:
        conn.execute('''
            UPDATE community_book_edits 
            SET status = ?, reviewed_at = CURRENT_TIMESTAMP, reviewed_by = ?
            WHERE edit_id = ?
        ''', (status, reviewed_by, edit_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating community edit status: {e}")
        return False
    finally:
        conn.close()


# =============================================================================
# LEKHA SHODHAKA — VIDWAN PROOFREADING REQUESTS
# =============================================================================

def create_proofreading_request(user_name, user_email, user_phone, submission_type, title,
                                content_text='', file_path='', file_name='', file_size=0,
                                notes='', user_id=None, wants_vector_data=0, embedding_model=''):
    """Create a new Vidwan proofreading request in the database."""
    import uuid
    import datetime
    conn = get_db()
    try:
        # Generate human-friendly unique request code: LSR-YYYYMMDD-XXXXX
        today_str = datetime.datetime.now().strftime('%Y%m%d')
        unique_suffix = uuid.uuid4().hex[:5].upper()
        request_id = f"LSR-{today_str}-{unique_suffix}"

        conn.execute('''
            INSERT INTO lekha_proofreading_requests 
            (request_id, user_id, user_name, user_email, user_phone, submission_type, 
             title, content_text, file_path, file_name, file_size, notes, status,
             wants_vector_data, embedding_model)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        ''', (request_id, user_id, (user_name or '').strip(), (user_email or '').strip(),
              (user_phone or '').strip(), submission_type, (title or '').strip(),
              content_text or '', file_path or '', file_name or '', file_size or 0,
              (notes or '').strip(), 1 if wants_vector_data else 0, (embedding_model or '').strip()))
        conn.commit()
        return request_id
    except Exception as e:
        print(f"Error creating proofreading request: {e}")
        return None
    finally:
        conn.close()


def get_proofreading_request(request_id):
    """Retrieve a single proofreading request by request_id."""
    conn = get_db()
    try:
        row = conn.execute('''
            SELECT * FROM lekha_proofreading_requests 
            WHERE request_id = ?
        ''', (request_id.strip(),)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"Error fetching proofreading request: {e}")
        return None
    finally:
        conn.close()


def list_proofreading_requests(status='all', limit=50, offset=0, search=None):
    """Retrieve proofreading requests with optional status filter and search term."""
    conn = get_db()
    try:
        query = 'SELECT * FROM lekha_proofreading_requests WHERE 1=1'
        params = []
        if status and status != 'all':
            query += ' AND status = ?'
            params.append(status)
        if search and search.strip():
            s = f"%{search.strip()}%"
            query += ''' AND (request_id LIKE ? OR user_name LIKE ? OR user_email LIKE ? 
                              OR user_phone LIKE ? OR title LIKE ? OR notes LIKE ?)'''
            params.extend([s, s, s, s, s, s])
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error listing proofreading requests: {e}")
        return []
    finally:
        conn.close()


def get_proofreading_requests_count(status='all'):
    """Count proofreading requests for badges and pagination."""
    conn = get_db()
    try:
        if status and status != 'all':
            row = conn.execute('SELECT COUNT(*) FROM lekha_proofreading_requests WHERE status = ?', (status,)).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) FROM lekha_proofreading_requests').fetchone()
        return row[0] if row else 0
    except Exception as e:
        print(f"Error getting proofreading requests count: {e}")
        return 0
    finally:
        conn.close()


def update_proofreading_request_status(request_id, status, admin_notes=None, completed_by=None):
    """Update status of a proofreading request ('pending', 'in_progress', 'completed', 'rejected')."""
    conn = get_db()
    try:
        if admin_notes is not None:
            conn.execute('''
                UPDATE lekha_proofreading_requests
                SET status = ?, admin_notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            ''', (status, admin_notes, request_id))
        else:
            conn.execute('''
                UPDATE lekha_proofreading_requests
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            ''', (status, request_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating proofreading request status: {e}")
        return False
    finally:
        conn.close()


def complete_proofreading_request(request_id, proofread_result_text, admin_notes='', 
                                  result_file_path='', result_file_name='', completed_by=None):
    """Mark a proofreading request as completed with proofread result text and remarks."""
    conn = get_db()
    try:
        conn.execute('''
            UPDATE lekha_proofreading_requests
            SET status = 'completed',
                proofread_result_text = ?,
                admin_notes = ?,
                result_file_path = ?,
                result_file_name = ?,
                completed_at = CURRENT_TIMESTAMP,
                completed_by = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE request_id = ?
        ''', (proofread_result_text or '', admin_notes or '', result_file_path or '', 
              result_file_name or '', completed_by or '', request_id))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error completing proofreading request: {e}")
        return False
    finally:
        conn.close()


def get_user_proofreading_requests(user_email=None, user_id=None, limit=20):
    """Fetch past proofreading requests submitted by a user or email."""
    conn = get_db()
    try:
        query = 'SELECT * FROM lekha_proofreading_requests WHERE '
        params = []
        conds = []
        if user_id:
            conds.append('user_id = ?')
            params.append(user_id)
        if user_email:
            conds.append('LOWER(user_email) = LOWER(?)')
            params.append(user_email.strip())
        if not conds:
            return []
        query += ' OR '.join(conds)
        query += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching user proofreading requests: {e}")
        return []
    finally:
        conn.close()





