import os

try:
    from dotenv import load_dotenv
    # Load .env from project root or sdl_web dir
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except ImportError:
    pass

# Flask configuration
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# Upload settings
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
MAX_CONTENT_LENGTH = 4 * 1024 * 1024 * 1024  # 4GB max upload size

ZSTD_COMPRESSION_LEVEL = 7  # Zstandard level (1-22). Default 7 is a great balance.

# Email Settings (for volunteer notifications & OCR alerts)
# Configure these via .env or environment variables — do not hardcode credentials here.
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '')      # e.g. yourapp@gmail.com
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')  # Loaded securely from .env or environment variable
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')  # Destination for admin notification emails

# Create uploads folder if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# AI / ChromaDB configurations
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chroma_db')
GEMINI_API_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gemini_key.json')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '') or os.environ.get('GOOGLE_API_KEY', '')

def get_gemini_api_key():
    """Retrieve the primary Gemini API key from environment, config, or stored admin key."""
    key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or GEMINI_API_KEY
    if key and key.strip():
        return key.strip()
    try:
        from db import common_db
        admin_key = common_db.get_any_admin_gemini_key()
        if admin_key and admin_key.strip():
            return admin_key.strip()
    except Exception:
        pass
    return ''

def is_gemini_quota_error(err):
    """Check if an exception corresponds to a Gemini 429 quota/rate limit error."""
    if not err:
        return False
    err_str = str(err).lower()
    class_name = err.__class__.__name__.lower()
    phrases = [
        "resourceexhausted", "resource exhausted", "429", "quota",
        "rate limit", "rate-limited", "limit exceeded", "toomanyrequests",
        "resource_exhausted"
    ]
    return any(p in err_str for p in phrases) or any(p in class_name for p in phrases)

# Central Cloud OCR Service API (leave empty if not using an external cloud worker)
SAMSHO_OCR_API_URL = os.environ.get('SAMSHO_OCR_API_URL', '')
SAMSHO_OCR_API_KEY = os.environ.get('SAMSHO_OCR_API_KEY', '')

# Central Cloud STT Service API (leave empty if not using an external cloud worker)
SAMSHO_STT_API_URL = os.environ.get('SAMSHO_STT_API_URL', '')
SAMSHO_STT_API_KEY = os.environ.get('SAMSHO_STT_API_KEY', '')

# Central Cloud NLP Service API (Paninian Grammar, Shabda, Dhatu, Sandhi & Tarka)
SAMSHO_NLP_API_URL = os.environ.get('SAMSHO_NLP_API_URL', 'http://localhost:5001/apps/api')
SAMSHO_NLP_API_KEY = os.environ.get('SAMSHO_NLP_API_KEY', '')

# Google Sign-in Configuration
# Set GOOGLE_CLIENT_ID in your .env to enable Google Sign-In.
# Leave empty (or unset) to disable Google Sign-In entirely.
# Get your client ID from: https://console.cloud.google.com/apis/credentials
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
