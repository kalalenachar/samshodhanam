import os
import sys
import logging
import io
import math
import asyncio

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.request import HTTPXRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

import bot_db as db
from bot_audio_processor import (
    transcribe_audio_file,
    get_audio_duration,
    ai_clean_transcript,
    ai_assist_audio_transcript,
    split_audio_into_chunks,
    cleanup_chunk_files
)

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or db.get_setting("telegram_bot_token", "")
SETUP_SECRET = os.getenv("ADMIN_SETUP_SECRET") or db.get_setting("admin_setup_secret", "admin123")
STT_URL = os.getenv("SAMSHO_STT_API_URL") or os.getenv("SAMSHODHANA_STT_HTTP_URL", "http://localhost:5001/api/v1/stt")

LARGE_AUDIO_DURATION_THRESHOLD = 60.0  # seconds (1 minute)
LARGE_AUDIO_SIZE_THRESHOLD = 10 * 1024 * 1024  # 10 MB
CHUNK_DURATION_SEC = 60.0  # chunk size in seconds

TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp_audio")
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize Database
db.init_db()

# Logging setup
LOG_FILE = os.path.join(os.path.dirname(__file__), "telegram_bot.log")

log_handlers = [
    logging.StreamHandler(sys.stdout),
    logging.FileHandler(LOG_FILE, encoding="utf-8")
]

logging.basicConfig(
    format="%(asctime)s [SamshodhanaBot] %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=log_handlers
)
logger = logging.getLogger("samshodhana_bot")

# Supported Languages & Scripts
LANGUAGES = db.ALL_LANGUAGES

