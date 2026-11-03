import os
import asyncio
import httpx
import logging
import subprocess

logger = logging.getLogger("samshodhana_bot_audio")

SAMSHO_STT_API_URL = os.getenv("SAMSHO_STT_API_URL", "http://localhost:5001/api/v1/stt")
SAMSHO_STT_API_KEY = os.getenv("SAMSHO_STT_API_KEY", "")
SAMSHODHANA_STT_HTTP_URL = SAMSHO_STT_API_URL

try:
    import stt_service
except ImportError:
    try:
        from . import stt_service
    except ImportError:
        import apps.sanskrit_stt.backend.stt_service as stt_service

def get_audio_duration(file_path: str) -> float:
    """Uses ffprobe to get exact audio duration in seconds."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        val = float(result.stdout.strip())
        return val if val > 0 else 5.0
    except Exception as e:
        logger.warning(f"[FFprobe] Could not determine duration: {e}")
        return 5.0

def split_audio_into_chunks(
    file_path: str,
    chunk_duration_sec: float = 60.0,
    output_dir: str = None
) -> list[str]:
    """
    Splits audio file into standardized 16kHz mono WAV chunks using ffmpeg.
    Returns list of chunk file paths in chronological order.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    total_duration = get_audio_duration(file_path)
    if total_duration <= 0:
        return [file_path]

    if output_dir is None:
        output_dir = os.path.dirname(file_path)

    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    chunk_pattern = os.path.join(output_dir, f"{base_name}_chunk_%03d.wav")

    cmd = [
        "ffmpeg", "-y", "-i", file_path,
        "-f", "segment",
        "-segment_time", str(chunk_duration_sec),
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        chunk_pattern
    ]

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info(f"[FFmpeg Chunking] Split '{file_path}' into segment files with pattern '{chunk_pattern}'")
    except Exception as e:
        logger.error(f"[FFmpeg Chunking Error] Failed to split audio: {e}")
        return [file_path]

    chunks = []
    idx = 0
    while True:
        c_path = os.path.join(output_dir, f"{base_name}_chunk_{idx:03d}.wav")
        if os.path.exists(c_path) and os.path.getsize(c_path) > 0:
            chunks.append(c_path)
            idx += 1
        else:
            break

    if not chunks:
        logger.warning("[FFmpeg Chunking] No chunk files generated, using original file")
        return [file_path]

    return chunks

def cleanup_chunk_files(chunk_paths: list[str], original_file: str = None) -> None:
    """Safely removes temporary chunk files from disk."""
    for p in chunk_paths:
        if original_file and os.path.abspath(p) == os.path.abspath(original_file):
            continue
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception as e:
                logger.warning(f"Could not remove chunk file '{p}': {e}")


