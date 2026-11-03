"""
Process Manager & Status Inspector for Samshodhanam Telegram OCR Bot.
Provides process control (start/stop/restart), log inspection, and OCR token management.
"""

import os
import sys
import time
import signal
import subprocess
import logging
from typing import Dict, Any, List, Tuple, Optional

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot.pid")
RUNNER_PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot_runner.pid")
CHILD_PID_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot_child.pid")
STOP_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot.stop")
LOG_FILE = os.path.join(BOT_DIR, "telegram_ocr_bot.log")

try:
    import apps.ocr_bot.config as config
except ImportError:
    import config

try:
    import apps.ocr_bot.ocr_service as ocr_service
except ImportError:
    import ocr_service

logger = logging.getLogger("ocr_bot_manager")


def get_bot_token() -> str:
    """Dynamically resolves the Telegram Bot Token."""
    if hasattr(config, 'get_telegram_token'):
        return config.get_telegram_token()
    return getattr(config, 'TELEGRAM_BOT_TOKEN', '') or os.getenv("TELEGRAM_OCR_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")


def is_bot_running() -> Tuple[bool, Optional[int]]:
    """
    Robust process and service check for Samshodhanam Telegram OCR Bot.
    Supports PID file verification, systemd service detection, psutil scanning, and CLI fallbacks.
    """
    pid = None
    is_running = False

    # 1. Try checking saved PID files
    for pf in [PID_FILE, RUNNER_PID_FILE, CHILD_PID_FILE]:
        if os.path.exists(pf):
            try:
                with open(pf, "r") as f:
                    candidate_pid = int(f.read().strip())
                if candidate_pid:
                    if sys.platform == "win32":
                        try:
                            import psutil
                            if psutil.pid_exists(candidate_pid):
                                proc = psutil.Process(candidate_pid)
                                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                                    p_cmd = " ".join(proc.cmdline() or [])
                                    if "run_bot.py" in p_cmd or "telegram_bot.py" in p_cmd or "ocr_bot" in p_cmd:
                                        is_running = True
                                        pid = candidate_pid
                                        break
                        except Exception:
                            try:
                                cmd = f'tasklist /FI "PID eq {candidate_pid}"'
                                out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8', errors='ignore')
                                if str(candidate_pid) in out and "python" in out.lower():
                                    is_running = True
                                    pid = candidate_pid
                                    break
                            except Exception:
                                pass
                    else:
                        try:
                            os.kill(candidate_pid, 0)
                            is_running = True
                            pid = candidate_pid
                            break
                        except (OSError, ValueError):
                            pass
            except Exception:
                pass

    # 2. Check systemd service if running on Linux
    if not is_running and sys.platform != "win32":
        for svc_name in ["samshodhana-ocr-bot", "samshodhana-ocr-bot.service"]:
            try:
                cmd_active = f"systemctl is-active {svc_name}"
                res = subprocess.check_output(cmd_active, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore').strip()
                if res == "active":
                    is_running = True
                    try:
                        cmd_pid = f"systemctl show {svc_name} --property=MainPID"
                        pid_out = subprocess.check_output(cmd_pid, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore').strip()
                        if "=" in pid_out:
                            found_pid = int(pid_out.split("=")[1])
                            if found_pid > 0:
                                pid = found_pid
                                try:
                                    with open(PID_FILE, "w") as f:
                                        f.write(str(pid))
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    break
            except Exception:
                pass

    # 3. Try psutil process iteration
    if not is_running:
        try:
            import psutil
            curr_pid = os.getpid()
            for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    if p.pid == curr_pid:
                        continue
                    cmdline_list = p.info.get('cmdline') or []
                    if "-c" in cmdline_list:
                        continue
                    cmdline = " ".join(cmdline_list)
                    # Match OCR bot script names or path
                    if "run_bot.py" in cmdline or ("telegram_bot.py" in cmdline and ("ocr_bot" in cmdline or "apps/ocr_bot" in cmdline)) or "samshodhana-ocr-bot" in cmdline:
                        pid = p.pid
                        is_running = True
                        try:
                            with open(PID_FILE, "w") as f:
                                f.write(str(pid))
                        except Exception:
                            pass
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

    # 4. Fallback process check via OS shell
    if not is_running:
        try:
            if sys.platform == "win32":
                try:
                    cmd = 'powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -notlike \'*-c*\' -and ($_.CommandLine -like \'*run_bot.py*\' -or ($_.CommandLine -like \'*telegram_bot.py*\' -and $_.CommandLine -like \'*ocr_bot*\')) } | Select-Object ProcessId, CommandLine"'
                    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
                    for line in out.splitlines():
                        parts = line.strip().split()
                        if parts and parts[0].isdigit():
                            pid = int(parts[0])
                            is_running = True
                            try:
                                with open(PID_FILE, "w") as f:
                                    f.write(str(pid))
                            except Exception:
                                pass
                            break
                except Exception:
                    pass
            else:
                try:
                    cmd = r"ps aux | grep -E 'run_bot\.py|ocr_bot/telegram_bot\.py' | grep -v -E 'grep|-c'"
                    res = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
                    if res.strip():
                        parts = res.strip().split()
                        if len(parts) > 1 and parts[1].isdigit():
                            pid = int(parts[1])
                            is_running = True
                            try:
                                with open(PID_FILE, "w") as f:
                                    f.write(str(pid))
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    if not is_running:
        for pf in [PID_FILE, RUNNER_PID_FILE, CHILD_PID_FILE]:
            if os.path.exists(pf):
                try:
                    os.remove(pf)
                except Exception:
                    pass

    return is_running, pid


def get_bot_status() -> Dict[str, Any]:
    """Returns process status, OCR API status, and health metrics."""
    is_running, pid = is_bot_running()

    api_url = ocr_service.get_ocr_api_url()
    has_ocr_api = bool(api_url)

    bot_token = get_bot_token()
    has_token = bool(bot_token)
    masked_token = f"{bot_token[:8]}...{bot_token[-4:]}" if len(bot_token) > 12 else ("Configured" if has_token else "Not Set")

    return {
        "is_running": is_running,
        "pid": pid,
        "status_label": "Running" if is_running else "Stopped",
        "has_bot_token": has_token,
        "masked_token": masked_token,
        "has_ocr_api": has_ocr_api,
        "ocr_api_url": api_url
    }


def start_bot() -> Tuple[bool, str]:
    """Starts the Telegram OCR Bot process."""
    if os.path.exists(STOP_FILE):
        try:
            os.remove(STOP_FILE)
        except Exception:
            pass

    is_running, pid = is_bot_running()
    if is_running:
        return True, f"Bot is already running (PID: {pid})"

    token = get_bot_token()
    if not token:
        return False, "Cannot start bot: Telegram Bot Token is missing."

    # If systemd service exists on Linux, try restarting service
    if sys.platform != "win32":
        try:
            cmd = "systemctl restart samshodhana-ocr-bot"
            res = subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res == 0:
                time.sleep(1.5)
                running, new_pid = is_bot_running()
                if running:
                    return True, f"Telegram OCR Bot started via systemd (PID: {new_pid})."
        except Exception:
            pass

    script_path = os.path.join(BOT_DIR, "run_bot.py")
    try:
        if sys.platform == "win32":
            proc = subprocess.Popen([sys.executable, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            proc = subprocess.Popen([sys.executable, script_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        try:
            with open(PID_FILE, "w") as f:
                f.write(str(proc.pid))
            with open(RUNNER_PID_FILE, "w") as f:
                f.write(str(proc.pid))
        except Exception:
            pass

        time.sleep(2.0)
        new_status = get_bot_status()
        if new_status["is_running"]:
            return True, f"Telegram OCR Bot started successfully (PID: {new_status['pid']})."
        return True, "Bot start command issued."
    except Exception as e:
        return False, f"Failed to start bot process: {e}"


def stop_bot() -> Tuple[bool, str]:
    """Stops the Telegram OCR Bot process completely."""
    try:
        # 1. Create stop flag file so runner loop exits cleanly
        try:
            with open(STOP_FILE, "w") as f:
                f.write("stop")
        except Exception:
            pass

        # 2. Stop systemd service if running on Linux
        if sys.platform != "win32":
            try:
                subprocess.call("systemctl stop samshodhana-ocr-bot", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        # 3. Collect PIDs from PID files
        pids_to_kill = set()
        for pf in [PID_FILE, RUNNER_PID_FILE, CHILD_PID_FILE]:
            if os.path.exists(pf):
                try:
                    with open(pf, "r") as f:
                        val = f.read().strip()
                        if val.isdigit():
                            pids_to_kill.add(int(val))
                except Exception:
                    pass

        # 4. Use psutil to find and terminate matching runner & bot processes
        try:
            import psutil
            curr_pid = os.getpid()
            for p in psutil.process_iter(['pid', 'cmdline']):
                try:
                    if p.pid == curr_pid:
                        continue
                    cmdline = " ".join(p.info.get('cmdline') or [])
                    if "run_bot.py" in cmdline or ("telegram_bot.py" in cmdline and ("ocr_bot" in cmdline or "apps/ocr_bot" in cmdline)):
                        pids_to_kill.add(p.pid)
                        try:
                            p.kill()
                        except Exception:
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
        except Exception:
            pass

        # 5. OS-level process termination fallback
        for pid in pids_to_kill:
            if sys.platform == "win32":
                subprocess.call(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.2)
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

        if sys.platform == "win32":
            ps_cmd = 'powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like \'*run_bot.py*\' -or ($_.CommandLine -like \'*telegram_bot.py*\' -and $_.CommandLine -like \'*ocr_bot*\') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
            subprocess.call(ps_cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.call("pkill -9 -f 'run_bot.py'", shell=True, stderr=subprocess.DEVNULL)
            subprocess.call("pkill -9 -f 'apps/ocr_bot'", shell=True, stderr=subprocess.DEVNULL)

        for pf in [PID_FILE, RUNNER_PID_FILE, CHILD_PID_FILE]:
            if os.path.exists(pf):
                try:
                    os.remove(pf)
                except Exception:
                    pass

        time.sleep(1)
        return True, "Telegram OCR Bot process and runner stopped."
    except Exception as e:
        return False, f"Failed to stop bot process: {e}"


def restart_bot() -> Tuple[bool, str]:
    """Restarts the Telegram OCR Bot process."""
    stop_bot()
    time.sleep(1)
    return start_bot()


def get_logs(lines_count: int = 50) -> str:
    """Reads recent log output from telegram_ocr_bot.log or systemd journal."""
    log_path = LOG_FILE
    logs = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                logs = "".join(all_lines[-lines_count:])
        except Exception as e:
            logs = f"Error reading log file: {e}"

    if not logs.strip() and sys.platform != "win32":
        try:
            cmd = f"journalctl -u samshodhana-ocr-bot -n {lines_count} --no-pager"
            logs = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
        except Exception:
            pass

    return logs if logs.strip() else "No log file found."

