"""
Transliteration Bridge for Samshodhanam OCR Bot.
Integrates with Samshodhanam Transliterator Engine to convert extracted OCR text
between Devanagari, Kannada, Telugu, Tamil, Malayalam, IAST, SLP1, ITRANS, etc.
"""

import os
import sys
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logger = logging.getLogger("ocr_bot_translit")

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_DIR = os.path.dirname(BOT_DIR)
TRANSLITERATOR_BACKEND = os.path.join(APPS_DIR, "transliterator", "backend")

if os.path.exists(TRANSLITERATOR_BACKEND) and TRANSLITERATOR_BACKEND not in sys.path:
    sys.path.insert(0, TRANSLITERATOR_BACKEND)

try:
    import translit_engine
    engine_convert_script = getattr(translit_engine, 'convert_script', None)
except Exception as e:
    engine_convert_script = None
    logger.warning(f"Could not import translit_engine: {e}")


def convert_text(text: str, target_script: str, src_script: str = "sa") -> str:
    """
    Transliterates given text from src_script (default 'sa' for Devanagari) to target_script.
    """
    if not text or not text.strip():
        return text

    if target_script == src_script:
        return text

    if engine_convert_script:
        try:
            return engine_convert_script(text, src_script, target_script)
        except Exception as e:
            logger.error(f"Transliteration via translit_engine failed: {e}")

    # Fallback to vidyut.lipi
    try:
        from vidyut.lipi import Scheme, transliterate as vidyut_transliterate
        scheme_map = {
            'sa': Scheme.Devanagari,
            'ka': Scheme.Kannada,
            'te': Scheme.Telugu,
            'ta': Scheme.Tamil,
            'ml': Scheme.Malayalam,
            'en': Scheme.Iast,
            'slp1': Scheme.Slp1,
            'itrans': Scheme.Itrans
        }
        if src_script in scheme_map and target_script in scheme_map:
            return vidyut_transliterate(text, scheme_map[src_script], scheme_map[target_script])
    except Exception:
        pass

    # Fallback to indic_transliteration
    try:
        from indic_transliteration import sanscript
        sanscript_map = {
            'sa': sanscript.DEVANAGARI,
            'ka': sanscript.KANNADA,
            'te': sanscript.TELUGU,
            'ta': sanscript.TAMIL,
            'ml': sanscript.MALAYALAM,
            'en': sanscript.IAST,
            'slp1': sanscript.SLP1,
            'itrans': sanscript.ITRANS,
            'bn': sanscript.BENGALI,
            'gu': sanscript.GUJARATI
        }
        if src_script in sanscript_map and target_script in sanscript_map:
            return sanscript.transliterate(text, sanscript_map[src_script], sanscript_map[target_script])
    except Exception:
        pass

    return text
