"""
Process Manager & Health Diagnostic for Transliterator Telegram Bot.
"""

import os
import sys
import time
import json
import logging
import subprocess
import urllib.request
import urllib.error
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("transliterator_bot_manager")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BACKEND_DIR, "transliterator_bot.pid")
LOG_FILE = os.path.join(BACKEND_DIR, "transliterator_bot.log")

def _get_bot_db():
    import importlib.util
    file_path = os.path.join(BACKEND_DIR, "bot_db.py")
    spec = importlib.util.spec_from_file_location("transliterator_bot_db_mod", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def get_bot_token() -> str:
    token = os.getenv("TRANSLITERATOR_BOT_TOKEN", "").strip()
    if not token:
        try:
            bot_db = _get_bot_db()
            token = bot_db.get_setting("transliterator_bot_token", "").strip()
        except Exception:
            pass
    return token

def check_telegram_token_valid(token: str) -> Tuple[bool, Dict[str, Any]]:
    """Tests the Telegram Bot Token via Telegram API getMe."""
    if not token:
        return False, {}
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SamshodhanaTransliterator/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, data.get("result", {})
    except Exception as e:
        logger.warning(f"Failed to validate Telegram bot token: {e}")
    return False, {}

def is_bot_running() -> Tuple[bool, Optional[int]]:
    """Checks if telegram_bot.py process is active."""
    pid = None
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None

    if pid is not None:
        if os.name == "nt":
            try:
                output = subprocess.check_output(
                    f'tasklist /FI "PID eq {pid}"',
                    shell=True,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                if str(pid) in output and "python" in output.lower():
                    return True, pid
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 0)
                return True, pid
            except (OSError, ValueError):
                pass

    # Fallback scan processes for transliterator/backend/telegram_bot.py
    try:
        if os.name == "nt":
            cmd = 'wmic process where "name like \'%python%\'" get processid,commandline'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            for line in output.splitlines():
                if "transliterator" in line.lower() and "telegram_bot.py" in line:
                    parts = line.strip().split()
                    found_pid = int(parts[-1])
                    with open(PID_FILE, "w") as f:
                        f.write(str(found_pid))
                    return True, found_pid
        else:
            cmd = "ps aux | grep transliterator | grep telegram_bot.py | grep -v grep"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            if output.strip():
                parts = output.strip().split()
                found_pid = int(parts[1])
                with open(PID_FILE, "w") as f:
                    f.write(str(found_pid))
                return True, found_pid
    except Exception:
        pass

    return False, None

def start_bot() -> Tuple[bool, str]:
    running, pid = is_bot_running()
    if running:
        return True, f"Transliterator Bot is already running (PID: {pid})."

    token = get_bot_token()
    if not token:
        return False, "Transliterator Bot Token is missing. Set it in Admin Panel settings."

    valid, bot_info = check_telegram_token_valid(token)
    if not valid:
        return False, "Invalid Telegram Bot Token. Check API credentials."

    script_path = os.path.join(BACKEND_DIR, "telegram_bot.py")
    python_exe = sys.executable

    try:
        log_fd = open(LOG_FILE, "a", encoding="utf-8")
        if os.name == "nt":
            proc = subprocess.Popen(
                [python_exe, script_path],
                cwd=BACKEND_DIR,
                stdout=log_fd,
                stderr=log_fd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            proc = subprocess.Popen(
                [python_exe, script_path],
                cwd=BACKEND_DIR,
                stdout=log_fd,
                stderr=log_fd,
                preexec_fn=os.setsid
            )

        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        try:
            log_fd.close()
        except Exception:
            pass

        time.sleep(1.5)
        if proc.poll() is not None:
            return False, "Process started but exited immediately. Check log file for details."

        return True, f"Transliterator Bot started successfully (PID: {proc.pid})."
    except Exception as e:
        return False, f"Failed to start process: {str(e)}"

def stop_bot() -> Tuple[bool, str]:
    running, pid = is_bot_running()
    if not running or pid is None:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        return True, "Transliterator Bot is not running."

    try:
        if os.name == "nt":
            subprocess.run(f"taskkill /F /PID {pid}", shell=True, check=False)
        else:
            os.kill(pid, 9)

        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

        return True, f"Transliterator Bot process (PID: {pid}) stopped."
    except Exception as e:
        return False, f"Failed to stop process PID {pid}: {str(e)}"

def restart_bot() -> Tuple[bool, str]:
    stop_bot()
    time.sleep(1)
    return start_bot()

def get_bot_status_info() -> Dict[str, Any]:
    running, pid = is_bot_running()
    token = get_bot_token()
    valid, bot_info = check_telegram_token_valid(token) if token else (False, {})
    bot_db = _get_bot_db()
    stats = bot_db.get_stats()

    return {
        "running": running,
        "pid": pid,
        "token_valid": valid,
        "bot_info": bot_info,
        "bot_token_masked": (token[:6] + "..." + token[-4:]) if len(token) > 10 else "",
        "bot_username": bot_info.get("username", bot_db.get_setting("transliterator_bot_username", "TVSM_Translatorator_Bot")),
        "stats": stats
    }

def get_bot_logs(max_lines: int = 50) -> str:
    """Reads the last N lines from transliterator_bot.log or systemd journal."""
    logs = ""
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                logs = "".join(lines[-max_lines:])
        except Exception as e:
            logs = f"Error reading log file: {str(e)}"

    if not logs.strip() and os.name != "nt":
        try:
            cmd = f"journalctl -u samshodhana-transliterator-bot -n {max_lines} --no-pager"
            logs = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except Exception:
            pass

    return logs if logs.strip() else "No log records found."
