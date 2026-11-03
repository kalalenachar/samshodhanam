"""
Configuration Module for Samshodhanam Telegram OCR Bot.
Loads environment variables and bot configuration settings.
"""

import os
import sys
from dotenv import load_dotenv

# Base paths
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_DIR = os.path.dirname(BOT_DIR)
PROJECT_ROOT = os.path.dirname(APPS_DIR)
SDL_WEB_DIR = os.path.join(PROJECT_ROOT, "sdl_web")

# Add sdl_web to path to import config if needed
if SDL_WEB_DIR not in sys.path:
    sys.path.insert(0, SDL_WEB_DIR)

def get_telegram_token() -> str:
    """Dynamically loads and returns Telegram Bot Token from .env files or environment."""
    load_dotenv(os.path.join(BOT_DIR, ".env"), override=True)
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)
    token = os.getenv("TELEGRAM_OCR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
    global TELEGRAM_BOT_TOKEN
    TELEGRAM_BOT_TOKEN = token
    return token

# Telegram Bot Usernames & Handles
TELEGRAM_BOT_TOKEN = get_telegram_token()
BOT_USERNAME = os.getenv("TELEGRAM_OCR_BOT_USERNAME", "Samshodhana_OCR_Bot")
TELEGRAM_OCR_BOT_USERNAME = BOT_USERNAME
SANSKRIT_STT_BOT_USERNAME = os.getenv("SANSKRIT_STT_BOT_USERNAME", "TVSM_STT_BOT")
TRANSLITERATOR_BOT_USERNAME = os.getenv("TRANSLITERATOR_BOT_USERNAME", "TVSM_Translatorator_Bot")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
SUPPORT_TELEGRAM_HANDLE = os.getenv("SUPPORT_TELEGRAM_HANDLE", "").lstrip("@")

# Central Cloud OCR Service API
SAMSHO_OCR_API_URL = os.getenv("SAMSHO_OCR_API_URL", "http://localhost:5001/api/v1/ocr")
SAMSHO_OCR_API_KEY = os.getenv("SAMSHO_OCR_API_KEY", "")

# Temporary directory for bot OCR jobs
TEMP_OCR_DIR = os.path.join(BOT_DIR, "temp_ocr")
os.makedirs(TEMP_OCR_DIR, exist_ok=True)

# Transliteration Script Definitions
SUPPORTED_SCRIPTS = {
    'sa': '🕉️ Devanagari',
    'ka': '💛 Kannada',
    'te': '💙 Telugu',
    'ta': '🌺 Tamil',
    'ml': '🌴 Malayalam',
    'en': '🔤 IAST (Roman)',
    'slp1': '🔀 SLP1',
    'itrans': '📝 ITRANS',
    'bn': '🇧🇩 Bengali',
    'gu': '🇮🇳 Gujarati'
}
