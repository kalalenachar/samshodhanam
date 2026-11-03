"""
Process Manager & Health Diagnostics Runner for Samshodhanam OCR Telegram Bot.
"""

import os
import sys
import time
import subprocess
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)


PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot.pid")
RUNNER_PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot_runner.pid")
CHILD_PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot_child.pid")
STOP_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot.stop")

try:
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    with open(RUNNER_PID_FILE, "w") as f:
        f.write(str(os.getpid()))
except Exception:
    pass

import config
import ocr_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [OCR_Bot_Runner] %(message)s")

def check_diagnostics():
    """Runs pre-flight diagnostics before launching the bot."""
    print("=" * 65)
    print(" 🤖 SAMSHODHANAM TELEGRAM OCR BOT DIAGNOSTICS")
    print("=" * 65)

    # 1. Check Bot Token
    token = config.get_telegram_token() if hasattr(config, 'get_telegram_token') else config.TELEGRAM_BOT_TOKEN
    if token:
        masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
        print(f"  ✅ Telegram Bot Token: Set ({masked})")
    else:
        print("  ⚠️ Telegram Bot Token: NOT SET (Set TELEGRAM_OCR_BOT_TOKEN in env or config.py)")

    # 2. Check OCR Engine Credentials
    api_url = ocr_service.get_ocr_api_url()
    if api_url:
        print(f"  ☁️ Samshodhanam OCR API: Configured ({api_url})")
    else:
        print("  ℹ️ Samshodhanam OCR API: Not set (Local OCR fallback active)")

    # 3. Check Dependencies
    print("  📦 Library Diagnostics:")
    print(f"      - PyMuPDF (fitz): {'Available ✅' if ocr_service.HAS_FITZ else 'Missing ❌ (pip install pymupdf)'}")
    print(f"      - PIL (Pillow):   {'Available ✅' if ocr_service.HAS_PIL else 'Missing ❌ (pip install Pillow)'}")
    print("      - Primary Engine: Cloud OCR API ✅")

    print("=" * 65 + "\n")


def run():
    check_diagnostics()
    bot_script = os.path.join(BOT_DIR, "telegram_bot.py")
    
    # If starting fresh, remove stop file
    if os.path.exists(STOP_FILE):
        try:
            os.remove(STOP_FILE)
        except Exception:
            pass

    token = config.get_telegram_token() if hasattr(config, 'get_telegram_token') else config.TELEGRAM_BOT_TOKEN
    if not token:
        print("❌ Cannot start bot without a valid TELEGRAM_OCR_BOT_TOKEN.")
        sys.exit(1)

    print("🚀 Launching Telegram OCR Bot process...\n")
    while True:
        if os.path.exists(STOP_FILE):
            print("🛑 Stop flag detected before launching child process. Exiting runner.")
            break

        try:
            p = subprocess.Popen([sys.executable, bot_script])
            try:
                with open(CHILD_PID_FILE, "w") as f:
                    f.write(str(p.pid))
            except Exception:
                pass

            p.wait()

            if os.path.exists(CHILD_PID_FILE):
                try:
                    os.remove(CHILD_PID_FILE)
                except Exception:
                    pass

            if os.path.exists(STOP_FILE):
                print("🛑 Stop flag detected. Bot runner shutting down cleanly.")
                break

            if p.returncode != 0:
                print(f"⚠️ Bot process exited with code {p.returncode}. Checking if stop was requested...")
                for _ in range(5):
                    if os.path.exists(STOP_FILE):
                        print("🛑 Stop flag detected during delay. Exiting runner.")
                        break
                    time.sleep(1)
                if os.path.exists(STOP_FILE):
                    break
            else:
                print("Bot process stopped cleanly.")
                break
        except KeyboardInterrupt:
            print("\nStopping OCR Telegram Bot...")
            break
        except Exception as e:
            print(f"Runner error: {e}. Retrying in 5 seconds...")
            for _ in range(5):
                if os.path.exists(STOP_FILE):
                    break
                time.sleep(1)
            if os.path.exists(STOP_FILE):
                break

    for pf in [PID_FILE, RUNNER_PID_FILE, CHILD_PID_FILE]:
        if os.path.exists(pf):
            try:
                os.remove(pf)
            except Exception:
                pass


if __name__ == "__main__":
    run()
