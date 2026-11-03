"""
Samshodhanam Transliterator Telegram Bot (Open for All).
Provides instant multiscript transliteration between Devanagari, Kannada, Telugu,
Tamil (with Grantha/superscripts), Malayalam, IAST, ITRANS, SLP1, etc.
Integrates with Speech-to-Text (STT) Telegram Bot via deep-linking (/start stt_<log_id>).
"""

import os
import sys
import logging
import io
import asyncio
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
import telegram
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
    InlineQueryResultArticle, InputTextMessageContent
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, InlineQueryHandler, ContextTypes, filters
)

import bot_db as db
import translit_engine as engine

# Dynamically import STT bot_db to fetch speech transcription logs by ID
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STT_BACKEND_PATH = os.path.join(PROJECT_ROOT, "sanskrit_stt", "backend")
if STT_BACKEND_PATH not in sys.path:
    sys.path.insert(0, STT_BACKEND_PATH)

try:
    import bot_db as stt_db
except Exception:
    stt_db = None

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

BOT_TOKEN = os.getenv("TRANSLITERATOR_BOT_TOKEN") or db.get_setting("transliterator_bot_token", "")
BOT_USERNAME = os.getenv("TRANSLITERATOR_BOT_USERNAME") or db.get_setting("transliterator_bot_username", "TVSM_Translatorator_Bot")

