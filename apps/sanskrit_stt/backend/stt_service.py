"""
STT Service Core Engine for Samshodhana Speech-to-Text.
Connects directly to the Central Samshodhanam Cloud STT API.
"""

import os
import sys
import time
import json
import logging
import requests
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("stt_service")

# Central Cloud STT API configuration
def get_stt_api_url() -> str:
    """Returns the configured Samshodhanam Cloud STT API URL."""
    return os.getenv("SAMSHO_STT_API_URL", "http://localhost:5001/api/v1/stt")

def get_stt_api_key() -> str:
    """Returns the configured Samshodhanam Cloud STT API Key."""
    return os.getenv("SAMSHO_STT_API_KEY", "")

def call_remote_stt_api(
    audio_path_or_bytes,
    language_code: str = "sa-IN",
    filename: str = "audio.wav",
    api_url: Optional[str] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submits audio to the Central Samshodhanam Cloud STT API.
    Returns dict with transcript text and latency.
    """
    url = (api_url or get_stt_api_url()).strip()
    key = (api_key if api_key is not None else get_stt_api_key()).strip()

    headers = {
        "User-Agent": "Samshodhanam-STT-Client/1.0"
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["X-API-Key"] = key

    data = {
        "language": language_code,
        "language_code": language_code,
        "lang": language_code
    }

    start_time = time.time()
    
    # Support both file path and raw bytes
    if isinstance(audio_path_or_bytes, (bytes, bytearray)):
        files = {"file": (filename, audio_path_or_bytes, "audio/wav")}
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)
    else:
        with open(audio_path_or_bytes, "rb") as f:
            files = {"file": (filename or os.path.basename(audio_path_or_bytes), f, "audio/wav")}
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)

    latency_ms = int((time.time() - start_time) * 1000)

    if resp.status_code in (200, 201):
        res_json = resp.json()
        
        # If response returned an async job_id, poll for completion
        job_id = res_json.get("job_id") if isinstance(res_json, dict) else None
        if job_id and isinstance(res_json, dict) and res_json.get("status") in ("queued", "processing"):
            server_base = url.rsplit("/", 1)[0]
            status_url = f"{server_base}/batch/status/{job_id}"
            poll_start = time.time()
            while time.time() - poll_start < 90:
                time.sleep(0.5)
                try:
                    s_resp = requests.get(status_url, headers=headers, timeout=10)
                    if s_resp.status_code == 200:
                        s_data = s_resp.json()
                        if s_data.get("status") == "completed":
                            res_json = s_data
                            break
                        elif s_data.get("status") == "failed":
                            err = s_data.get("error_message", "Transcription failed on remote server")
                            raise RuntimeError(err)
                except Exception:
                    pass

        text = (res_json.get("transcript") or res_json.get("text") or "").lstrip("\ufeff").strip()
        return {
            "success": True,
            "text": text,
            "transcript": text,
            "latency_ms": latency_ms,
            "raw": res_json
        }
    else:
        err_text = resp.text[:200]
        logger.warning(f"Remote STT API returned HTTP {resp.status_code}: {err_text}")
        raise RuntimeError(f"Cloud STT API error (HTTP {resp.status_code}): {err_text}")

def transcribe_audio_file(file_path: str, language_code: str = "sa-IN") -> Tuple[str, int]:
    """Transcribes an audio file via the Central Cloud STT API. Returns (transcript, latency_ms)."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    res = call_remote_stt_api(file_path, language_code=language_code, filename=os.path.basename(file_path))
    return res.get("transcript", ""), res.get("latency_ms", 0)
