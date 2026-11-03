"""
Samshodhanam Telegram OCR Bot.
High-Accuracy OCR Engine + Unlimited PDF support + Script Transliteration.
"""

import os
import sys
import io
import time
import uuid
import logging
import asyncio
from typing import Dict, Any, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import telegram
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

try:
    import apps.ocr_bot.config as config
except ImportError:
    import config

try:
    import apps.ocr_bot.ocr_service as ocr_service
except ImportError:
    import ocr_service

try:
    import apps.ocr_bot.translit_bridge as translit_bridge
except ImportError:
    import translit_bridge


LOG_FILE = os.path.join(config.BOT_DIR, "telegram_ocr_bot.log")
PID_FILE = os.path.join(config.BOT_DIR, "telegram_ocr_bot.pid")
CHILD_PID_FILE = os.path.join(config.BOT_DIR, "telegram_ocr_bot_child.pid")
STOP_FILE = os.path.join(config.BOT_DIR, "telegram_ocr_bot.stop")

try:
    with open(CHILD_PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    if not os.path.exists(PID_FILE):
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
except Exception:
    pass

logging.basicConfig(
    format="%(asctime)s [Samshodhana_OCR_Bot] %(levelname)s %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
logger = logging.getLogger("ocr_bot")

# In-memory store for recent OCR job outputs: job_id -> { 'text': str, 'filename': str, 'chat_id': int }
JOB_CACHE: Dict[str, Dict[str, Any]] = {}
MAX_CACHE_SIZE = 200

# User preferences: chat_id -> preferred output script code ('sa', 'ka', 'te', 'ta', 'ml', 'en', 'slp1', 'itrans')
USER_PREFERENCES: Dict[int, str] = {}


def clean_job_cache():
    """AUD2-06: Evicts entries older than 15 minutes (900s) and trims cache if too large."""
    now = time.time()
    ttl = 900  # 15 minutes
    expired = [k for k, v in JOB_CACHE.items() if now - v.get('timestamp', 0) > ttl]
    for k in expired:
        JOB_CACHE.pop(k, None)
    if len(JOB_CACHE) > MAX_CACHE_SIZE:
        keys_to_remove = list(JOB_CACHE.keys())[:50]
        for k in keys_to_remove:
            JOB_CACHE.pop(k, None)


def build_welcome_keyboard() -> InlineKeyboardMarkup:
    """Builds interactive inline keyboard for welcome menu."""
    keyboard = [
        [
            InlineKeyboardButton("📖 How to Use", callback_data="menu_help"),
            InlineKeyboardButton("🌐 Supported Scripts", callback_data="menu_scripts"),
        ],
        [
            InlineKeyboardButton("🔄 Auto Transliterate Output", callback_data="menu_autotrans"),
        ],
        [
            InlineKeyboardButton("⚡ Key Features", callback_data="menu_features"),
            InlineKeyboardButton("🤖 Other Telegram Bots", callback_data="menu_otherbots"),
        ],
        [
            InlineKeyboardButton("💬 Contact & Support", callback_data="menu_support"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_other_bots_keyboard() -> InlineKeyboardMarkup:
    """Builds inline keyboard with direct links to all Samshodhanam Telegram Bots."""
    ocr_uname = getattr(config, 'TELEGRAM_OCR_BOT_USERNAME', 'Samshodhana_OCR_Bot').lstrip('@')
    stt_uname = getattr(config, 'SANSKRIT_STT_BOT_USERNAME', 'TVSM_STT_BOT').lstrip('@')
    trans_uname = getattr(config, 'TRANSLITERATOR_BOT_USERNAME', 'TVSM_Translatorator_Bot').lstrip('@')
    
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


def build_autotrans_keyboard(current_script: str = "off") -> InlineKeyboardMarkup:
    """Creates inline keyboard for Auto-Transliterate settings."""
    row0 = [
        InlineKeyboardButton(f"{'✅ ' if current_script=='off' else ''}🚫 Off (Original Extracted Text)", callback_data="set_autotrans_off")
    ]
    row1 = [
        InlineKeyboardButton(f"{'✅ ' if current_script=='sa' else ''}🕉️ Devanagari", callback_data="set_autotrans_sa"),
        InlineKeyboardButton(f"{'✅ ' if current_script=='ka' else ''}💛 Kannada", callback_data="set_autotrans_ka")
    ]
    row2 = [
        InlineKeyboardButton(f"{'✅ ' if current_script=='te' else ''}💙 Telugu", callback_data="set_autotrans_te"),
        InlineKeyboardButton(f"{'✅ ' if current_script=='ta' else ''}🌺 Tamil", callback_data="set_autotrans_ta")
    ]
    row3 = [
        InlineKeyboardButton(f"{'✅ ' if current_script=='ml' else ''}🌴 Malayalam", callback_data="set_autotrans_ml"),
        InlineKeyboardButton(f"{'✅ ' if current_script=='en' else ''}🔤 IAST", callback_data="set_autotrans_en")
    ]
    row4 = [
        InlineKeyboardButton(f"{'✅ ' if current_script=='slp1' else ''}🔀 SLP1", callback_data="set_autotrans_slp1"),
        InlineKeyboardButton(f"{'✅ ' if current_script=='itrans' else ''}📝 ITRANS", callback_data="set_autotrans_itrans")
    ]
    row5 = [
        InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")
    ]
    return InlineKeyboardMarkup([row0, row1, row2, row3, row4, row5])


def build_back_keyboard() -> InlineKeyboardMarkup:
    """Builds back button keyboard."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")]])


def build_translit_keyboard(job_id: str, active_script: str = "sa") -> InlineKeyboardMarkup:
    """Creates inline keyboard with script transliteration options."""
    keyboard = []
    
    # Grid of scripts
    row1 = [
        InlineKeyboardButton(f"{'✅ ' if active_script=='sa' else ''}🕉️ Devanagari", callback_data=f"tr_{job_id}_sa"),
        InlineKeyboardButton(f"{'✅ ' if active_script=='ka' else ''}💛 Kannada", callback_data=f"tr_{job_id}_ka")
    ]
    row2 = [
        InlineKeyboardButton(f"{'✅ ' if active_script=='te' else ''}💙 Telugu", callback_data=f"tr_{job_id}_te"),
        InlineKeyboardButton(f"{'✅ ' if active_script=='ta' else ''}🌺 Tamil", callback_data=f"tr_{job_id}_ta")
    ]
    row3 = [
        InlineKeyboardButton(f"{'✅ ' if active_script=='ml' else ''}🌴 Malayalam", callback_data=f"tr_{job_id}_ml"),
        InlineKeyboardButton(f"{'✅ ' if active_script=='en' else ''}🔤 IAST", callback_data=f"tr_{job_id}_en")
    ]
    row4 = [
        InlineKeyboardButton(f"{'✅ ' if active_script=='slp1' else ''}🔀 SLP1", callback_data=f"tr_{job_id}_slp1"),
        InlineKeyboardButton(f"{'✅ ' if active_script=='itrans' else ''}📝 ITRANS", callback_data=f"tr_{job_id}_itrans")
    ]
    row5 = [
        InlineKeyboardButton("📁 Download .txt File", callback_data=f"dl_{job_id}_{active_script}")
    ]
    
    keyboard.extend([row1, row2, row3, row4, row5])
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start and /help commands."""
    welcome_text = (
        "✨ <b>Welcome to Samshodhanam OCR Bot!</b> ✨\n"
        "<i>High-Accuracy Multilingual OCR & Transliteration Service</i>\n\n"
        "📸 <b>Send any Photo, Image Document, or PDF file to extract text instantly!</b>\n\n"
        "<i>Tap a button below to explore features or get help:</i>"
    )
    keyboard = build_welcome_keyboard()
    if update.message:
        await update.message.reply_html(welcome_text, reply_markup=keyboard)
    elif update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=keyboard)


async def process_media_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_obj, original_filename: str):
    """Downloads and processes an incoming image or PDF file."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    status_msg = await update.message.reply_text("⚡ <i>Receiving document... Preparing OCR pipeline.</i>", parse_mode="HTML")

    # Download file to temporary location
    job_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(original_filename)[1].lower() or ".jpg"
    temp_filepath = os.path.join(config.TEMP_OCR_DIR, f"ocr_{job_id}{ext}")

    try:
        tg_file = await context.bot.get_file(file_obj.file_id)
        await tg_file.download_to_drive(temp_filepath)
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await status_msg.edit_text(f"❌ <b>Failed to download file from Telegram:</b> {e}", parse_mode="HTML")
        return

    # Real-time progress updater callback
    last_update_time = [0]
    async def update_progress(current_page: int, total_pages: int):
        now = time.time()
        if now - last_update_time[0] > 2.5 or current_page == total_pages:
            last_update_time[0] = now
            pct = int((current_page / total_pages) * 100)
            try:
                await status_msg.edit_text(
                    f"⏳ <b>Processing OCR... Page {current_page}/{total_pages} ({pct}%)</b>",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    loop = asyncio.get_running_loop()

    def run_ocr_sync():
        def cb(c, t):
            asyncio.run_coroutine_threadsafe(update_progress(c, t), loop)
        return ocr_service.process_ocr_file(temp_filepath, progress_callback=cb)

    try:
        await status_msg.edit_text("⚡ <i>Running OCR engine... Please wait.</i>", parse_mode="HTML")
        extracted_text = await loop.run_in_executor(None, run_ocr_sync)
    except Exception as e:
        logger.error(f"OCR execution error: {e}")
        await status_msg.edit_text(f"❌ <b>OCR Processing Failed:</b> {e}", parse_mode="HTML")
        if os.path.exists(temp_filepath):
            try: os.unlink(temp_filepath)
            except: pass
        return

    # Clean up temp input file
    if os.path.exists(temp_filepath):
        try: os.unlink(temp_filepath)
        except: pass

    if not extracted_text or not extracted_text.strip():
        await status_msg.edit_text("⚠️ <b>No text could be extracted from the file.</b>", parse_mode="HTML")
        return

    # Store in job cache
    clean_job_cache()
    JOB_CACHE[job_id] = {
        'text': extracted_text,
        'filename': original_filename,
        'chat_id': chat_id,
        'timestamp': time.time()
    }

    # Determine user auto-transliterate setting
    active_script = USER_PREFERENCES.get(chat_id, "off")
    
    if active_script == "off":
        output_text = extracted_text
        keyboard = build_translit_keyboard(job_id, active_script="sa")
        header_title = "<b>✅ OCR Text Output:</b>"
        doc_caption = "<b>✅ OCR Extraction Complete!</b>"
        out_filename_ext = ""
    else:
        try:
            output_text = translit_bridge.convert_text(extracted_text, target_script=active_script, src_script="sa")
        except Exception as e:
            logger.error(f"Auto-transliteration error: {e}")
            output_text = extracted_text

        keyboard = build_translit_keyboard(job_id, active_script=active_script)
        script_label = config.SUPPORTED_SCRIPTS.get(active_script, active_script.upper())
        header_title = f"<b>✅ OCR Text Output ({script_label}):</b>"
        doc_caption = f"<b>✅ OCR Extraction Complete ({script_label})!</b>"
        out_filename_ext = f"_{active_script}"

    # Send extracted text
    if len(output_text) <= 3500:
        await status_msg.delete()
        await update.message.reply_text(
            f"{header_title}\n\n{output_text}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    else:
        await status_msg.delete()
        snippet = output_text[:1200] + f"\n\n... [Truncated: Total {len(output_text)} characters]"
        
        # Create text file attachment
        txt_bytes = io.BytesIO(output_text.encode('utf-8'))
        base_name = os.path.splitext(original_filename)[0]
        out_filename = f"{base_name}_OCR{out_filename_ext}.txt"
        
        await update.message.reply_document(
            document=txt_bytes,
            filename=out_filename,
            caption=f"{doc_caption} ({len(output_text)} characters)\n\n<i>Preview:</i>\n{snippet[:500]}...",
            parse_mode="HTML",
            reply_markup=keyboard
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for photos sent to bot."""
    photo = update.message.photo[-1] # Highest resolution photo
    filename = f"photo_{int(time.time())}.jpg"
    await process_media_file(update, context, photo, filename)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for document files (PDFs, Images as docs) sent to bot."""
    doc = update.message.document
    filename = doc.file_name or f"doc_{int(time.time())}.pdf"
    await process_media_file(update, context, doc, filename)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for script transliteration buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("tr_"):
        parts = data.split("_")
        if len(parts) < 3:
            return
        job_id = parts[1]
        target_script = parts[2]

        job = JOB_CACHE.get(job_id)
        if not job:
            await query.edit_message_caption(caption="⚠️ <i>Session expired. Please re-send the image or PDF file.</i>", parse_mode="HTML")
            return

        raw_text = job['text']
        converted_text = translit_bridge.convert_text(raw_text, target_script=target_script, src_script="sa")
        script_label = config.SUPPORTED_SCRIPTS.get(target_script, target_script.upper())

        keyboard = build_translit_keyboard(job_id, active_script=target_script)

        if len(converted_text) <= 3500 and query.message.text:
            await query.edit_message_text(
                f"<b>✅ OCR Text Output ({script_label}):</b>\n\n{converted_text}",
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            # Send updated file or edit caption
            base_name = os.path.splitext(job['filename'])[0]
            out_filename = f"{base_name}_OCR_{target_script}.txt"
            
            txt_bytes = io.BytesIO(converted_text.encode('utf-8'))
            caption = f"<b>✅ OCR Text Transliterated to {script_label}!</b>"

            await query.message.reply_document(
                document=txt_bytes,
                filename=out_filename,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    elif data.startswith("dl_"):
        parts = data.split("_")
        if len(parts) < 3:
            return
        job_id = parts[1]
        target_script = parts[2]

        job = JOB_CACHE.get(job_id)
        if not job:
            await query.message.reply_text("⚠️ <i>Session expired. Please re-send the image or PDF file.</i>", parse_mode="HTML")
            return

        raw_text = job['text']
        converted_text = translit_bridge.convert_text(raw_text, target_script=target_script, src_script="sa")
        script_label = config.SUPPORTED_SCRIPTS.get(target_script, target_script.upper())

        base_name = os.path.splitext(job['filename'])[0]
        out_filename = f"{base_name}_OCR_{target_script}.txt"
        txt_bytes = io.BytesIO(converted_text.encode('utf-8'))

        keyboard = build_translit_keyboard(job_id, active_script=target_script)
        await query.message.reply_document(
            document=txt_bytes,
            filename=out_filename,
            caption=f"📁 <b>Here is your OCR text in {script_label}:</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )

    elif data.startswith("set_autotrans_"):
        chat_id = update.effective_chat.id
        target_script = data.replace("set_autotrans_", "")
        USER_PREFERENCES[chat_id] = target_script
        
        if target_script == "off":
            autotrans_text = (
                "<b>🔄 Auto-Transliterate Output Settings</b>\n\n"
                "✅ Auto-transliteration is set to: <b>Off (Original Extracted Text)</b>!\n\n"
                "You will receive the exact text extracted by the OCR engine without any automatic script conversion."
            )
        else:
            script_label = config.SUPPORTED_SCRIPTS.get(target_script, target_script.upper())
            autotrans_text = (
                "<b>🔄 Auto-Transliterate Output Settings</b>\n\n"
                f"✅ Default Output Script set to: <b>{script_label}</b>!\n\n"
                "All future OCR extractions will automatically be converted to this script upon processing."
            )
        await query.edit_message_text(autotrans_text, parse_mode="HTML", reply_markup=build_autotrans_keyboard(target_script))

    elif data.startswith("menu_"):
        chat_id = update.effective_chat.id
        if data == "menu_main":
            welcome_text = (
                "✨ <b>Welcome to Samshodhanam OCR Bot!</b> ✨\n"
                "<i>High-Accuracy Multilingual OCR & Transliteration Service</i>\n\n"
                "📸 <b>Send any Photo, Image Document, or PDF file to extract text instantly!</b>\n\n"
                "<i>Tap a button below to explore features or get help:</i>"
            )
            await query.edit_message_text(welcome_text, parse_mode="HTML", reply_markup=build_welcome_keyboard())

        elif data == "menu_autotrans":
            pref = USER_PREFERENCES.get(chat_id, "off")
            if pref == "off":
                script_label = "Off (Original Extracted Text)"
            else:
                script_label = config.SUPPORTED_SCRIPTS.get(pref, pref.upper())

            autotrans_text = (
                "<b>🔄 Auto-Transliterate Output Settings</b>\n\n"
                f"Currently Active: <b>{script_label}</b>\n\n"
                "Select a default script below, or keep it Off to receive the original extracted text as it is."
            )
            await query.edit_message_text(autotrans_text, parse_mode="HTML", reply_markup=build_autotrans_keyboard(pref))

        elif data == "menu_help":
            help_text = (
                "<b>📖 How to Use Samshodhanam OCR Bot</b>\n\n"
                "1️⃣ <b>Send your document:</b> Upload a photo, image, or multi-page PDF.\n"
                "2️⃣ <b>Automatic Extraction:</b> The bot processes the document with high-accuracy OCR.\n"
                "3️⃣ <b>Auto / Manual Transliteration:</b> Use 🔄 <b>Auto Transliterate</b> to set your default script, or tap any script button below your results.\n"
                "4️⃣ <b>Download Output:</b> Tap 📁 Download .txt to save your output file.\n\n"
                "<i>💡 Tip: Clear, well-lit images deliver the highest extraction accuracy.</i>"
            )
            await query.edit_message_text(help_text, parse_mode="HTML", reply_markup=build_back_keyboard())

        elif data == "menu_scripts":
            scripts_text = (
                "<b>🌐 Supported Transliteration Scripts</b>\n\n"
                "• 🕉️ <b>Devanagari</b> (Sanskrit / Hindi)\n"
                "• 💛 <b>Kannada</b>\n"
                "• 💙 <b>Telugu</b>\n"
                "• 🌺 <b>Tamil</b>\n"
                "• 🌴 <b>Malayalam</b>\n"
                "• 🔤 <b>IAST</b> (Roman with diacritics)\n"
                "• 🔀 <b>SLP1</b> (Sanskrit Library Phonetic 1)\n"
                "• 📝 <b>ITRANS</b>\n\n"
                "<i>All scripts are available for instant 1-tap conversion after OCR!</i>"
            )
            await query.edit_message_text(scripts_text, parse_mode="HTML", reply_markup=build_back_keyboard())

        elif data == "menu_features":
            features_text = (
                "<b>⚡ Key Features</b>\n\n"
                "• 📄 <b>Unlimited PDF Pages:</b> Process single pages or full PDF books.\n"
                "• 🎯 <b>High Accuracy:</b> Tuned for Indic and Sanskrit classical texts.\n"
                "• 🌐 <b>Instant Transliteration:</b> Convert across 8 popular scripts with 1 tap.\n"
                "• 📁 <b>Export Anywhere:</b> Inline text preview + downloadable `.txt` files.\n"
            )
            await query.edit_message_text(features_text, parse_mode="HTML", reply_markup=build_back_keyboard())

        elif data == "menu_otherbots":
            other_bots_text = (
                "🤖 <b>Samshodhanam Telegram Bot Family</b>\n\n"
                "Explore our suite of specialized Telegram bots for Sanskrit & Indic literature:\n\n"
                "• 📸 <b>OCR Bot:</b> High-accuracy image/PDF text extraction & script conversion.\n"
                "• 🎙️ <b>Speech-to-Text Bot:</b> Sanskrit audio & voice message transcription.\n"
                "• 🌐 <b>Transliterator Bot:</b> Instant 1-tap script transliteration across 20+ Indic scripts.\n\n"
                "<i>Tap any bot button below to open and start using it directly in Telegram!</i>"
            )
            await query.edit_message_text(other_bots_text, parse_mode="HTML", reply_markup=build_other_bots_keyboard())

        elif data == "menu_support":
            support_email = getattr(config, 'SUPPORT_EMAIL', 'samshodhanamandiram@gmail.com')
            tg_handle = getattr(config, 'SUPPORT_TELEGRAM_HANDLE', '').lstrip('@')
            
            support_text = (
                "<b>💬 Contact & Support — Samshodhana Mandiram</b>\n\n"
                "If you face any issues, have questions, or need assistance:\n\n"
                f"📧 <b>Support Email:</b> {support_email}\n"
                "🌐 <b>Website:</b> <a href='https://samshodhanam.in'>samshodhanam.in</a>\n\n"
                "<i>We welcome your feedback, bug reports, and feature requests!</i>"
            )
            
            support_buttons = []
            if tg_handle:
                support_buttons.append([InlineKeyboardButton("💬 Message Support on Telegram", url=f"https://t.me/{tg_handle}")])
            support_buttons.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_main")])
            
            await query.edit_message_text(support_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(support_buttons))


def main():
    """Starts the Telegram OCR Bot application."""
    token = config.get_telegram_token() if hasattr(config, 'get_telegram_token') else getattr(config, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        logger.error("TELEGRAM_OCR_BOT_TOKEN or TELEGRAM_BOT_TOKEN is not set! Set it in config.py or environment.")
        print("\n❌ TELEGRAM_BOT_TOKEN missing! Please set TELEGRAM_OCR_BOT_TOKEN in config.py or environment variables.\n")
        return

    logger.info("Initializing Samshodhanam Telegram OCR Bot...")
    app = ApplicationBuilder().token(token).build()

    # Add command handlers
    app.add_handler(CommandHandler(["start", "help"], start_command))

    # Add media handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Add callback handler for transliteration buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot is ready. Starting polling loop...")
    print("🚀 Samshodhanam Telegram OCR Bot is running!")
    app.run_polling()


if __name__ == "__main__":
    main()