def get_language_keyboard(current_lang: str):
    enabled_codes = db.get_enabled_languages()
    keyboard = []
    row = []
    for code in enabled_codes:
        name = LANGUAGES.get(code, code)
        short_code = f"{code}-IN" if not code.endswith("-IN") else code
        prefix = "✅ " if (code == current_lang or short_code == current_lang) else ""
        row.append(InlineKeyboardButton(f"{prefix}{name}", callback_data=f"setlang_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def get_script_keyboard(current_script: str):
    enabled_scripts = db.get_enabled_scripts()
    keyboard = []
    row = []
    for code in enabled_scripts:
        name = SCRIPTS.get(code, code)
        prefix = "✅ " if code == current_script else ""
        row.append(InlineKeyboardButton(f"{prefix}{name}", callback_data=f"setscript_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def get_transliterator_bot_url(log_id: int) -> str:
    bot_username = os.getenv("TRANSLITERATOR_BOT_USERNAME") or db.get_setting("transliterator_bot_username", "TVSM_Translatorator_Bot")
    bot_username = bot_username.lstrip("@")
    return f"https://t.me/{bot_username}?start=stt_{log_id}"

def get_transcription_action_keyboard(log_id: int, is_iast: bool = False):
    iast_label = "🔤 Show Devanagari" if is_iast else "🔄 IAST Script"
    translit_url = get_transliterator_bot_url(log_id)
    keyboard = [
        [
            InlineKeyboardButton("✨ AI Clean", callback_data=f"ai_clean_{log_id}"),
            InlineKeyboardButton("🤖 AI Assist (Audio)", callback_data=f"ai_assist_{log_id}")
        ],
        [
            InlineKeyboardButton(iast_label, callback_data=f"toggle_iast_{log_id}"),
            InlineKeyboardButton("📋 Copy Text", callback_data=f"copy_text_{log_id}")
        ],
        [
            InlineKeyboardButton("🌐 Transliterate", url=translit_url)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_other_bots_keyboard() -> InlineKeyboardMarkup:
    """Builds inline keyboard with direct links to all Samshodhanam Telegram Bots."""
    ocr_uname = (os.getenv("TELEGRAM_OCR_BOT_USERNAME") or "Samshodhana_OCR_Bot").lstrip('@')
    stt_uname = (os.getenv("SANSKRIT_STT_BOT_USERNAME") or "TVSM_STT_BOT").lstrip('@')
    trans_uname = (os.getenv("TRANSLITERATOR_BOT_USERNAME") or db.get_setting("transliterator_bot_username", "TVSM_Translatorator_Bot")).lstrip('@')
    
    keyboard = [
        [
            InlineKeyboardButton("📸 OCR Bot", url=f"https://t.me/{ocr_uname}"),
            InlineKeyboardButton("🎙️ Speech-to-Text Bot", url=f"https://t.me/{stt_uname}")
        ],
        [
            InlineKeyboardButton("🌐 Transliterator Bot", url=f"https://t.me/{trans_uname}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ Create Access Code", callback_data="admin_create_help"),
            InlineKeyboardButton("📋 List Access Codes", callback_data="admin_list_codes")
        ],
        [
            InlineKeyboardButton("📊 Usage Report", callback_data="admin_team_report"),
            InlineKeyboardButton("⛔ Revoke Code", callback_data="admin_revoke_prompt")
        ],
        [
            InlineKeyboardButton("📝 AI System Prompts", callback_data="admin_prompts_menu"),
            InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="admin_menu")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_dashboard_text(user_name: str):
    codes = db.list_access_codes()
    active_codes = len([c for c in codes if c['status'] == 'active'])
    revoked_codes = len([c for c in codes if c['status'] == 'revoked'])
    report = db.get_team_usage_report()
    total_users = len(report)

    return (
        f"👑 *Samshodhana Sanskrit STT Admin Panel*\n"
        f"Powered by *Samshodhana STT Engine*\n\n"
        f"👋 Welcome back, Admin *{user_name}*!\n"
        f"───────────────────\n"
        f"📊 *System Overview:*\n"
        f"• 👥 *Total Active Users:* {total_users}\n"
        f"• 🔑 *Active Access Codes:* {active_codes}\n"
        f"• ⛔ *Revoked Codes:* {revoked_codes}\n\n"
        f"👇 *Select an admin action below:*"
    )

# ─── Commands ─────────────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # Admin Check
    if db.is_admin(user_id):
        dash_text = get_admin_dashboard_text(user.first_name or user.username or "Admin")
        await update.message.reply_text(dash_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
        return

    # Check existing user
    user_data = db.get_user(user_id)
    if user_data:
        is_ok, msg = db.check_user_access(user_id)
        if is_ok:
            lang_name = LANGUAGES.get(user_data.get('preferred_language', 'sa-IN'), 'Sanskrit')
            text = (
                f"🎙️ *Samshodhana Sanskrit Speech-to-Text Bot*\n\n"
                f"Welcome, *{user.first_name}*!\n"
                f"🔑 Access Code: `{user_data['access_code']}` (Active)\n"
                f"🌐 Language: *{lang_name}*\n\n"
                f"🎙️ *Send me any voice note or audio file* to transcribe into Sanskrit Devanagari!"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🤖 Other Telegram Bots", callback_data="menu_otherbots")],
                [InlineKeyboardButton("💬 Contact & Support", callback_data="menu_support")]
            ])
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
            return
        else:
            await update.message.reply_text(f"⚠️ {msg}")
            return

    # Unregistered user prompt
    text = (
        f"🎙️ *Welcome to Samshodhana Sanskrit Speech-to-Text Bot*\n\n"
        f"🔑 *Access Code Required*\n"
        f"To use this bot, please enter your assigned Access Code:\n"
        f"👉 Type `/code YOUR_CODE` or simply send the code in chat."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if context.args:
        code_input = context.args[0].strip().upper()
    else:
        await update.message.reply_text("Usage: `/code YOUR_ACCESS_CODE`", parse_mode="Markdown")
        return

    code_data = db.get_access_code(code_input)
    if not code_data or code_data['status'] != 'active':
        await update.message.reply_text("❌ *Invalid or Inactive Access Code.* Please check with your administrator.", parse_mode="Markdown")
        return

    db.register_user(user_id, user.username or "", user.first_name or "", code_input)
    await update.message.reply_text(
        f"✅ *Access Granted!*\n"
        f"Access Code `{code_input}` activated.\n\n"
        f"🎙️ *Send me any voice note or audio file* now to transcribe it into Sanskrit!",
        parse_mode="Markdown"
    )

async def createcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/createcode <CODE> [daily_max_minutes]`", parse_mode="Markdown")
        return

    code_str = context.args[0].strip().upper()
    max_mins = 100.0
    if len(context.args) > 1:
        try:
            max_mins = float(context.args[1])
        except ValueError:
            pass

    code_obj = db.create_access_code(code_str, daily_max_minutes=max_mins)
    await update.message.reply_text(
        f"✅ *Access Code Created!*\n"
        f"• Code: `{code_obj['code']}`\n"
        f"• Daily Limit: `{int(max_mins)} mins`",
        parse_mode="Markdown"
    )

async def revokecode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/revokecode <CODE>`", parse_mode="Markdown")
        return

    code_str = context.args[0].strip().upper()
    db.revoke_access_code(code_str)
    await update.message.reply_text(f"⛔ Access Code `{code_str}` has been revoked.", parse_mode="Markdown")


async def setprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📝 *Usage:* `/setprompt <assist|clean> <PROMPT_TEXT>`\n\n"
            "• `assist` = Multimodal Audio + STT proofreading prompt\n"
            "• `clean` = Text-only phonetic proofreading prompt\n\n"
            "*Example:*\n`/setprompt assist Listen to the audio carefully and correct all visargas and anusvaras based on accurate pronunciation...`",
            parse_mode="Markdown"
        )
        return

    prompt_type = context.args[0].strip().lower()
    if prompt_type not in ["assist", "clean", "ai_assist", "ai_clean"]:
        await update.message.reply_text("⚠️ First argument must be `assist` (or `ai_assist`) or `clean` (or `ai_clean`).", parse_mode="Markdown")
        return

    new_prompt = " ".join(context.args[1:]).strip()
    if not new_prompt:
        await update.message.reply_text("⚠️ Prompt text cannot be empty.", parse_mode="Markdown")
        return

    if "assist" in prompt_type:
        db.set_ai_assist_prompt(new_prompt)
        label = "AI Assist (Audio + Text)"
    else:
        db.set_ai_clean_prompt(new_prompt)
        label = "AI Clean (Text)"

    await update.message.reply_text(
        f"✅ *{label} System Prompt Updated!*\n\n"
        f"```text\n{new_prompt}\n```",
        parse_mode="Markdown"
    )

async def getprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required.")
        return

    target = context.args[0].strip().lower() if context.args else "all"

    msg_lines = ["📝 *Current System Prompts:*", ""]

    if target in ["all", "assist", "ai_assist"]:
        is_custom = db.is_ai_prompt_customized("ai_assist")
        status = "🟢 CUSTOMIZED" if is_custom else "🔵 DEFAULT"
        p_text = db.get_ai_assist_prompt()
        msg_lines.append(f"🤖 *AI Assist Prompt* ({status}):")
        msg_lines.append(f"```text\n{p_text}\n```")
        msg_lines.append("")

    if target in ["all", "clean", "ai_clean"]:
        is_custom = db.is_ai_prompt_customized("ai_clean")
        status = "🟢 CUSTOMIZED" if is_custom else "🔵 DEFAULT"
        p_text = db.get_ai_clean_prompt()
        msg_lines.append(f"✨ *AI Clean Prompt* ({status}):")
        msg_lines.append(f"```text\n{p_text}\n```")
        msg_lines.append("")

    msg_lines.append("💡 *Commands to Edit:*")
    msg_lines.append("• `/setprompt assist <PROMPT>` — Update AI Assist prompt")
    msg_lines.append("• `/setprompt clean <PROMPT>` — Update AI Clean prompt")
    msg_lines.append("• `/resetprompt assist` — Reset AI Assist prompt to default")
    msg_lines.append("• `/resetprompt clean` — Reset AI Clean prompt to default")

    await update.message.reply_text("\n".join(msg_lines), parse_mode="Markdown")

async def resetprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required.")
        return

    if not context.args:
        await update.message.reply_text("Usage: `/resetprompt <assist|clean>`", parse_mode="Markdown")
        return

    prompt_type = context.args[0].strip().lower()
    if "assist" in prompt_type:
        db.reset_ai_prompt("ai_assist")
        await update.message.reply_text("🔄 *AI Assist System Prompt reset to Default.*", parse_mode="Markdown")
    elif "clean" in prompt_type:
        db.reset_ai_prompt("ai_clean")
        await update.message.reply_text("🔄 *AI Clean System Prompt reset to Default.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Argument must be `assist` or `clean`.", parse_mode="Markdown")


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Usage: `/setup <secret_key>`", parse_mode="Markdown")
        return

    key = context.args[0].strip()
    current_secret = os.getenv("ADMIN_SETUP_SECRET") or db.get_setting("admin_setup_secret", "admin123")
    
    if key == current_secret:
        db.add_admin(user.id, user.username or user.first_name or "")
        dash_text = get_admin_dashboard_text(user.first_name or "Admin")
        await update.message.reply_text("🎉 *Admin Setup Successful!*", parse_mode="Markdown")
        await update.message.reply_text(dash_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    else:
        await update.message.reply_text("❌ *Incorrect setup key.* Access denied.")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not db.is_admin(user.id):
        await update.message.reply_text("⛔ Admin access required. Use `/setup <secret>` first.")
        return

    dash_text = get_admin_dashboard_text(user.first_name or "Admin")
    await update.message.reply_text(dash_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def lang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = db.get_user(user_id)
    current_lang = user_data.get('preferred_language', 'sa-IN') if user_data else 'sa-IN'
    await update.message.reply_text("🌐 *Select Preferred Transcription Language:*", parse_mode="Markdown", reply_markup=get_language_keyboard(current_lang))


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logs = db.get_user_transcription_history(user_id, limit=100)
    if not logs:
        await update.message.reply_text("📥 *No transcription history found to export.*", parse_mode="Markdown")
        return

    lines = [f"=== SAMSHODHANA SANSKRIT STT TRANSCRIPTION HISTORY ==="]
    lines.append(f"User ID: {user_id} | Total Logs: {len(logs)}\n" + ("=" * 55) + "\n")

    for idx, l in enumerate(logs, 1):
        ts = l.get('timestamp', '')
        dur = l.get('duration_sec', 0.0)
        text = l.get('full_transcript') or l.get('transcript_snippet') or ''
        lines.append(f"[{idx}] Timestamp: {ts} | Duration: {dur:.1f}s")
        lines.append(f"Transcript: {text}")
        lines.append("-" * 55)

    content = "\n".join(lines)
    file_bytes = io.BytesIO(content.encode('utf-8'))
    file_bytes.name = f"Samshodhana_STT_History_{user_id}.txt"

    await update.message.reply_document(
        document=file_bytes,
        filename=f"Samshodhana_STT_History_{user_id}.txt",
        caption=f"📄 Exported *{len(logs)} transcription records* as a clean `.txt` document.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_txt = (
        f"🎙️ *Samshodhana Sanskrit Speech-to-Text Bot Help*\n\n"
        f"• 🎤 *Voice Notes & Audio*: Send any audio clip or voice note to transcribe.\n"
        f"• 🌐 `/lang` : Switch speech recognition language (Sanskrit, Tamil, Hindi, Telugu, etc.)\n"
        
        f"• 📥 `/export` : Download your full transcription history as a `.txt` file\n"
        f"• 🔑 `/code <CODE>` : Activate your access code\n"
        
    )
    await update.message.reply_text(help_txt, parse_mode="Markdown")

# ─── Callback Queries ──────────────────────────────────────────────────────────

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user
    user_id = user.id

    await query.answer()

    if data.startswith("setlang_"):
        lang_code = data.split("_")[1]
        if not db.is_language_enabled(lang_code):
            await query.edit_message_text("⚠️ *This language is currently disabled by administrator.*", parse_mode="Markdown")
            return
        db.set_user_language(user_id, lang_code)
        lang_name = LANGUAGES.get(lang_code, lang_code)
        await query.edit_message_text(f"✅ Preferred language set to *{lang_name}*.", parse_mode="Markdown")
        return
    if data.startswith("ai_clean_"):
        try:
            user_id = query.from_user.id
            user = db.get_user(user_id)
            is_admin = db.is_admin(user_id)
            code_obj = db.get_access_code(user['access_code']) if user and user.get('access_code') else None

            allow_clean = 1
            if not is_admin:
                if user and user.get('allow_ai_clean') is not None:
                    allow_clean = user['allow_ai_clean']
                elif code_obj and code_obj.get('allow_ai_clean') is not None:
                    allow_clean = code_obj['allow_ai_clean']

            if not allow_clean:
                await query.answer("⛔ Access Restricted: AI Clean is disabled.", show_alert=True)
                await query.message.reply_text("⛔ *Access Restricted*\n\nAI Clean feature is currently disabled for your access code/account. Please contact your system administrator to request access.", parse_mode="Markdown")
                return

            log_id = int(data.split("_")[2])
            log_data = db.get_transcription_log_by_id(log_id)
            if not log_data:
                await query.answer("⚠️ Log record expired or not found.", show_alert=True)
                return

            original_text = log_data.get('full_transcript') or log_data.get('transcript_snippet') or ''
            cleaned_text = log_data.get('cleaned_transcript')
            lang_code = log_data.get('language') or 'sa-IN'

            if not cleaned_text:
                await query.answer("⏳ Proofreading with Samshodhana AI...", show_alert=False)
                try:
                    cleaned_text = await ai_clean_transcript(original_text, language_code=lang_code)
                    db.update_cleaned_transcript(log_id, cleaned_text)
                except Exception as clean_err:
                    try:
                        await query.message.reply_text(
                            f"❌ *AI Clean Failed:* {clean_err}\n\nOriginal Text:\n`{original_text}`",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        await query.message.reply_text(
                            f"❌ AI Clean Failed: {clean_err}\n\nOriginal Text:\n{original_text}"
                        )
                    return

            dur = log_data.get('duration_sec', 0.0)
            res_text = (
                f"✨ *{LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript (AI Cleaned):*\n\n"
                f"{cleaned_text}\n\n"
                f"───────────────────\n"
                f"⏱️ Duration: `{dur:.1f}s` | ✨ Phonetic Proofread (Devanagari)"
            )
            clean_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📋 Copy Cleaned Text", callback_data=f"copy_clean_{log_id}"),
                    InlineKeyboardButton("🌐 Transliterate", url=get_transliterator_bot_url(log_id))
                ]
            ])
            try:
                await query.message.reply_text(
                    res_text,
                    parse_mode="Markdown",
                    reply_markup=clean_kb
                )
            except Exception as md_err:
                logger.warning(f"Markdown reply failed in AI Clean ({md_err}), using plain text fallback")
                plain_res = (
                    f"✨ {LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript (AI Cleaned):\n\n"
                    f"{cleaned_text}\n\n"
                    f"───────────────────\n"
                    f"⏱️ Duration: {dur:.1f}s | ✨ Phonetic Proofread (Devanagari)"
                )
                await query.message.reply_text(
                    plain_res,
                    reply_markup=clean_kb
                )
        except Exception as e:
            logger.error(f"Error executing AI Clean: {e}")
        return

    if data.startswith("ai_assist_"):
        try:
            user_id = query.from_user.id
            user = db.get_user(user_id)
            is_admin = db.is_admin(user_id)
            code_obj = db.get_access_code(user['access_code']) if user and user.get('access_code') else None

            allow_assist = 1
            if not is_admin:
                if user and user.get('allow_ai_assist') is not None:
                    allow_assist = user['allow_ai_assist']
                elif code_obj and code_obj.get('allow_ai_assist') is not None:
                    allow_assist = code_obj['allow_ai_assist']

            if not allow_assist:
                await query.answer("⛔ Access Restricted: AI Assist is disabled.", show_alert=True)
                await query.message.reply_text("⛔ *Access Restricted*\n\nAI Assist feature is currently disabled for your access code/account. Please contact your system administrator to request access.", parse_mode="Markdown")
                return

            log_id = int(data.split("_")[2])
            log_data = db.get_transcription_log_by_id(log_id)
            if not log_data:
                await query.answer("⚠️ Log record expired or not found.", show_alert=True)
                return

            original_text = log_data.get('full_transcript') or log_data.get('transcript_snippet') or ''
            audio_path = ""
            lang_code = log_data.get('language') or 'sa-IN'

            await query.answer("🤖 Processing audio with Samshodhana AI...", show_alert=False)
            try:
                assisted_text = await ai_assist_audio_transcript(audio_path, original_text, language_code=lang_code)
                db.update_assisted_transcript(log_id, assisted_text)
            except Exception as assist_err:
                try:
                    await query.message.reply_text(
                        f"❌ *AI Assist Failed:* {assist_err}\n\nOriginal Text:\n`{original_text}`",
                        parse_mode="Markdown"
                    )
                except Exception:
                    await query.message.reply_text(
                        f"❌ AI Assist Failed: {assist_err}\n\nOriginal Text:\n{original_text}"
                    )
                return

            dur = log_data.get('duration_sec', 0.0)
            res_text = (
                f"🤖 *{LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript (AI Assist - Audio Verified):*\n\n"
                f"{assisted_text}\n\n"
                f"───────────────────\n"
                f"⏱️ Duration: `{dur:.1f}s` | 🎙️ Audio-Acoustic Proofread (Devanagari)"
            )
            assist_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📋 Copy Assisted Text", callback_data=f"copy_clean_{log_id}"),
                    InlineKeyboardButton("🌐 Transliterate", url=get_transliterator_bot_url(log_id))
                ]
            ])
            try:
                await query.message.reply_text(
                    res_text,
                    parse_mode="Markdown",
                    reply_markup=assist_kb
                )
            except Exception as md_err:
                logger.warning(f"Markdown reply failed in AI Assist ({md_err}), using plain text fallback")
                plain_res = (
                    f"🤖 {LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript (AI Assist - Audio Verified):\n\n"
                    f"{assisted_text}\n\n"
                    f"───────────────────\n"
                    f"⏱️ Duration: {dur:.1f}s | 🎙️ Audio-Acoustic Proofread (Devanagari)"
                )
                await query.message.reply_text(
                    plain_res,
                    reply_markup=assist_kb
                )
        except Exception as e:
            logger.error(f"Error executing AI Assist: {e}")
        return

    if data.startswith("toggle_iast_"):
        try:
            log_id = int(data.split("_")[2])
            log_data = db.get_transcription_log_by_id(log_id)
            if not log_data:
                await query.edit_message_text("⚠️ Log record expired or not found.")
                return

            current_msg_text = query.message.text or ""
            active_text = log_data.get('full_transcript') or log_data.get('transcript_snippet') or ''
            header_title = f"📜 *{LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript (Raw STT"

            is_currently_iast = "IAST" in current_msg_text

            if is_currently_iast:
                target_text = active_text
                title = f"{header_title} - Devanagari):*"
                next_is_iast = False
            else:
                target_text = active_text
                title = f"{header_title} - IAST Transliteration):*"
                next_is_iast = True

            dur = log_data.get('duration_sec', 0.0)
            res_text = (
                f"{title}\n\n"
                f"{target_text}\n\n"
                f"───────────────────\n"
                f"⏱️ Duration: `{dur:.1f}s`"
            )
            try:
                await query.edit_message_text(
                    res_text,
                    parse_mode="Markdown",
                    reply_markup=get_transcription_action_keyboard(log_id)
                )
            except Exception as md_err:
                logger.warning(f"Markdown edit failed in toggle_iast ({md_err}), using plain text fallback")
                plain_title = title.replace("*", "")
                plain_res = (
                    f"{plain_title}\n\n"
                    f"{target_text}\n\n"
                    f"───────────────────\n"
                    f"⏱️ Duration: {dur:.1f}s"
                )
                await query.edit_message_text(
                    plain_res,
                    reply_markup=get_transcription_action_keyboard(log_id)
                )
        except Exception as e:
            logger.error(f"Error toggling IAST script: {e}")
        return

    if data.startswith("copy_text_") or data.startswith("copy_clean_"):
        try:
            log_id = int(data.split("_")[2])
            log_data = db.get_transcription_log_by_id(log_id)
            if log_data:
                if data.startswith("copy_clean_"):
                    txt = log_data.get('assisted_transcript') or log_data.get('cleaned_transcript') or ''
                else:
                    txt = log_data.get('full_transcript') or log_data.get('transcript_snippet') or ''
                if txt:
                    try:
                        await query.message.reply_text(f"`{txt}`", parse_mode="Markdown")
                    except Exception:
                        await query.message.reply_text(txt)
        except Exception as e:
            logger.error(f"Error sending copy snippet: {e}")
        return

    if not db.is_admin(user_id):
        await query.edit_message_text("⛔ Admin access required.")
        return

    if data == "admin_menu":
        dash_text = get_admin_dashboard_text(user.first_name or "Admin")
        await query.edit_message_text(dash_text, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_list_codes":
        codes = db.list_access_codes()
        if not codes:
            txt = "📋 *No Access Codes Found.* Use button below to create one."
        else:
            lines = ["📋 *Active Access Codes:*"]
            for c in codes:
                status_icon = "✅" if c['status'] == 'active' else "⛔"
                used_m = math.ceil(c['daily_used_seconds'] / 60)
                max_m = math.ceil(c['daily_max_seconds'] / 60)
                lines.append(f"{status_icon} `{c['code']}` — {used_m}/{max_m} mins today ({c['request_count']} requests)")
            txt = "\n".join(lines)
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_create_help":
        txt = "➕ *Create Access Code:*\nUse command `/createcode <CODE> [daily_max_minutes]`\nExample: `/createcode GURUKUL2026 120`"
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_team_report":
        report = db.get_team_usage_report()
        if not report:
            txt = "📊 *No Active Users Yet.*"
        else:
            lines = ["📊 *User Activity Report:*"]
            for u in report:
                tot_m = math.ceil(u['total_used_seconds'] / 60)
                lines.append(f"• *{u['first_name']}* (@{u['username'] or 'N/A'}) — `{u['access_code']}` — {tot_m} mins ({u['request_count']} requests)")
            txt = "\n".join(lines)
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_revoke_prompt":
        txt = "⛔ *Revoke Code:*\nUse command `/revokecode <CODE>` to disable an access code."
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_prompts_menu":
        assist_status = "🟢 Custom" if db.is_ai_prompt_customized("ai_assist") else "🔵 Default"
        clean_status = "🟢 Custom" if db.is_ai_prompt_customized("ai_clean") else "🔵 Default"
        
        assist_p = db.get_ai_assist_prompt()
        clean_p = db.get_ai_clean_prompt()

        txt = (
            f"📝 *AI System Prompts Management*\n\n"
            f"🤖 *AI Assist Prompt (Audio + Text)* — [{assist_status}]\n"
            f"```text\n{assist_p[:350]}{'...' if len(assist_p)>350 else ''}\n```\n"
            f"✨ *AI Clean Prompt (Text Only)* — [{clean_status}]\n"
            f"```text\n{clean_p[:350]}{'...' if len(clean_p)>350 else ''}\n```\n\n"
            f"💡 *How to Edit Prompts:*\n"
            f"• `/setprompt assist YOUR_PROMPT` — set AI Assist prompt\n"
            f"• `/setprompt clean YOUR_PROMPT` — set AI Clean prompt\n"
            f"• `/getprompt` — view full active prompts\n"
            f"• `/resetprompt assist` or `clean` — restore default"
        )
        prompt_kb = [
            [
                InlineKeyboardButton("🔄 Reset AI Assist Prompt", callback_data="admin_reset_prompt_assist"),
                InlineKeyboardButton("🔄 Reset AI Clean Prompt", callback_data="admin_reset_prompt_clean")
            ],
            [
                InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="admin_menu")
            ]
        ]
        await query.edit_message_text(txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(prompt_kb))
    elif data == "admin_reset_prompt_assist":
        db.reset_ai_prompt("ai_assist")
        await query.answer("✅ AI Assist prompt reset to Default!", show_alert=True)
        await query.edit_message_text("🔄 *AI Assist prompt reset to Default.* Click `/getprompt` to view.", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "admin_reset_prompt_clean":
        db.reset_ai_prompt("ai_clean")
        await query.answer("✅ AI Clean prompt reset to Default!", show_alert=True)
        await query.edit_message_text("🔄 *AI Clean prompt reset to Default.* Click `/getprompt` to view.", parse_mode="Markdown", reply_markup=get_admin_keyboard())
    elif data == "menu_otherbots":
        other_bots_text = (
            "🤖 *Samshodhanam Telegram Bot Family*\n\n"
            "Explore our suite of specialized Telegram bots for Sanskrit & Indic literature:\n\n"
            "• 📸 *OCR Bot:* High-accuracy image/PDF text extraction & script conversion.\n"
            "• 🎙️ *Speech-to-Text Bot:* Sanskrit audio & voice message transcription.\n"
            "• 🌐 *Transliterator Bot:* Instant 1-tap script transliteration across 20+ Indic scripts.\n\n"
            "_Tap any bot button below to open and start using it directly in Telegram!_"
        )
        await query.edit_message_text(other_bots_text, parse_mode="Markdown", reply_markup=build_other_bots_keyboard())
    elif data == "menu_support":
        support_email = os.getenv("SUPPORT_EMAIL", "samshodhanamandiram@gmail.com")
        tg_handle = (os.getenv("SUPPORT_TELEGRAM_HANDLE") or "").lstrip('@')
        
        support_text = (
            "💬 *Contact & Support — Samshodhana Mandiram*\n\n"
            "If you face any issues, have questions, or need assistance:\n\n"
            f"📧 *Support Email:* `{support_email}`\n"
            "🌐 *Website:* [samshodhanam.in](https://samshodhanam.in)\n\n"
            "_We welcome your feedback, bug reports, and feature requests!_"
        )
        
        support_buttons = []
        if tg_handle:
            support_buttons.append([InlineKeyboardButton("💬 Message Support on Telegram", url=f"https://t.me/{tg_handle}")])
        
        await query.edit_message_text(support_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(support_buttons))

# ─── Audio & Voice Handling ───────────────────────────────────────────────────

async def process_large_audio_background(
    file_path: str,
    original_filename: str,
    user_id: int,
    user_data: dict,
    status_msg_id: int,
    chat_id: int,
    ext: str,
    duration: float,
    file_size: int,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Background worker that chunks a large audio file into 60s segments,
    transcribes each chunk, reports progress to the Telegram user, merges the results,
    creates a formatted output text file, sends the document, and provides interactive buttons.
    """
    chunk_paths = []
    try:
        # Re-fetch user_data fresh from DB to get the latest preferred_language/script
        user_data = db.get_user(user_id) or user_data

        raw_lang = user_data.get('preferred_language', 'sa-IN') if user_data else 'sa-IN'
        if db.is_language_enabled(raw_lang):
            lang_code = raw_lang
        else:
            def_code = db.get_default_language()
            lang_code = f"{def_code}-IN" if not def_code.endswith("-IN") else def_code

        # Step 1: Chunk audio
        logger.info(f"[Large Audio] Chunking '{file_path}' (duration={duration:.1f}s, size={file_size} bytes)")
        chunk_paths = split_audio_into_chunks(file_path, chunk_duration_sec=CHUNK_DURATION_SEC, output_dir=TEMP_DIR)
        total_chunks = len(chunk_paths)

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"🧩 *Audio chunked into {total_chunks} segments.* Starting transcription (0/{total_chunks})...",
                parse_mode="Markdown"
            )
        except Exception as edit_err:
            logger.warning(f"Failed to update initial chunk status: {edit_err}")

        # Step 2: Transcribe each chunk
        transcripts = []
        total_latency_ms = 0
        import time as t_mod
        last_edit_time = t_mod.time()

        for idx, chunk_file in enumerate(chunk_paths, 1):
            c_transcript, c_latency = await transcribe_audio_file(chunk_file, language_code=lang_code, stt_url=STT_URL)
            if c_transcript.strip():
                transcripts.append(c_transcript.strip())
            total_latency_ms += c_latency

            # Update progress message (throttled to avoid Telegram API rate limits)
            now = t_mod.time()
            if (now - last_edit_time > 2.0) or idx == total_chunks:
                pct = int((idx / total_chunks) * 100)
                last_edit_time = now
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=status_msg_id,
                        text=f"⏳ *Transcribing audio ({pct}% complete)*\nChunk {idx} of {total_chunks} finished...",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        # Step 3: Merge transcripts
        merged_raw = " ".join(transcripts).strip()
        if not merged_raw:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_id,
                    text="⚠️ *No clear speech detected in large audio file.* Please speak clearly.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            return

        import datetime

        # Update Usage & Database Log
        db.update_usage(user_id, duration)
        access_code = user_data['access_code'] if user_data else 'ADMIN'
        log_id = db.log_transcription(
            user_id,
            access_code,
            lang_code,
            duration,
            len(merged_raw),
            merged_raw,
            full_transcript=merged_raw,
            audio_filename=""
        )

        user_script = user_data.get('preferred_script', 'devanagari') if user_data else 'devanagari'
        display_text = merged_raw
        is_iast = False
        if user_script != 'devanagari':
            display_text = merged_raw
            if user_script == 'iast':
                is_iast = True

        

        # Step 4: Create Output Text File
        timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        txt_filename = f"Samshodhana_STT_Transcript_{user_id}_{timestamp_str}.txt"
        txt_filepath = os.path.join(TEMP_DIR, txt_filename)

        header_lines = [
            "==================================================",
            "   SAMSHODHANA SANSKRIT STT TRANSCRIPTION REPORT",
            "==================================================",
            f"Original File : {original_filename}",
            f"User ID       : {user_id}",
            f"Timestamp     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Audio Duration: {duration:.1f} seconds",
            f"Total Chunks  : {total_chunks} segments",
            f"Language      : {lang_code}",
            f"Output Script : {script_title}",
            "==================================================",
            "",
            "--- FULL TRANSCRIPT ---",
            "",
            display_text,
            "",
            "=================================================="
        ]

        with open(txt_filepath, "w", encoding="utf-8") as tf:
            tf.write("\n".join(header_lines))

        # Step 5: Send Document File to Telegram User
        with open(txt_filepath, "rb") as tf:
            await context.bot.send_document(
                chat_id=chat_id,
                document=tf,
                filename=txt_filename,
                caption=f"📄 *Full Transcript Document* ({total_chunks} chunks, {duration:.1f}s duration)",
                parse_mode="Markdown"
            )

        # Cleanup output txt file
        if os.path.exists(txt_filepath):
            try:
                os.remove(txt_filepath)
            except Exception:
                pass

        # Step 6: Send / Edit Summary Telegram Message with Actions
        preview_text = display_text if len(display_text) <= 2500 else display_text[:2500] + "...\n\n*(Full text available in attached document above)*"

        res_text = (
            f"📜 *{LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript  — Merged ({total_chunks} Chunks):*\n\n"
            f"{preview_text}\n\n"
            f"───────────────────\n"
            f"⏱️ Total Duration: `{duration:.1f}s` | 🧩 Chunks: `{total_chunks}` | ⚡ Latency: `{total_latency_ms}ms`"
        )

        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=res_text,
                parse_mode="Markdown",
                reply_markup=get_transcription_action_keyboard(log_id)
            )
        except Exception as md_err:
            logger.warning(f"Markdown edit failed for large transcription ({md_err}), using plain text fallback")
            plain_res = (
                f"📜 {LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript  — Merged ({total_chunks} Chunks):\n\n"
                f"{preview_text}\n\n"
                f"───────────────────\n"
                f"⏱️ Total Duration: {duration:.1f}s | 🧩 Chunks: {total_chunks} | ⚡ Latency: {total_latency_ms}ms"
            )
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=plain_res,
                reply_markup=get_transcription_action_keyboard(log_id)
            )

    except Exception as err:
        logger.error(f"[Large Audio Processing Error] {err}", exc_info=True)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"❌ *Background Chunked Transcription Failed:* {str(err)}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    finally:
        cleanup_chunk_files(chunk_paths, original_file=file_path)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass


async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # Access Verification
    if not db.is_admin(user_id):
        is_ok, msg = db.check_user_access(user_id)
        if not is_ok:
            await update.message.reply_text(f"⚠️ {msg}")
            return

    msg = await update.message.reply_text("⏳ *Processing audio with Samshodhana STT...*", parse_mode="Markdown")

    try:
        # Determine File Source (Voice vs Audio File)
        original_filename = "audio.wav"
        if update.message.voice:
            tg_file = await update.message.voice.get_file()
            ext = ".ogg"
            original_filename = f"voice_note_{update.message.message_id}.ogg"
        elif update.message.audio:
            tg_file = await update.message.audio.get_file()
            original_filename = update.message.audio.file_name or "audio.wav"
            ext = os.path.splitext(original_filename)[1] or ".wav"
        elif update.message.document:
            tg_file = await update.message.document.get_file()
            original_filename = update.message.document.file_name or "audio.wav"
            ext = os.path.splitext(original_filename)[1] or ".wav"
        else:
            await msg.edit_text("Unsupported audio format.")
            return

        file_path = os.path.join(TEMP_DIR, f"{user_id}_{update.message.message_id}{ext}")
        await tg_file.download_to_drive(file_path)

        duration = get_audio_duration(file_path)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        user_data = db.get_user(user_id)

        # Check if file is large (duration > 60s or size > 10MB)
        if duration > LARGE_AUDIO_DURATION_THRESHOLD or file_size > LARGE_AUDIO_SIZE_THRESHOLD:
            await msg.edit_text(
                f"⏳ *Large audio file detected ({duration:.1f}s / {file_size / (1024*1024):.1f} MB).* Chunking & transcribing in background...",
                parse_mode="Markdown"
            )
            asyncio.create_task(
                process_large_audio_background(
                    file_path=file_path,
                    original_filename=original_filename,
                    user_id=user_id,
                    user_data=user_data,
                    status_msg_id=msg.message_id,
                    chat_id=update.effective_chat.id,
                    ext=ext,
                    duration=duration,
                    file_size=file_size,
                    context=context
                )
            )
            return

        raw_lang = user_data.get('preferred_language', 'sa-IN') if user_data else 'sa-IN'
        if db.is_language_enabled(raw_lang):
            lang_code = raw_lang
        else:
            def_code = db.get_default_language()
            lang_code = f"{def_code}-IN" if not def_code.endswith("-IN") else def_code

        # Transcribe audio
        transcript, latency_ms = await transcribe_audio_file(file_path, language_code=lang_code, stt_url=STT_URL)

        # Cleanup local audio temp file immediately for privacy
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

        if not transcript.strip():
            await msg.edit_text("⚠️ *No clear speech detected in audio clip.* Please speak clearly.", parse_mode="Markdown")
            return

        # Update Usage & Log
        db.update_usage(user_id, duration)
        access_code = user_data['access_code'] if user_data else 'ADMIN'
        log_id = db.log_transcription(user_id, access_code, lang_code, duration, len(transcript), transcript, full_transcript=transcript, audio_filename="")

        user_script = user_data.get('preferred_script', 'devanagari') if user_data else 'devanagari'
        display_text = transcript
        is_iast = False
        if user_script != 'devanagari':
            display_text = transcript
            if user_script == 'iast':
                is_iast = True

        
        res_text = (
            f"📜 *{LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript :*\n\n"
            f"{display_text}\n\n"
            f"───────────────────\n"
            f"⏱️ Duration: `{duration:.1f}s` | ⚡ Latency: `{latency_ms}ms`"
        )
        try:
            await msg.edit_text(res_text, parse_mode="Markdown", reply_markup=get_transcription_action_keyboard(log_id))
        except Exception as md_err:
            logger.warning(f"Markdown edit failed, using plain text fallback: {md_err}")
            plain_res = (
                f"📜 {LANGUAGES.get(lang_code, 'Sanskrit').split(' ')[0]} Transcript :\n\n"
                f"{display_text}\n\n"
                f"───────────────────\n"
                f"⏱️ Duration: {duration:.1f}s | ⚡ Latency: {latency_ms}ms"
            )
            await msg.edit_text(plain_res, reply_markup=get_transcription_action_keyboard(log_id))

    except Exception as e:
        logger.error(f"Audio processing error: {e}")
        try:
            await msg.edit_text(f"❌ *Transcription Failed:* {str(e)}", parse_mode="Markdown")
        except Exception:
            await msg.edit_text(f"❌ Transcription Failed: {str(e)}")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = (update.message.text or "").strip()

    if not text:
        return

    code_input = text.upper()
    code_data = db.get_access_code(code_input)

    if code_data and code_data['status'] == 'active':
        db.register_user(user_id, user.username or "", user.first_name or "", code_input)
        await update.message.reply_text(
            f"✅ *Access Granted!*\n"
            f"Access Code `{code_input}` activated.\n\n"
            f"🎙️ *Send me any voice note or audio file* now to transcribe it into Sanskrit!",
            parse_mode="Markdown"
        )
        return

    user_data = db.get_user(user_id)
    if user_data:
        lang_name = LANGUAGES.get(user_data.get('preferred_language', 'sa-IN'), 'Sanskrit')
        await update.message.reply_text(
            f"🎙️ Send a **voice note** or **audio clip** (.ogg, .mp3, .wav) to transcribe into {lang_name}.\n"
            f"Use `/menu` or open the command menu to switch language (`/lang`) or script (`/script`).",
            parse_mode="Markdown"
        )
    elif db.is_admin(user_id):
        await update.message.reply_text(
            "👑 You are an Admin. Use `/admin` to manage access codes, or send a voice/audio message to test STT."
        )
    else:
        await update.message.reply_text(
            "❌ *Invalid Access Code.* Please enter a valid Access Code (e.g. `/code YOUR_CODE`) or ask your admin for one.",
            parse_mode="Markdown"
        )

# ─── Main Runner ──────────────────────────────────────────────────────────────

async def setup_bot_commands(application):
    commands = [
        BotCommand("start", "🎙️ Welcome & Status"),
        BotCommand("lang", "🌐 Select Speech Language"),
        BotCommand("export", "📥 Export History (.txt)"),
        BotCommand("code", "🔑 Activate Access Code"),
        BotCommand("help", "❓ Help & Usage Instructions"),
    ]
    try:
        await application.bot.set_my_commands(commands)
        logger.info("BotFather Chat Command Menu registered successfully!")
    except Exception as e:
        logger.warning(f"Could not register Bot commands: {e}")

async def bot_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for Telegram bot updates."""
    err = context.error
    if isinstance(err, telegram.error.Conflict):
        logger.critical(
            "⚠️ Telegram Conflict Error: Another process is using the same Telegram Bot Token! "
            "Stopping this instance gracefully to prevent endless polling conflicts."
        )
        if context.application and context.application.updater and context.application.updater.is_running:
            context.application.stop_running()
        return

    logger.error("Exception encountered while handling an update:", exc_info=err)

def main():
    token = BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is missing in environment or database settings.")
        print("Please configure TELEGRAM_BOT_TOKEN in .env or via Web Admin Panel.")
        sys.exit(1)

    # Write PID file
    pid_path = os.path.join(os.path.dirname(__file__), "telegram_bot.pid")
    try:
        with open(pid_path, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning(f"Could not write PID file: {e}")

    logger.info(f"Starting Samshodhana Sanskrit STT Telegram Bot (PID {os.getpid()})...")
    request = HTTPXRequest(connect_timeout=20.0, read_timeout=30.0)
    app = ApplicationBuilder().token(token).request(request).post_init(setup_bot_commands).build()

    app.add_error_handler(bot_error_handler)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("code", code_command))
    app.add_handler(CommandHandler("createcode", createcode_command))
    app.add_handler(CommandHandler("revokecode", revokecode_command))
    app.add_handler(CommandHandler("setup", setup_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("setprompt", setprompt_command))
    app.add_handler(CommandHandler("getprompt", getprompt_command))
    app.add_handler(CommandHandler("resetprompt", resetprompt_command))
    app.add_handler(CommandHandler("lang", lang_command))
    app.add_handler(CommandHandler("export", export_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO | filters.Document.ALL, handle_audio_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    print(f"Samshodhana STT Telegram Bot is now running! (PID {os.getpid()})")
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        if os.path.exists(pid_path):
            try:
                os.remove(pid_path)
            except Exception:
                pass

if __name__ == "__main__":
    main()


