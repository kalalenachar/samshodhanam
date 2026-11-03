import os
import sys
import time
import json
import logging
import subprocess
import urllib.request
import urllib.error

logger = logging.getLogger("samshodhana_bot_manager")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BACKEND_DIR, "telegram_bot.pid")
LOG_FILE = os.path.join(BACKEND_DIR, "telegram_bot.log")

def _get_bot_db():
    if BACKEND_DIR not in sys.path:
        sys.path.insert(0, BACKEND_DIR)
    import bot_db
    return bot_db

def get_bot_token():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        try:
            bot_db = _get_bot_db()
            token = bot_db.get_setting("telegram_bot_token", "").strip()
        except Exception:
            pass
    return token

def check_telegram_token_valid(token: str) -> tuple[bool, dict]:
    """Tests the Telegram Bot Token via Telegram API getMe."""
    if not token:
        return False, {}
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SamshodhanaSTT/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, data.get("result", {})
    except Exception as e:
        logger.warning(f"Failed to validate Telegram bot token: {e}")
    return False, {}

def is_bot_running() -> tuple[bool, int or None]:
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
                # Windows tasklist check
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

    # Fallback scan processes for telegram_bot.py
    try:
        if os.name == "nt":
            cmd = 'wmic process where "name like \'%python%\'" get processid,commandline'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            for line in output.splitlines():
                if "telegram_bot.py" in line:
                    parts = line.strip().split()
                    found_pid = int(parts[-1])
                    with open(PID_FILE, "w") as f:
                        f.write(str(found_pid))
                    return True, found_pid
        else:
            cmd = "ps aux | grep telegram_bot.py | grep -v grep"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
            if output.strip():
                parts = output.strip().split()
                found_pid = int(parts[1])
                with open(PID_FILE, "w") as f:
                    f.write(str(found_pid))
                return True, found_pid
    except Exception:
        pass

    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

    return False, None

def get_full_bot_status() -> dict:
    """Returns complete runtime and configuration status of the Telegram Bot."""
    token = get_bot_token()
    token_configured = bool(token)
    running, pid = is_bot_running()
    
    bot_info = {}
    token_valid = False
    if token_configured:
        token_valid, bot_info = check_telegram_token_valid(token)

    if not token_configured:
        status_code = "missing_token"
        status_label = "🔴 Missing Token"
        status_color = "#ef4444"
    elif not token_valid:
        status_code = "invalid_token"
        status_label = "⚠️ Invalid Token"
        status_color = "#dc2626"
    elif running:
        bot_uname = bot_info.get("username", "")
        uname_str = f" (@{bot_uname})" if bot_uname else ""
        status_code = "running"
        status_label = f"🟢 Running{uname_str}"
        status_color = "#10b981"
    else:
        status_code = "stopped"
        status_label = "🟡 Configured (Stopped)"
        status_color = "#f59e0b"

    return {
        "token_configured": token_configured,
        "token_valid": token_valid,
        "is_running": running,
        "pid": pid,
        "bot_info": bot_info,
        "status_code": status_code,
        "status_label": status_label,
        "status_color": status_color
    }

