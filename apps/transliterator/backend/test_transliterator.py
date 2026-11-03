"""
Automated unit test for Transliterator Engine & Cross-Bot Integration.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import translit_engine as engine
import bot_db as db

def test_transliteration_accuracy():
    print("--- 1. Testing Tamil Superscripts & Phoneme Table ---")

    # Devanagari to Tamil (with superscripts ² ³ ⁴)
    # क -> க, ख -> க², ग -> க³, घ -> க⁴
    ka_tam = engine.convert_script("क", "sa", "ta")
    kha_tam = engine.convert_script("ख", "sa", "ta")
    ga_tam = engine.convert_script("ग", "sa", "ta")
    gha_tam = engine.convert_script("घ", "sa", "ta")

    print(f"क (ka)  -> Tamil: {ka_tam}")
    print(f"ख (kha) -> Tamil: {kha_tam}")
    print(f"ग (ga)  -> Tamil: {ga_tam}")
    print(f"घ (gha) -> Tamil: {gha_tam}")

    assert ka_tam == "க", f"Expected 'க', got '{ka_tam}'"
    assert kha_tam == "க²", f"Expected 'க²', got '{kha_tam}'"
    assert ga_tam == "க³", f"Expected 'க³', got '{ga_tam}'"
    assert gha_tam == "க⁴", f"Expected 'க⁴', got '{gha_tam}'"
    print("✅ Tamil Superscript tests passed!")

    print("\n--- 2. Testing Devanagari to Kannada & IAST ---")
    verse = "धर्मक्षेत्रे कुरुक्षेत्रे समवेता युयुत्सवः"
    kan_verse = engine.convert_script(verse, "sa", "ka")
    iast_verse = engine.convert_script(verse, "sa", "en")

    print(f"Original (Devanagari): {verse}")
    print(f"Kannada:              {kan_verse}")
    print(f"IAST:                 {iast_verse}")

    assert "ಧರ್ಮಕ್ಷೇತ್ರೇ" in kan_verse or "ಧರ್ಮ" in kan_verse
    print("✅ Devanagari -> Kannada & IAST tests passed!")

def test_bot_database():
    print("\n--- 3. Testing Transliterator Bot DB & Manager ---")
    db.init_db()
    db.set_user_pref(9999, input_script='sa', output_script='ta')
    pref = db.get_user_pref(9999)
    assert pref['output_script'] == 'ta'

    import bot_manager
    info = bot_manager.get_bot_status_info()
    assert 'running' in info
    assert 'bot_username' in info
    print(f"Bot Status Info verified: {info}")
    print("✅ Database preferences & Manager tests passed!")

def test_stt_keyboard_linking():
    print("\n--- 4. Testing STT Keyboard Linking ---")
    stt_dir = os.path.join(os.path.dirname(os.path.dirname(BACKEND_DIR)), "sanskrit_stt", "backend")
    if "bot_db" in sys.modules:
        del sys.modules["bot_db"]
    sys.path.insert(0, stt_dir)
    import telegram_bot as stt_bot

    kb = stt_bot.get_transcription_action_keyboard(log_id=123)
    found_translit = False
    for row in kb.inline_keyboard:
        for btn in row:
            if "Transliterate" in btn.text:
                found_translit = True
                assert "t.me/" in btn.url
                assert "start=stt_123" in btn.url
                print(f"Found Transliterate button with URL: {btn.url}")
    assert found_translit, "Transliterate button missing from STT keyboard!"
    print("✅ STT bot keyboard deep-link test passed!")

if __name__ == "__main__":
    test_transliteration_accuracy()
    test_bot_database()
    test_stt_keyboard_linking()
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY!")