LOG_FILE = os.path.join(os.path.dirname(__file__), "transliterator_bot.log")
logging.basicConfig(
    format="%(asctime)s [TVSM_Translatorator_Bot] %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
logger = logging.getLogger("transliterator_bot")

SUPPORTED_SCRIPTS = {
    'sa': '🕉️ Devanagari',
    'ka': '💛 Kannada',
    'te': '💙 Telugu',
    'ta': '❤️ Tamil',
    'ml': '💚 Malayalam',
    'en': '🔤 IAST',
    'itrans': '🔤 ITRANS',
    'slp1': '🔤 SLP1'
}

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
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_script_grid_keyboard(prefix: str = "setout_", active_code: str = "ka", payload_suffix: str = ""):
    """Generate an Inline Keyboard grid for script selection."""
    keyboard = []
    row = []
    for code, label in SUPPORTED_SCRIPTS.items():
        is_active = (code == active_code)
        mark = "✅ " if is_active else ""
        btn_text = f"{mark}{label}"
        cb_data = f"{prefix}{code}"
        if payload_suffix:
            cb_data += f"_{payload_suffix}"
        row.append(InlineKeyboardButton(btn_text, callback_data=cb_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if prefix == "setout_":
        keyboard.append([InlineKeyboardButton("🤖 Other Telegram Bots", callback_data="menu_otherbots")])
        keyboard.append([InlineKeyboardButton("💬 Contact & Support", callback_data="menu_support")])
    return InlineKeyboardMarkup(keyboard)

def get_action_keyboard(user_id: int, current_out: str):
    """Generate action buttons placed below transliterated responses."""
    pref = db.get_user_pref(user_id)
    in_s = pref['input_script']
    kb = [
        [
            InlineKeyboardButton("🔁 Swap Scripts", callback_data="swap_scripts"),
            InlineKeyboardButton("🔀 Change Script", callback_data="open_script_menu")
        ],
        [
            InlineKeyboardButton("📁 Get .txt File", callback_data=f"dl_file_{current_out}")
        ]
    ]
    return InlineKeyboardMarkup(kb)

# --- Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start and deep-linked STT payload (/start stt_<log_id>)."""
    user = update.effective_user
    args = context.args

    # Check deep-link payload from STT bot (e.g. /start stt_1234)
    if args and args[0].startswith("stt_"):
        try:
            log_id = int(args[0].replace("stt_", ""))
            transcript_text = None

            if stt_db:
                log_entry = stt_db.get_transcription_log_by_id(log_id)
                if log_entry:
                    transcript_text = log_entry.get("cleaned_transcript") or log_entry.get("assisted_transcript") or log_entry.get("full_transcript") or log_entry.get("transcript_snippet")

            if transcript_text:
                # Save temp transcript in user context data
                context.user_data['stt_text'] = transcript_text
                context.user_data['stt_log_id'] = log_id

                snippet = transcript_text[:150] + "..." if len(transcript_text) > 150 else transcript_text
                msg = (
                    f"🎙️ *Text Received from Speech-to-Text Bot!*\n\n"
                    f"📝 *Preview:* _{snippet}_\n\n"
                    f"👉 *Select your desired target script for transliteration:*"
                )
                reply_markup = get_script_grid_keyboard(prefix="transstt_", payload_suffix=str(log_id))
                await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
                return
            else:
                await update.message.reply_text("⚠️ Could not load transcript text from Speech-to-Text log. Please try copying the text directly.")
                return
        except Exception as e:
            logger.error(f"Error reading STT deep-link payload: {e}")

    pref = db.get_user_pref(user.id)
    in_name = SUPPORTED_SCRIPTS.get(pref['input_script'], '🔍 Auto-Detect')
    out_name = SUPPORTED_SCRIPTS.get(pref['output_script'], '💛 Kannada')

    welcome_text = (
        f"👋 *Welcome to Samshodhanam Multiscript Transliterator!*\n\n"
        f"Transliterate Sanskrit and Indic texts instantly across Devanagari, Kannada, Telugu, Tamil (with superscripts ² ³ ⁴), Malayalam, IAST, ITRANS, and SLP1.\n\n"
        f"⚙️ *Current Settings:*\n"
        f"• *Input Script:* {in_name}\n"
        f"• *Output Script:* {out_name}\n\n"
        f"💡 *How to use:*\n"
        f"1️⃣ Send any text message to convert instantly.\n"
        f"2️⃣ Upload a `.txt` file to transliterate full documents.\n"
        f"3️⃣ Tap buttons below or send `/script` to change output script.\n"
        f"4️⃣ Use `@{(context.bot.username or BOT_USERNAME)} <text>` in any chat!"
    )
    reply_markup = get_script_grid_keyboard(prefix="setout_", active_code=pref['output_script'])
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "📖 *Samshodhanam Transliterator Help & Usage Guide*\n\n"
        "• `/start` — Main menu & script settings\n"
        "• `/script` — Choose input & output scripts\n"
        "• `/swap` — Swap input and output scripts\n"
        "• `/convert <from> <to> <text>` — Direct one-shot conversion\n\n"
        "*Supported Scripts:*\n"
        "🕉️ Devanagari (`sa`)\n"
        "💛 Kannada (`ka`)\n"
        "💙 Telugu (`te`)\n"
        "❤️ Tamil (`ta` — with superscripts ² ³ ⁴ and Grantha)\n"
        "💚 Malayalam (`ml`)\n"
        "🔤 English / IAST (`en`)\n"
        "🔤 ITRANS (`itrans`)\n"
        "🔤 SLP1 (`slp1`)\n\n"
        "*Text File Transliteration:*\n"
        "Simply send a `.txt` file to receive a converted document file!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /swap command."""
    user_id = update.effective_user.id
    pref = db.get_user_pref(user_id)
    in_s = pref['input_script']
    out_s = pref['output_script']
    if in_s == 'auto':
        in_s = 'sa'
    db.set_user_pref(user_id, input_script=out_s, output_script=in_s)
    in_name = SUPPORTED_SCRIPTS.get(out_s, out_s)
    out_name = SUPPORTED_SCRIPTS.get(in_s, in_s)
    await update.message.reply_text(f"🔁 *Scripts Swapped!*\nInput: *{in_name}* ⇄ Output: *{out_name}*", parse_mode="Markdown")

async def script_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /script command."""
    user_id = update.effective_user.id
    pref = db.get_user_pref(user_id)
    msg = "🔀 *Select Desired Output Script:*"
    reply_markup = get_script_grid_keyboard(prefix="setout_", active_code=pref['output_script'])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /convert <from> <to> <text>."""
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("⚠️ Usage: `/convert <from_script> <to_script> <text>`\nExample: `/convert sa ka नमस्ते`", parse_mode="Markdown")
        return
    from_s = context.args[0].lower()
    to_s = context.args[1].lower()
    text = " ".join(context.args[2:])
    converted = engine.convert_script(text, from_s, to_s)
    await update.message.reply_text(f"🔤 *Converted ({from_s} ➔ {to_s}):*\n\n{converted}", parse_mode="Markdown")

# --- Callback Query Handler ---

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("setout_"):
        target_script = data.replace("setout_", "")
        db.set_user_pref(user_id, output_script=target_script)
        script_label = SUPPORTED_SCRIPTS.get(target_script, target_script)
        reply_markup = get_script_grid_keyboard(prefix="setout_", active_code=target_script)
        await query.edit_message_text(f"✅ *Default Output Script set to: {script_label}*\n\nSend any text message or file now to select your script!", parse_mode="Markdown", reply_markup=reply_markup)

    elif data.startswith("dotrans_") or data.startswith("transstt_"):
        if data.startswith("dotrans_"):
            target_script = data.replace("dotrans_", "")
            log_id = None
        else:
            parts = data.split("_")
            target_script = parts[1]
            log_id = int(parts[2]) if len(parts) > 2 else context.user_data.get('stt_log_id')

        text = context.user_data.get('pending_text') or context.user_data.get('stt_text')
        if not text and stt_db and log_id:
            log_entry = stt_db.get_transcription_log_by_id(log_id)
            if log_entry:
                text = log_entry.get("cleaned_transcript") or log_entry.get("assisted_transcript") or log_entry.get("full_transcript") or log_entry.get("transcript_snippet")

        if not text:
            await query.edit_message_text("⚠️ No pending text found. Please send your text message or file again.")
            return

        db.set_user_pref(user_id, output_script=target_script)
        converted = engine.convert_script(text, 'auto', target_script)
        script_label = SUPPORTED_SCRIPTS.get(target_script, target_script)
        db.log_transliteration(user_id, 'auto', target_script, len(text), source='user_selection')

        header = f"✨ *Transliterated Result ({script_label}):*\n\n"

        if len(header + converted) <= 4000:
            await query.edit_message_text(header + converted, parse_mode="Markdown", reply_markup=get_action_keyboard(user_id, target_script))
        else:
            await query.edit_message_text(f"✨ *Transliteration completed ({script_label})!* Sending output messages & text document...", parse_mode="Markdown")
            for chunk in [converted[i:i+3800] for i in range(0, len(converted), 3800)]:
                await query.message.reply_text(chunk)
            
            bio = io.BytesIO(converted.encode("utf-8"))
            fname = context.user_data.get('pending_filename') or "transliterated"
            base_name = fname.rsplit(".", 1)[0]
            bio.name = f"{base_name}_{target_script}.txt"
            await query.message.reply_document(document=bio, caption=f"📁 Transliterated Text Document ({script_label})")

    elif data.startswith("dl_file_"):
        target_script = data.replace("dl_file_", "")
        text = context.user_data.get('pending_text') or context.user_data.get('stt_text')
        if not text:
            await query.answer("⚠️ Text session expired. Send your message again.", show_alert=True)
            return
        converted = engine.convert_script(text, 'auto', target_script)
        script_label = SUPPORTED_SCRIPTS.get(target_script, target_script)
        bio = io.BytesIO(converted.encode("utf-8"))
        bio.name = f"transliterated_{target_script}.txt"
        await query.message.reply_document(document=bio, caption=f"📁 Transliterated Document ({script_label})")

    elif data == "swap_scripts":
        pref = db.get_user_pref(user_id)
        in_s = pref['input_script']
        out_s = pref['output_script']
        if in_s == 'auto':
            in_s = 'sa'
        db.set_user_pref(user_id, input_script=out_s, output_script=in_s)
        await query.message.reply_text(f"🔁 *Scripts Swapped!* Input: {out_s} ➔ Output: {in_s}", parse_mode="Markdown")

    elif data == "open_script_menu":
        text = context.user_data.get('pending_text') or context.user_data.get('stt_text')
        if text:
            msg = "🔀 *Select Target Script for Transliteration:*"
            reply_markup = get_script_grid_keyboard(prefix="dotrans_")
            await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            pref = db.get_user_pref(user_id)
            reply_markup = get_script_grid_keyboard(prefix="setout_", active_code=pref['output_script'])
            await query.message.reply_text("🔀 *Select Output Script:*", parse_mode="Markdown", reply_markup=reply_markup)

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
        support_buttons.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")])
        
        await query.edit_message_text(support_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(support_buttons))

    elif data == "menu_main":
        pref = db.get_user_pref(user_id)
        reply_markup = get_script_grid_keyboard(prefix="setout_", active_code=pref['output_script'])
        welcome_text = (
            "👋 *Welcome to Samshodhanam Multiscript Transliterator!*\n\n"
            "Transliterate Sanskrit and Indic texts instantly across Devanagari, Kannada, Telugu, Tamil, Malayalam, IAST, ITRANS, and SLP1.\n\n"
            "👉 *Select your preferred output script or tap Other Telegram Bots below:*"
        )
        await query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)

# --- Text & File Handlers ---

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive text message and prompt user to choose target output script."""
    if not update.message or not update.message.text:
        return

    text = update.message.text
    if text.startswith("/"):
        return

    context.user_data['pending_text'] = text
    context.user_data['pending_type'] = 'text'

    snippet = text[:120] + "..." if len(text) > 120 else text
    msg = (
        f"📝 *Text Received!*\n"
        f"Preview: _{snippet}_\n\n"
        f"👉 *Select your desired output script:*"
    )
    pref = db.get_user_pref(update.effective_user.id)
    reply_markup = get_script_grid_keyboard(prefix="dotrans_", active_code=pref['output_script'])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive .txt document and prompt user to choose target output script."""
    doc = update.message.document
    if not doc or not doc.file_name.endswith(".txt"):
        await update.message.reply_text("⚠️ Please upload a `.txt` text file for document transliteration.", parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text("⏳ *Reading text file...*", parse_mode="Markdown")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        content = file_bytes.decode("utf-8", errors="replace")

        context.user_data['pending_text'] = content
        context.user_data['pending_filename'] = doc.file_name
        context.user_data['pending_type'] = 'file'

        msg = (
            f"📁 *Text Document Received:* `{doc.file_name}` ({len(content)} characters)\n\n"
            f"👉 *Select your desired output script for transliteration:*"
        )
        pref = db.get_user_pref(update.effective_user.id)
        reply_markup = get_script_grid_keyboard(prefix="dotrans_", active_code=pref['output_script'])

        await status_msg.delete()
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"File reading error: {e}")
        await status_msg.edit_text("❌ Error reading text file. Make sure it is UTF-8 encoded plain text.")

# --- Inline Query Handler ---

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Support inline @TVSM_Translatorator_Bot <text> in any chat."""
    query = update.inline_query.query
    if not query:
        return

    results = []
    top_scripts = [('ka', 'Kannada'), ('sa', 'Devanagari'), ('te', 'Telugu'), ('ta', 'Tamil'), ('en', 'IAST')]

    for code, label in top_scripts:
        converted = engine.convert_script(query, 'auto', code)
        results.append(
            InlineQueryResultArticle(
                id=f"trans_{code}_{hash(query)}",
                title=f"{label}: {converted[:40]}",
                description=converted,
                input_message_content=InputTextMessageContent(f"🔤 *{label}:*\n{converted}", parse_mode="Markdown")
            )
        )

    await update.inline_query.answer(results, cache_time=10)


def main():
    if not BOT_TOKEN:
        logger.error("TRANSLITERATOR_BOT_TOKEN missing in environment or database. Set it in .env or Admin Hub.")
        sys.exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("script", script_command))
    app.add_handler(CommandHandler("settings", script_command))
    app.add_handler(CommandHandler("swap", swap_command))
    app.add_handler(CommandHandler("convert", convert_command))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    logger.info("Transliterator Bot started polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