def _get_python_interpreter() -> str:
    """Finds the best Python executable for running the bot."""
    candidates = []
    
    # 1. Virtualenv Python in directory hierarchy
    curr = BACKEND_DIR
    for _ in range(5):
        if os.name == "nt":
            candidates.append(os.path.join(curr, "venv", "Scripts", "python.exe"))
            candidates.append(os.path.join(curr, ".venv", "Scripts", "python.exe"))
        else:
            candidates.append(os.path.join(curr, "venv", "bin", "python3"))
            candidates.append(os.path.join(curr, "venv", "bin", "python"))
            candidates.append(os.path.join(curr, ".venv", "bin", "python3"))
            candidates.append(os.path.join(curr, ".venv", "bin", "python"))
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    # 2. Current process executable
    candidates.append(sys.executable)

    # First pass: find executable where import telegram already succeeds
    for py_path in candidates:
        if os.path.exists(py_path):
            try:
                res = subprocess.run(
                    [py_path, "-c", "import telegram"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                if res.returncode == 0:
                    return py_path
            except Exception:
                pass

    # Second pass: pick the first existing virtualenv executable
    for py_path in candidates:
        if os.path.exists(py_path) and "venv" in py_path.lower():
            return py_path

    return sys.executable


def _ensure_telegram_dependencies(py_exec: str, log_f) -> None:
    """Auto-installs python-telegram-bot, httpx, python-dotenv if missing in the selected python environment."""
    try:
        res = subprocess.run(
            [py_exec, "-c", "import telegram"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        if res.returncode != 0:
            log_f.write("[BOT SETUP] Installing python-telegram-bot, httpx, python-dotenv...\n")
            log_f.flush()
            subprocess.run(
                [py_exec, "-m", "pip", "install", "python-telegram-bot>=21.0", "httpx", "python-dotenv"],
                stdout=log_f, stderr=subprocess.STDOUT
            )
            log_f.write("[BOT SETUP] Dependencies setup check finished.\n")
            log_f.flush()
    except Exception as e:
        logger.warning(f"Auto-install of telegram dependencies encountered error: {e}")


def start_bot() -> tuple[bool, str]:
    """Launches telegram_bot.py process in background."""
    running, pid = is_bot_running()
    if running:
        return True, f"Bot is already running (PID {pid})."

    token = get_bot_token()
    if not token:
        return False, "Telegram Bot Token is missing. Please set token first."

    script_path = os.path.join(BACKEND_DIR, "telegram_bot.py")
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}"

    try:
        log_f = open(LOG_FILE, "a", encoding="utf-8")
        log_f.write(f"\n--- [BOT STARTING AT {time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
        log_f.flush()

        py_exec = _get_python_interpreter()

        # Ensure python-telegram-bot is installed in target python environment
        _ensure_telegram_dependencies(py_exec, log_f)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["TELEGRAM_BOT_TOKEN"] = token

        # If virtualenv python is selected, adjust PATH and VIRTUAL_ENV
        bin_dir = os.path.dirname(py_exec)
        if "venv" in py_exec.lower():
            venv_dir = os.path.dirname(bin_dir)
            env["VIRTUAL_ENV"] = venv_dir
            env["PATH"] = bin_dir + os.path.pathsep + env.get("PATH", "")

        proc = subprocess.Popen(
            [py_exec, script_path],
            cwd=BACKEND_DIR,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env
        )
        try:
            log_f.close()
        except Exception:
            pass

        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        time.sleep(1.5)
        if proc.poll() is not None:
            err_log = get_bot_logs(15)
            return False, f"Bot exited immediately (code {proc.returncode}). Log snippet:\n{err_log}"

        return True, f"Telegram Bot started successfully (PID {proc.pid})."

    except Exception as e:
        logger.error(f"Error starting Telegram Bot: {e}")
        return False, f"Failed to start bot process: {str(e)}"

def stop_bot() -> tuple[bool, str]:
    """Stops telegram_bot.py background process and cleans up any stray instances."""
    running, pid = is_bot_running()
    
    try:
        if running and pid:
            if os.name == "nt":
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                import signal
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

        # Perform extra cleanup sweep for stray instances matching telegram_bot.py
        if os.name != "nt":
            subprocess.run("pkill -9 -f telegram_bot.py", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(PID_FILE):
            try: os.remove(PID_FILE)
            except Exception: pass

        return True, f"Telegram Bot (PID {pid if pid else 'all'}) stopped successfully."
    except Exception as e:
        return False, f"Error stopping bot process: {str(e)}"

def restart_bot() -> tuple[bool, str]:
    """Restarts telegram_bot.py process."""
    stop_bot()
    time.sleep(1.0)
    return start_bot()

def get_bot_logs(max_lines: int = 50) -> str:
    """Reads the last N lines from telegram_bot.log or systemd journal."""
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
            cmd = f"journalctl -u samshodhana-telegram-bot -n {max_lines} --no-pager"
            logs = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except Exception:
            pass

    return logs if logs.strip() else "No log file found."

if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]
    if "--ensure-running" in args or "autostart" in args:
        token = get_bot_token()
        if token:
            ok, msg = start_bot()
            print(f"[AutoStart] {msg}")
        else:
            print("[AutoStart] Telegram Bot Token not configured yet. Skipping auto-start.")
    elif "start" in args:
        ok, msg = start_bot()
        print(msg)
    elif "stop" in args:
        ok, msg = stop_bot()
        print(msg)
    elif "restart" in args:
        ok, msg = restart_bot()
        print(msg)
    elif "status" in args:
        st = get_full_bot_status()
        print(json.dumps(st, indent=2))