async def transcribe_audio_file(
    file_path: str,
    language_code: str = "sa-IN",
    stt_url: str = None
) -> tuple[str, int]:
    """
    Submits an audio file to Central Samshodhana Cloud STT API.
    Returns (transcript_text, latency_ms).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    target_url = stt_url or SAMSHO_STT_API_URL
    api_key = SAMSHO_STT_API_KEY
    filename = os.path.basename(file_path)

    logger.info(f"[Samshodhana STT Client] Submitting {filename} (lang={language_code}) to {target_url}")

    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None,
        lambda: stt_service.call_remote_stt_api(
            file_path,
            language_code=language_code,
            filename=filename,
            api_url=target_url,
            api_key=api_key
        )
    )

    transcript = res.get("transcript") or res.get("text") or ""
    latency_ms = res.get("latency_ms", 0)
    return transcript, latency_ms

def transliterate_text(text: str, target_scheme: str = "iast", source_scheme: str = "devanagari") -> str:
    """Transliterates Sanskrit / Indic text into target scheme (iast, tamil, telugu, kannada, malayalam, iso, slp1)."""
    if not text:
        return ""
    target_scheme = target_scheme.lower()
    source_scheme = source_scheme.lower()
    
    if target_scheme in ("devanagari", "sa") and source_scheme in ("devanagari", "sa"):
        return text

    try:
        from vidyut.lipi import Scheme, transliterate
        scheme_map = {
            "devanagari": Scheme.Devanagari, "sa": Scheme.Devanagari,
            "iast": Scheme.Iast,
            "tamil": Scheme.Tamil, "ta": Scheme.Tamil,
            "telugu": Scheme.Telugu, "te": Scheme.Telugu,
            "kannada": Scheme.Kannada, "kn": Scheme.Kannada,
            "malayalam": Scheme.Malayalam, "ml": Scheme.Malayalam,
            "slp1": Scheme.Slp1,
            "iso": Scheme.Iso15919, "iso15919": Scheme.Iso15919,
        }
        src = scheme_map.get(source_scheme, Scheme.Devanagari)
        tgt = scheme_map.get(target_scheme, Scheme.Iast)
        return transliterate(text, src, tgt)
    except Exception as e:
        logger.warning(f"Transliteration fallback error: {e}")
        return text


async def ai_clean_transcript(text: str, language_code: str = "sa-IN") -> str:
    """Clean raw STT transcript using Gemini with strict phonetic proofreading instructions."""
    if not text:
        return ""
        
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:5000")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            endpoints = ["/apps/api/stt/ai_clean", "/api/stt/ai_clean"]
            for ep in endpoints:
                try:
                    resp = await client.post(f"{backend_url.rstrip('/')}{ep}", json={
                        "text": text,
                        "language_code": language_code
                    })
                    if resp.status_code == 200:
                        res_json = resp.json()
                        if res_json.get("success"):
                            return res_json.get("cleaned_text", text)
                except Exception as inner_e:
                    logger.debug(f"HTTP call to {ep} failed: {inner_e}")
    except Exception as e:
        logger.warning(f"Backend API AI clean failed: {e}. Trying direct platform API key fallback.")

    # Direct fallback using config Gemini API key
    try:
        import sys, importlib
        _curr = os.path.abspath(__file__)
        _backend_dir = os.path.dirname(_curr)
        _stt_dir = os.path.dirname(_backend_dir)
        _apps_dir = os.path.dirname(_stt_dir)
        _root_dir = os.path.dirname(_apps_dir)
        _sdl_web_dir = os.path.join(_root_dir, 'sdl_web')

        for p in [_sdl_web_dir, _root_dir, _apps_dir, _backend_dir]:
            if os.path.exists(p) and p not in sys.path:
                sys.path.insert(0, p)

        import config
        import bot_db

        sys_prompt = bot_db.get_ai_clean_prompt()
        model_name = bot_db.get_setting("stt_ai_clean_model", "models/gemini-3.5-flash")

        prompt = f"Language: {language_code}\nSpeech-to-Text Raw Output:\n{text}\n\nProvide the phonetically proofread text:"

        def run_gen(key):
            import google.generativeai as genai
            genai.configure(api_key=key)
            gen_config = genai.types.GenerationConfig(temperature=0.1)
            model = genai.GenerativeModel(model_name, generation_config=gen_config, system_instruction=sys_prompt)
            return model.generate_content(prompt)

        api_key = config.get_gemini_api_key()
        res = run_gen(api_key).text.strip()
        import re
        if res.startswith("```") and res.endswith("```"):
            res = re.sub(r"^```[a-zA-Z]*\n?", "", res)
            res = re.sub(r"\n?```$", "", res).strip()
        return res
    except Exception as gem_e:
        logger.error(f"Direct Gemini platform API key clean error: {gem_e}")
        raise RuntimeError(f"AI Clean failed: {gem_e}")


async def ai_assist_audio_transcript(audio_path: str, text: str, language_code: str = "sa-IN") -> str:
    """Multimodal Audio + Text proofreading using Gemini API."""
    if not text:
        return ""

    backend_url = os.getenv("STT_BACKEND_URL", "http://127.0.0.1:5000")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=45.0) as client:
            audio_bytes = None
            if audio_path and os.path.exists(audio_path):
                try:
                    with open(audio_path, "rb") as af:
                        audio_bytes = af.read()
                except Exception as read_err:
                    logger.warning(f"Could not read audio file {audio_path}: {read_err}")

            endpoints = ["/apps/api/stt/ai_assist", "/api/stt/ai_assist"]
            for ep in endpoints:
                try:
                    files = {}
                    if audio_bytes is not None:
                        files = {"audio": (os.path.basename(audio_path), audio_bytes, "audio/wav")}
                    data = {"text": text, "language_code": language_code}
                    resp = await client.post(f"{backend_url.rstrip('/')}{ep}", data=data, files=files if files else None)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        if res_json.get("success"):
                            return res_json.get("assisted_text", text)
                except Exception as inner_e:
                    logger.debug(f"HTTP call to {ep} failed: {inner_e}")
    except Exception as e:
        logger.warning(f"Backend API AI assist failed: {e}. Trying direct platform API key fallback.")

    import sys, importlib
    _curr = os.path.abspath(__file__)
    _backend_dir = os.path.dirname(_curr)
    _stt_dir = os.path.dirname(_backend_dir)
    _apps_dir = os.path.dirname(_stt_dir)
    _root_dir = os.path.dirname(_apps_dir)
    _sdl_web_dir = os.path.join(_root_dir, 'sdl_web')

    for p in [_sdl_web_dir, _root_dir, _apps_dir, _backend_dir]:
        if os.path.exists(p) and p not in sys.path:
            sys.path.insert(0, p)

    import config
    import bot_db

    sys_prompt = bot_db.get_ai_assist_prompt()
    m_setting = bot_db.get_setting("stt_ai_assist_model", "gemini-3.6-flash")
    raw_m = m_setting.replace("models/", "") if m_setting else "gemini-3.6-flash"
    model_candidates = []
    for cand in [raw_m, f"models/{raw_m}", "gemini-3.6-flash", "models/gemini-3.6-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]:
        if cand not in model_candidates:
            model_candidates.append(cand)

    def run_gen(key):
        import google.generativeai as genai
        genai.configure(api_key=key)
        gen_config = genai.types.GenerationConfig(temperature=0.1)

        prompt_parts = []
        uploaded_file = None
        if audio_path and os.path.exists(audio_path):
            try:
                uploaded_file = genai.upload_file(audio_path)
                prompt_parts.append(uploaded_file)
            except Exception as upload_err:
                logger.warning(f"Audio file upload to Gemini failed: {upload_err}")

        prompt_text = f"Language: {language_code}\nSpeech-to-Text Raw Output Reference:\n{text}\n\nListen to the audio and provide the exact phonetically proofread Sanskrit text:"
        prompt_parts.append(prompt_text)

        last_err = None
        for m_name in model_candidates:
            try:
                model = genai.GenerativeModel(m_name, generation_config=gen_config, system_instruction=sys_prompt)
                result = model.generate_content(prompt_parts)
                if uploaded_file:
                    try:
                        genai.delete_file(uploaded_file.name)
                    except Exception:
                        pass
                return result
            except Exception as gen_err:
                last_err = gen_err
                err_str = str(gen_err)
                if "404" in err_str or "not found" in err_str.lower():
                    logger.warning(f"Gemini model '{m_name}' unavailable/404, trying fallback model...")
                    continue
                if uploaded_file:
                    try:
                        genai.delete_file(uploaded_file.name)
                    except Exception:
                        pass
                raise gen_err

        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass
        if last_err:
            raise last_err

    try:
        api_key = config.get_gemini_api_key()
        res = run_gen(api_key).text.strip()
        import re
        if res.startswith("```") and res.endswith("```"):
            res = re.sub(r"^```[a-zA-Z]*\n?", "", res)
            res = re.sub(r"\n?```$", "", res).strip()
        return res
    except Exception as gem_e:
        logger.error(f"Gemini AI Assist error: {gem_e}")
        raise RuntimeError(f"AI Assist failed: {gem_e}")



