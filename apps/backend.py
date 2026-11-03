import os
import sys
import re
import json
import math
import time
import logging
import threading
import requests
from flask import Blueprint, request, jsonify, session
from sanskrit_processor import SanskritNLPProcessor
try:
    from vidyut.lipi import Scheme, transliterate
except ImportError:
    Scheme = None
    transliterate = None

try:
    import sandhi
except ImportError:
    sandhi = None

try:
    import chanda
except ImportError:
    chanda = None

try:
    from vidyut.prakriya import Vyakarana, Dhatu, Pada, Gana, Prayoga, Lakara, Purusha, Vacana, DhatuPada, Pratipadika, Linga, Vibhakti, Krt, Sanadi, Taddhita
except ImportError:
    Vyakarana = Dhatu = Pada = Gana = Prayoga = Lakara = Purusha = Vacana = DhatuPada = Pratipadika = Linga = Vibhakti = Krt = Sanadi = Taddhita = None

try:
    from sanskrit_parser.api import ParseNode, ParseEdge
except ImportError:
    ParseNode = ParseEdge = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None
import sys
_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_path = os.path.join(_base, 'sdl_web')
if _path not in sys.path:
    sys.path.insert(0, _path)

def get_effective_gemini_key():
    try:
        import config
        return config.get_gemini_api_key()
    except Exception:
        return os.environ.get('GEMINI_API_KEY', '')

apps_bp = Blueprint('apps_backend', __name__)

def _load_isolated_module(module_name: str, file_path: str):
    """Load a module dynamically with full namespace isolation to prevent collisions."""
    import importlib.util, sys
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {module_name} from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

def _get_stt_bot_db():
    p = os.path.join(os.path.dirname(__file__), 'sanskrit_stt', 'backend', 'bot_db.py')
    return _load_isolated_module('apps_sanskrit_stt_bot_db', p)

def _get_stt_bot_manager():
    p = os.path.join(os.path.dirname(__file__), 'sanskrit_stt', 'backend', 'bot_manager.py')
    return _load_isolated_module('apps_sanskrit_stt_bot_manager', p)

def _get_ocr_bot_manager():
    p = os.path.join(os.path.dirname(__file__), 'ocr_bot', 'bot_manager.py')
    return _load_isolated_module('apps_ocr_bot_bot_manager', p)

_get_bot_db = _get_stt_bot_db
_get_bot_manager = _get_stt_bot_manager

def is_request_authenticated():
    from flask import session
    if session.get('user_id') or session.get('logged_in'):
        return True
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ', 1)[1].strip()
        try:
            from db import common_db
            user_id = common_db.verify_user_token(token)
            if user_id:
                return True
        except Exception:
            pass
    # Check access code if present in JSON body, Form data, or Headers
    access_code = None
    if request.is_json and request.json:
        access_code = request.json.get('access_code')
    if not access_code:
        access_code = request.form.get('access_code') or request.headers.get('X-Access-Code')
    if access_code:
        try:
            bot_db = _get_stt_bot_db()
            code_obj = bot_db.get_access_code(access_code.strip().upper())
            if code_obj and code_obj.get('status') == 'active':
                return True
        except Exception:
            pass
    return False

UPASARGAS_PREFIXES_MAP = {
    'pra': ['pra', 'pre', 'pro', 'prA', 'prAr', 'prE', 'prO'], 
    'parA': ['parA', 'pare', 'paro', 'parAr', 'parE', 'parO'], 
    'apa': ['apa', 'ape', 'apo', 'apA', 'apAr', 'apE', 'apO'], 
    'sam': ['sam', 'saM', 'san', 'saR', 'saY', 'saS', 'sal', 'sam'], 
    'anu': ['anu', 'anv', 'anU'], 'ava': ['ava', 'ave', 'avo', 'avA', 'avAr', 'avE', 'avO'], 
    'nis': ['nis', 'nih', 'niH', 'niz', 'niS', 'nI'], 'nir': ['nir', 'nih', 'niH', 'nI'], 
    'dus': ['dus', 'duh', 'duH', 'duz', 'duS', 'dU'], 'dur': ['dur', 'duh', 'duH', 'dU'], 
    'vi': ['vi', 'vy', 'vI'], 'A': ['A', 'e', 'o', 'Ar', 'E', 'O'], 'ni': ['ni', 'ny', 'nI'], 
    'aDi': ['aDi', 'aDy', 'aDI'], 'api': ['api', 'apy', 'apI'], 'ati': ['ati', 'aty', 'atI'], 
    'su': ['su', 'sv', 'sU'], 'ud': ['ud', 'un', 'uc', 'uC', 'uj', 'ut', 'ul', 'uz'], 
    'aBi': ['aBi', 'aBy', 'aBI'], 'prati': ['prati', 'praty', 'pratI'], 
    'pari': ['pari', 'pary', 'parI'], 'upa': ['upa', 'upe', 'upo', 'upA', 'upAr', 'upE', 'upO'], 'pi': ['pi', 'py', 'pI']
}

LAKARA_UI_MAP = {
    'ASIrli~N': 'AshirLin', 'la~N': 'Lan', 'la~w': 'Lat', 'le~w': 'Let',
    'li~w': 'Lit', 'lo~w': 'Lot', 'lf~N': 'Lrn', 'lf~w': 'Lrt',
    'lu~N': 'Lun', 'lu~w': 'Lut', 'viDili~N': 'VidhiLin'
}

PRAYOGA_UI_MAP = {
    'BAve': 'Bhave', 'karmaRi': 'Karmani', 'kartari': 'Kartari'
}

LINGA_UI_MAP = {
    'pum': 'Pum', 'strI': 'Stri', 'napuMsaka': 'Napumsaka'
}

def find_inflected_verb(word_slp1):
    entries = processor.kosha.get(word_slp1)
    for e in entries:
        if 'Tinanta' in str(type(e)):
            return e, []
    for pref_key, variations in UPASARGAS_PREFIXES_MAP.items():
        for var in variations:
            if word_slp1.startswith(var):
                remainder = word_slp1[len(var):]
                entries = processor.kosha.get(remainder)
                for e in entries:
                    if 'Tinanta' in str(type(e)):
                        return e, [pref_key]
                if var.endswith('y'):
                    for v_start in ['i', 'I', 'e', 'a', 'A']:
                        entries = processor.kosha.get(v_start + remainder)
                        for e in entries:
                            if 'Tinanta' in str(type(e)):
                                return e, [pref_key]
                if var.endswith('v'):
                    for v_start in ['u', 'U', 'o', 'a', 'A']:
                        entries = processor.kosha.get(v_start + remainder)
                        for e in entries:
                            if 'Tinanta' in str(type(e)):
                                return e, [pref_key]
    return None, []

def find_inflected_krdanta(word_slp1):
    # Try direct lookup first
    entries = processor.kosha.get(word_slp1)
    for e in entries:
        if 'Subanta' in str(type(e)) and not e.is_avyaya:
            pe = e.pratipadika_entry
            if pe and 'Krdanta' in str(type(pe)):
                return e, []
    # Try strip prefix variations
    for pref_key, variations in UPASARGAS_PREFIXES_MAP.items():
        for var in variations:
            if word_slp1.startswith(var):
                remainder = word_slp1[len(var):]
                entries = processor.kosha.get(remainder)
                for e in entries:
                    if 'Subanta' in str(type(e)) and not e.is_avyaya:
                        pe = e.pratipadika_entry
                        if pe and 'Krdanta' in str(type(pe)):
                            return e, [pref_key]
                if var.endswith('y'):
                    for v_start in ['i', 'I', 'e', 'a', 'A']:
                        entries = processor.kosha.get(v_start + remainder)
                        for e in entries:
                            if 'Subanta' in str(type(e)) and not e.is_avyaya:
                                pe = e.pratipadika_entry
                                if pe and 'Krdanta' in str(type(pe)):
                                    return e, [pref_key]
                if var.endswith('v'):
                    for v_start in ['u', 'U', 'o', 'a', 'A']:
                        entries = processor.kosha.get(v_start + remainder)
                        for e in entries:
                            if 'Subanta' in str(type(e)) and not e.is_avyaya:
                                pe = e.pratipadika_entry
                                if pe and 'Krdanta' in str(type(pe)):
                                    return e, [pref_key]
    return None, []


# Initialize the processor in a background daemon thread to avoid blocking server bootup
workspace_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
data_path = os.path.join(workspace_dir, 'vidyut-data')

processor = None
dhatupatha = []
sutrapatha = {}
shabda_stems = {}
shabda_pratipadikas = {}
_nlp_ready = threading.Event()

SAMSHO_NLP_API_URL = os.environ.get('SAMSHO_NLP_API_URL', 'http://localhost:5001/apps/api')
SAMSHO_NLP_API_KEY = os.environ.get('SAMSHO_NLP_API_KEY', '')


def proxy_nlp_request():
    """Forward an NLP request to the central cloud API when local vidyut-data is not installed."""
    if not SAMSHO_NLP_API_URL:
        return jsonify({
            "success": False,
            "error": "Sanskrit NLP data not installed locally and SAMSHO_NLP_API_URL is not configured."
        }), 503

    rel_path = request.path
    if rel_path.startswith('/apps/api'):
        rel_path = rel_path[len('/apps/api'):]
    rel_path = rel_path.lstrip('/')

    target_url = f"{SAMSHO_NLP_API_URL.rstrip('/')}/{rel_path}"

    headers = {
        "User-Agent": "Open-Samsho-Client/1.0"
    }
    if SAMSHO_NLP_API_KEY:
        headers["Authorization"] = f"Bearer {SAMSHO_NLP_API_KEY}"
        headers["X-API-Key"] = SAMSHO_NLP_API_KEY
    if request.headers.get("Content-Type"):
        headers["Content-Type"] = request.headers.get("Content-Type")

    try:
        if request.method == 'GET':
            resp = requests.get(target_url, headers=headers, params=request.args, timeout=30)
        elif request.method == 'POST':
            if request.is_json:
                resp = requests.post(target_url, headers=headers, json=request.get_json(silent=True), params=request.args, timeout=30)
            else:
                resp = requests.post(target_url, headers=headers, data=request.form, files=request.files, params=request.args, timeout=30)
        else:
            resp = requests.request(request.method, target_url, headers=headers, params=request.args, data=request.get_data(), timeout=30)

        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        response_headers = [(name, value) for (name, value) in resp.headers.items() if name.lower() not in excluded_headers]
        return (resp.content, resp.status_code, response_headers)
    except Exception as e:
        logging.error(f"[NLP Cloud Proxy] Error connecting to {target_url}: {e}")
        return jsonify({
            "success": False,
            "error": f"Failed to connect to central Sanskrit NLP service: {str(e)}"
        }), 502


def _load_nlp_data():
    global processor, dhatupatha, sutrapatha, shabda_stems, shabda_pratipadikas
    t0 = time.time()
    if not os.path.exists(data_path) or not os.path.exists(os.path.join(data_path, 'kosha')):
        logging.info("[NLP] Local vidyut-data not found. Running in Cloud API mode via %s", SAMSHO_NLP_API_URL)
        _nlp_ready.set()
        return

    logging.info("[NLP] Background initialization started from local %s...", data_path)
    try:
        proc = SanskritNLPProcessor(data_path)
        
        # Load dhatupatha
        dp = []
        dhatupatha_path = os.path.join(data_path, 'prakriya', 'dhatupatha.tsv')
        if os.path.exists(dhatupatha_path):
            with open(dhatupatha_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) >= 3:
                        dp.append({
                            "code": parts[0],
                            "dhatu": parts[1],
                            "artha": parts[2]
                        })

        # Load sutrapatha
        sp = {}
        sutrapatha_path = os.path.join(data_path, 'prakriya', 'sutrapatha.tsv')
        if os.path.exists(sutrapatha_path):
            with open(sutrapatha_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.strip().split('\t')
                    if len(parts) >= 2:
                        sp[parts[0]] = parts[1]

        # Load shabda stems list for search autocomplete
        stems = {}
        pratipadikas = {}
        try:
            for entry in proc.kosha.pratipadikas():
                lemma = entry.lemma
                if lemma not in stems:
                    stems[lemma] = set()
                    pratipadikas[lemma] = entry
                for l in entry.lingas:
                    stems[lemma].add(l.name)
                    
            gender_order = {'Pum': 0, 'Stri': 1, 'Napumsaka': 2}
            for lemma in stems:
                stems[lemma] = sorted(list(stems[lemma]), key=lambda g: gender_order.get(g, 9))
                
            if 'Bavat' in stems:
                stems['Bavat'] = ['Pum', 'Stri', 'Napumsaka']
        except Exception as e:
            logging.error("Failed to pre-compile shabda stems: %s", e)

        processor = proc
        dhatupatha = dp
        sutrapatha = sp
        shabda_stems = stems
        shabda_pratipadikas = pratipadikas
        logging.info("[NLP] Background initialization complete in %.2f seconds", time.time() - t0)
    except Exception as ex:
        logging.error("[NLP] Failed to initialize Sanskrit NLP processor: %s", ex)
    finally:
        _nlp_ready.set()

_nlp_thread = threading.Thread(target=_load_nlp_data, name="SanskritNLP-Loader", daemon=True)
_nlp_thread.start()

def ensure_nlp_ready(timeout=25):
    """Wait for background NLP initialization if not yet ready."""
    if not _nlp_ready.is_set():
        _nlp_ready.wait(timeout=timeout)
    return processor is not None

@apps_bp.before_request
def _ensure_nlp_before_request():
    """Ensure NLP models are initialized or forward to Central Cloud NLP API."""
    path = request.path
    rel_path = path
    if rel_path.startswith('/apps/api'):
        rel_path = rel_path[len('/apps/api'):]

    nlp_prefixes = ('/shabda', '/dhatu', '/sandhi', '/samasa', '/pratyaya', '/prakriya', '/vyakarana', '/tarka')
    if any(rel_path.startswith(p) for p in nlp_prefixes):
        if processor is None and (not os.path.exists(data_path) or not os.path.exists(os.path.join(data_path, 'kosha'))):
            return proxy_nlp_request()

        if not _nlp_ready.is_set():
            _nlp_ready.wait(timeout=25)
            if processor is None:
                if SAMSHO_NLP_API_URL:
                    return proxy_nlp_request()
                return jsonify({
                    "success": False,
                    "error": "Sanskrit NLP engine is still initializing. Please retry in a few moments.",
                    "initializing": True
                }), 503


# -----------------------------------------------------------------------------
# 1. SANDHI STUDIO APIs
# -----------------------------------------------------------------------------
def get_sandhi_alternatives(text):
    original_text = text
    # Normalize Vedic LLa (ळ) to la (ल) for parsing/dictionary compatibility
    text = text.replace('ळ', 'ल')
    slp1_text = transliterate(text, Scheme.Devanagari, Scheme.Slp1)
    is_single_word = len(text.split()) == 1
    valid_alternatives = []
    seen_dev_words = set()
    s = sandhi.Sandhi()
    

    parser_splits = []
    try:
        parser_splits = list(processor.syntax_parser.split(text.replace(" ", ""), limit=20))
    except Exception:
        pass
        
    for split in parser_splits:
        words_slp1 = [str(w) for w in split.split]
        if all(processor.kosha.get(w) for w in words_slp1):
            dev_words = tuple(transliterate(w, Scheme.Slp1, Scheme.Devanagari) for w in words_slp1)
            if dev_words not in seen_dev_words:
                seen_dev_words.add(dev_words)
                
                joins = []
                for i in range(len(dev_words) - 1):
                    w1 = dev_words[i]
                    w2 = dev_words[i+1]
                    res = s.sandhi(w1, w2)
                    if res:
                        fused, rule, stype = res[0]
                        w1_disp = w1[:-2] + 'ः' if w1.endswith('स्') or w1.endswith('र्') else w1
                        w2_disp = w2[:-2] + 'ः' if w2.endswith('स्') or w2.endswith('र्') else w2
                        
                        if not rule and stype == w2:
                            stype = "वर्णमेलनम्"
                        elif stype == "वर्णमेलन":
                            stype = "वर्णमेलनम्"
                            
                        joins.append({
                            "word1": w1_disp,
                            "word2": w2_disp,
                            "fused": fused,
                            "rule": rule,
                            "type": stype
                        })
                display_words = []
                for w in dev_words:
                    if w.endswith('स्') or w.endswith('र्'):
                        display_words.append(w[:-2] + 'ः')
                    else:
                        display_words.append(w)
                        
                valid_alternatives.append({
                    "words": display_words,
                    "joins": joins
                })

    if not valid_alternatives:
        cheda_result = processor.cheda.run(slp1_text)
        words = [transliterate(t.text, Scheme.Slp1, Scheme.Devanagari) for t in cheda_result]
        joins = []
        for i in range(len(words) - 1):
            w1 = words[i]
            w2 = words[i+1]
            res = s.sandhi(w1, w2)
            if res:
                fused, rule, stype = res[0]
                w1_disp = w1[:-2] + 'ः' if w1.endswith('स्') or w1.endswith('र्') else w1
                w2_disp = w2[:-2] + 'ः' if w2.endswith('स्') or w2.endswith('र्') else w2
                
                if not rule and stype == w2:
                    stype = "वर्णमेलनम्"
                elif stype == "वर्णमेलन":
                    stype = "वर्णमेलनम्"
                    
                joins.append({
                    "word1": w1_disp,
                    "word2": w2_disp,
                    "fused": fused,
                    "rule": rule,
                    "type": stype
                })
                
        display_words = []
        for w in words:
            if w.endswith('स्') or w.endswith('र्'):
                display_words.append(w[:-2] + 'ः')
            else:
                display_words.append(w)
                
        valid_alternatives.append({
            "words": display_words,
            "joins": joins
        })

    # Restore Vedic LLa (ळ) in results if it was present in the original input
    if 'ळ' in original_text:
        import difflib
        def restore(s):
            if not s:
                return s
            matcher = difflib.SequenceMatcher(None, text, s)
            chars = list(s)
            for i, j, n in matcher.get_matching_blocks():
                for offset in range(n):
                    idx_norm = i + offset
                    idx_s = j + offset
                    if idx_norm < len(original_text) and original_text[idx_norm] == 'ळ':
                        if chars[idx_s] == 'ल':
                            chars[idx_s] = 'ळ'
            return "".join(chars)

        restored_alternatives = []
        for alt in valid_alternatives:
            restored_words = [restore(w) for w in alt["words"]]
            restored_joins = []
            for join in alt["joins"]:
                restored_joins.append({
                    "word1": restore(join["word1"]),
                    "word2": restore(join["word2"]),
                    "fused": restore(join["fused"]),
                    "rule": join["rule"],
                    "type": join["type"]
                })
            restored_alternatives.append({
                "words": restored_words,
                "joins": restored_joins
            })
        valid_alternatives = restored_alternatives

    # Filter out alternatives that are exactly the same as the input (single word with no splits)
    filtered_alternatives = [alt for alt in valid_alternatives if not (len(alt["words"]) == 1 and alt["words"][0] == original_text)]
    
    # Sort remaining so length=1 (if any other form) goes to the bottom
    filtered_alternatives.sort(key=lambda x: len(x["words"]) == 1)
    return filtered_alternatives


@apps_bp.route('/sandhi/split', methods=['POST'])
def sandhi_split():
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({"success": False, "error": "No text provided"})
    
    try:
        alternatives = get_sandhi_alternatives(text)
        if not alternatives:
            return jsonify({
                "success": True,
                "words": [text],
                "joins": [],
                "alternatives": []
            })
        top = alternatives[0]
                
        return jsonify({
            "success": True,
            "words": top["words"],
            "joins": top["joins"],
            "alternatives": alternatives
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/sandhi/join', methods=['POST'])
def sandhi_join():
    data = request.json or {}
    words = data.get('words', [])
    if not words:
        return jsonify({"success": False, "error": "No words provided"})
        
    try:
        s = sandhi.Sandhi()
        steps = []
        current = words[0]
        
        for i in range(1, len(words)):
            next_word = words[i]
            res = s.sandhi(current, next_word)
            if res:
                fused, rule, stype = res[0]
                steps.append({
                    "w1": current,
                    "w2": next_word,
                    "result": fused,
                    "rule": rule,
                    "type": stype
                })
                current = fused
            else:
                fused_combined = current + " " + next_word
                steps.append({
                    "w1": current,
                    "w2": next_word,
                    "result": fused_combined,
                    "rule": "None (No phonetic merger)",
                    "type": "Varnamelana (Direct combination)"
                })
                current = fused_combined
                
        return jsonify({
            "success": True,
            "fused": current,
            "steps": steps
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})




# -----------------------------------------------------------------------------
# 2. CHANDAS METER APIs
# -----------------------------------------------------------------------------
@apps_bp.route('/chandas/analyze', methods=['POST'])
def chandas_analyze():
    data = request.json or {}
    verse = data.get('verse', '').strip()
    if not verse:
        return jsonify({"success": False, "error": "No verse provided"})
        
    try:
        # Load custom / overridden meter patterns
        custom_meters = []
        if os.path.exists(_CHANDAS_METERS_FILE):
            try:
                with open(_CHANDAS_METERS_FILE, 'r', encoding='utf-8') as f:
                    custom_meters = json.load(f)
            except Exception:
                pass
        
        custom_keys = {m['key'] for m in custom_meters}
        all_patterns = custom_meters + [m for m in _BUILTIN_METER_PATTERNS if m['key'] not in custom_keys]

        # Use analyze_text with verse_mode=True to preserve collective meter context
        res = chanda.analyze_text(verse, verse_mode=True, fuzzy=True)
        res_dict = res.result.to_dict()
        
        line_analyses = []
        for line_item in res_dict.get('line', []):
            line_res = line_item.get('result', {})
            chanda_list = line_res.get('chanda', [])
            actual_lg = line_res.get('lg', [])
            
            # Format chanda options
            clean_chanda = [{"name": c[0], "info": ", ".join(map(str, c[1])) if c[1] else ""} for c in chanda_list]
            
            # Check for custom meter pattern matches
            for pattern_def in all_patterns:
                pat = pattern_def.get('pattern', [])
                if len(actual_lg) == len(pat):
                    match_count = sum(1 for i in range(len(actual_lg)) if actual_lg[i] == pat[i])
                    if match_count == len(pat):
                        # Exact match! Add to the candidate list at the top
                        exists = any(c['name'] == pattern_def['name'] for c in clean_chanda)
                        if not exists:
                            clean_chanda.insert(0, {
                                "name": pattern_def['name'],
                                "info": "Custom/Overridden Structure" if not pattern_def.get('builtin') else "Standard Structure"
                            })

            clean_fuzzy = []
            for f in line_res.get('fuzzy', []):
                clean_fuzzy.append({
                    "chanda": f.get('chanda', []),
                    "gana": f.get('gana', ''),
                    "similarity": f.get('similarity', 0.0),
                    "suggestion": f.get('suggestion', [])
                })
                
            line_analyses.append({
                "text": line_res.get('line', ''),
                "syllables": line_res.get('syllables', []),
                "lg": actual_lg,
                "chanda": clean_chanda,
                "fuzzy": clean_fuzzy
            })
            
        # Get overall verse-level meter match
        verse_meters = []
        for v_item in res_dict.get('verse', []):
            chanda_val = v_item.get('chanda', [])
            if chanda_val and isinstance(chanda_val, (list, tuple)):
                if len(chanda_val) > 0 and isinstance(chanda_val[0], (list, tuple)):
                    meter_names = chanda_val[0]
                    for name in meter_names:
                        verse_meters.append({
                            "name": name,
                            "info": ""
                        })
                        
        # Check if all padas match a custom/overridden structure
        for pattern_def in all_patterns:
            pat = pattern_def.get('pattern', [])
            all_padas_match = True
            if len(line_analyses) > 0:
                for la in line_analyses:
                    actual_lg = la.get('lg', [])
                    if len(actual_lg) != len(pat):
                        all_padas_match = False
                        break
                    match_count = sum(1 for i in range(len(actual_lg)) if actual_lg[i] == pat[i])
                    if match_count != len(pat):
                        all_padas_match = False
                        break
            else:
                all_padas_match = False

            if all_padas_match:
                exists = any(v['name'] == pattern_def['name'] for v in verse_meters)
                if not exists:
                    verse_meters.insert(0, {
                        "name": pattern_def['name'],
                        "info": "Custom/Overridden Structure" if not pattern_def.get('builtin') else "Standard Structure"
                    })
                
        return jsonify({
            "success": True,
            "lines": line_analyses,
            "verse_meters": verse_meters
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})



# -----------------------------------------------------------------------------
# 4. DHATU EXPLORER APIs
# -----------------------------------------------------------------------------
def clean_dhatu_slp1(d):
    for char in ['~', '\\', '^', '!']:
        d = d.replace(char, '')
    if len(d) > 1 and d[-1] in ('a', 'i', 'u', 'f', 'x'):
        d = d[:-1]
    return d


@apps_bp.route('/dhatu/search', methods=['GET'])
def search_dhatu():
    q = request.args.get('query', '').strip()
    exact = request.args.get('exact', 'false').lower() == 'true'
    if not q:
        return jsonify([])
        
    slp1_q = clean_dhatu_slp1(transliterate(q, Scheme.Devanagari, Scheme.Slp1)).upper()
    matches = []
    
    try:
        slp1_case = transliterate(q, Scheme.Devanagari, Scheme.Slp1)
        if slp1_case.endswith('H'):
            slp1_case = slp1_case[:-1] + 's'
            
        inflected_verb, found_prefixes = find_inflected_verb(slp1_case)
        if inflected_verb:
            dhatu_entry = inflected_verb.dhatu_entry
            d = dhatu_entry.dhatu
            clean_dhatu = dhatu_entry.clean_text
            aupadeshika = d.aupadeshika
            dev_dhatu = transliterate(clean_dhatu, Scheme.Slp1, Scheme.Devanagari)
            dev_artha = transliterate(dhatu_entry.artha_sa or '', Scheme.Slp1, Scheme.Devanagari)
            
            gana_str = d.gana.name
            lakara = inflected_verb.lakara.name
            prayoga = inflected_verb.prayoga.name
            
            prefixes = list(d.prefixes) if hasattr(d, 'prefixes') and d.prefixes else []
            for p_val in found_prefixes:
                if p_val not in prefixes:
                    prefixes.append(p_val)
                    
            matches.append({
                "is_inflected": True,
                "word": q,
                "dhatu": dev_dhatu,
                "dhatu_slp1": aupadeshika,
                "gana": gana_str,
                "artha": dev_artha,
                "code": "inflected",
                "upasargas": prefixes,
                "lakara": lakara,
                "prayoga": prayoga,
                "highlight": q
            })
        else:
            inflected_krt, found_prefixes = find_inflected_krdanta(slp1_case)
            if inflected_krt:
                pe = inflected_krt.pratipadika_entry
                dhatu_entry = pe.dhatu_entry
                d = dhatu_entry.dhatu
                clean_dhatu = dhatu_entry.clean_text
                aupadeshika = d.aupadeshika
                dev_dhatu = transliterate(clean_dhatu, Scheme.Slp1, Scheme.Devanagari)
                dev_artha = transliterate(dhatu_entry.artha_sa or '', Scheme.Slp1, Scheme.Devanagari)
                
                gana_str = d.gana.name
                
                prefixes = list(d.prefixes) if hasattr(d, 'prefixes') and d.prefixes else []
                for p_val in found_prefixes:
                    if p_val not in prefixes:
                        prefixes.append(p_val)
                        
                matches.append({
                    "is_inflected": True,
                    "is_krdanta": True,
                    "word": q,
                    "dhatu": dev_dhatu,
                    "dhatu_slp1": aupadeshika,
                    "gana": gana_str,
                    "artha": dev_artha,
                    "code": "inflected",
                    "upasargas": prefixes,
                    "highlight": q,
                    "krt_affix": pe.krt.name
                })
    except Exception as e:
        logging.error("Failed to parse inflected verb/krdanta in search: %s", e)
    
    for d in dhatupatha:
        dev_dhatu = transliterate(d["dhatu"], Scheme.Slp1, Scheme.Devanagari)
        dev_artha = transliterate(d["artha"], Scheme.Slp1, Scheme.Devanagari)
        
        clean_d = clean_dhatu_slp1(d["dhatu"]).upper()
        
        matches_cond = False
        if exact:
            clean_dev_dhatu = dev_dhatu.replace('ँ', '').replace('\\', '').replace('्', '')
            clean_q = q.replace('्', '')
            matches_cond = (clean_d == slp1_q or clean_dev_dhatu == clean_q)
        else:
            matches_cond = (slp1_q in clean_d or 
                            q in dev_dhatu or 
                            slp1_q in d["artha"].upper() or 
                            q in dev_artha or 
                            q in d["code"])
                            
        if matches_cond:
            gana_num = d["code"].split('.')[0]
            gana_names = {
                "01": "Bhvadi", "02": "Adadi", "03": "Juhotyadi", "04": "Divadi",
                "05": "Svadi", "06": "Tudadi", "07": "Rudhadi", "08": "Tanadi",
                "09": "Kryadi", "10": "Curadi"
            }
            gana_name = gana_names.get(gana_num, "Bhvadi")
            
            matches.append({
                "code": d["code"],
                "dhatu": dev_dhatu,
                "dhatu_slp1": d["dhatu"],
                "artha": dev_artha,
                "artha_slp1": d["artha"],
                "gana": gana_name
            })
            
            if len(matches) >= 20:
                break
                
    return jsonify(matches)


def filter_citation_forms(words):
    # Remove voiced final consonant variant (e.g. -d) if the corresponding voiceless variant (e.g. -t) is present
    voiceless_map = {
        '\u0917\u094d': '\u0915\u094d', # ग् -> क्
        '\u0921\u094d': '\u091f\u094d', # ड् -> ट्
        '\u0926\u094d': '\u0924\u094d', # द् -> त्
        '\u092c\u094d': '\u092a\u094d', # ब् -> प्
    }
    to_remove = set()
    for w in words:
        for voiced, voiceless in voiceless_map.items():
            if w.endswith(voiced):
                prefix = w[:-len(voiced)]
                corresponding_voiceless = prefix + voiceless
                if corresponding_voiceless in words:
                    to_remove.add(w)
                    break
    return [w for w in words if w not in to_remove]


@apps_bp.route('/dhatu/derive', methods=['POST'])
def derive_dhatu():
    data = request.json or {}
    dhatu_slp1 = data.get('dhatu')
    gana_str = data.get('gana')
    lakara_str = data.get('lakara')
    prayoga_str = data.get('prayoga')
    sanadi_str = data.get('sanadi', 'Mula')
    upasargas = data.get('upasargas', [])
    
    if not all([dhatu_slp1, gana_str, lakara_str, prayoga_str]):
        return jsonify({"success": False, "error": "Missing parameters"})
        
    try:
        gana = getattr(Gana, gana_str)
        prayoga = getattr(Prayoga, prayoga_str)
        
        v = processor.prakriya
        d = Dhatu.mula(dhatu_slp1, gana)
        
        if sanadi_str == 'Nic':
            d = d.with_sanadi([Sanadi.Ric])
        elif sanadi_str == 'San':
            d = d.with_sanadi([Sanadi.san])
        elif sanadi_str == 'Yan':
            d = d.with_sanadi([Sanadi.yaN])
        elif sanadi_str == 'Yanluk':
            d = d.with_sanadi([Sanadi.yaNluk])
            
        if upasargas:
            d = d.with_prefixes(upasargas)
        
        lakaras_to_derive = []
        if lakara_str == "All":
            lakaras_to_derive = ["Lat", "Lit", "Lut", "Lrt", "Lot", "Lan", "VidhiLin", "AshirLin", "Lun", "Lrn", "Let"]
        else:
            lakaras_to_derive = [lakara_str]
            
        all_grids = {}
        
        for lak_name in lakaras_to_derive:
            lak_enum = getattr(Lakara, lak_name)
            grids = {
                "Parasmaipada": [],
                "Atmanepada": []
            }
            
            for pada_name, pada_enum in [("Parasmaipada", DhatuPada.Parasmaipada), ("Atmanepada", DhatuPada.Atmanepada)]:
                grid = []
                for purusha_str, purusha_enum in [("Prathama", Purusha.Prathama), ("Madhyama", Purusha.Madhyama), ("Uttama", Purusha.Uttama)]:
                    row = []
                    for vacana_str, vacana_enum in [("Eka", Vacana.Eka), ("Dvi", Vacana.Dvi), ("Bahu", Vacana.Bahu)]:
                        try:
                            p = Pada.Tinanta(d, prayoga, lak_enum, purusha_enum, vacana_enum, dhatu_pada=pada_enum)
                            prakriyas = v.derive(p)
                            if prakriyas:
                                words_list = []
                                all_steps = []
                                for prak in prakriyas:
                                    w_dev = transliterate(prak.text, Scheme.Slp1, Scheme.Devanagari)
                                    if w_dev not in words_list:
                                        words_list.append(w_dev)
                                    
                                    if not all_steps:
                                        for step in prak.history:
                                            sutra_slp1 = sutrapatha.get(step.code, '')
                                            sutra_dev = transliterate(sutra_slp1, Scheme.Slp1, Scheme.Devanagari) if sutra_slp1 else ''
                                            valid_terms = [x for x in step.result if x.strip()]
                                            result_dev = [transliterate(x, Scheme.Slp1, Scheme.Devanagari) for x in valid_terms]
                                            all_steps.append({
                                                "code": step.code,
                                                "sutra": sutra_dev,
                                                "result": " + ".join(result_dev)
                                            })
                                    
                                filtered_words = filter_citation_forms(words_list)
                                row.append({
                                    "word": " / ".join(filtered_words),
                                    "purusha": purusha_str,
                                    "vacana": vacana_str,
                                    "steps": all_steps
                                })
                            else:
                                row.append({"word": "-", "purusha": purusha_str, "vacana": vacana_str, "steps": []})
                        except Exception as ex:
                            row.append({"word": "-", "purusha": purusha_str, "vacana": vacana_str, "steps": [], "error": str(ex)})
                    grid.append(row)
                    
                has_words = any(cell["word"] != "-" for row in grid for cell in row)
                if has_words:
                    grids[pada_name] = grid
            
            non_empty_grids = {k: v for k, v in grids.items() if v}
            if non_empty_grids:
                all_grids[lak_name] = non_empty_grids
                
        return jsonify({
            "success": True,
            "is_all": (lakara_str == "All"),
            "grids": all_grids if (lakara_str == "All") else list(all_grids.values())[0] if all_grids else {}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# -----------------------------------------------------------------------------
# 4.5 KRDANTA (PARTICIPLE) EXPLORER APIs
# -----------------------------------------------------------------------------
@apps_bp.route('/dhatu/derive_krt', methods=['POST'])
def derive_dhatu_krt():
    data = request.json or {}
    dhatu_slp1 = data.get('dhatu')
    gana_str = data.get('gana')
    sanadi_str = data.get('sanadi', 'Mula')
    upasargas = data.get('upasargas', [])
    
    if not all([dhatu_slp1, gana_str]):
        return jsonify({"success": False, "error": "Missing parameters"})
        
    try:
        gana = getattr(Gana, gana_str)
        v = processor.prakriya
        d = Dhatu.mula(dhatu_slp1, gana)
        
        if sanadi_str == 'Nic':
            d = d.with_sanadi([Sanadi.Ric])
        elif sanadi_str == 'San':
            d = d.with_sanadi([Sanadi.san])
        elif sanadi_str == 'Yan':
            d = d.with_sanadi([Sanadi.yaN])
        elif sanadi_str == 'Yanluk':
            d = d.with_sanadi([Sanadi.yaNluk])
            
        if upasargas:
            d = d.with_prefixes(upasargas)
            
        krt_results = []
        
        # Get all valid affix names from the Krt class
        affix_names = [x for x in dir(Krt) if not x.startswith('_') and x not in ['anubandhas', 'choices', 'drshya', 'from_string', 'name', 'value']]
        
        for affix_name in affix_names:
            krt_affix = getattr(Krt, affix_name)
            try:
                prat = Pratipadika.krdanta(d, krt_affix)
                
                genders_data = {}
                for g_key, g_enum in [("pum", Linga.Pum), ("stri", Linga.Stri), ("napumsaka", Linga.Napumsaka)]:
                    p = Pada.Subanta(prat, g_enum, Vibhakti.Prathama, Vacana.Eka)
                    prakriyas = v.derive(p)
                    if prakriyas:
                        words_list = []
                        all_steps = []
                        for prak in prakriyas:
                            w_dev = transliterate(prak.text, Scheme.Slp1, Scheme.Devanagari)
                            if w_dev not in words_list:
                                words_list.append(w_dev)
                            
                            if not all_steps:
                                for step in prak.history:
                                    sutra_slp1 = sutrapatha.get(step.code, '')
                                    sutra_dev = transliterate(sutra_slp1, Scheme.Slp1, Scheme.Devanagari) if sutra_slp1 else ''
                                    valid_terms = [x for x in step.result if x.strip()]
                                    result_dev = [transliterate(x, Scheme.Slp1, Scheme.Devanagari) for x in valid_terms]
                                    all_steps.append({
                                        "code": step.code,
                                        "sutra": sutra_dev,
                                        "result": " + ".join(result_dev)
                                    })
                        filtered_words = filter_citation_forms(words_list)
                        genders_data[g_key] = {
                            "word": " / ".join(filtered_words),
                            "steps": all_steps
                        }
                    else:
                        genders_data[g_key] = {
                            "word": "-",
                            "steps": []
                        }
                
                has_forms = any(genders_data[g]["word"] != "-" for g in genders_data)
                if has_forms:
                    affix_dev = transliterate(krt_affix.name, Scheme.Slp1, Scheme.Devanagari)
                    krt_results.append({
                        "affix": affix_dev,
                        "affix_slp1": krt_affix.name,
                        "genders": genders_data
                    })
            except Exception:
                pass
                
        return jsonify({
            "success": True,
            "results": krt_results
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def get_shabda_search_variants(slp1):
    variants = [slp1]
    if slp1.endswith('H') or slp1.endswith('z') or slp1.endswith('S'):
        s_form = slp1[:-1] + 's'
        if s_form not in variants:
            variants.append(s_form)
    if slp1.endswith('s'):
        for ending in ['z', 'S', 'H']:
            alt = slp1[:-1] + ending
            if alt not in variants:
                variants.append(alt)
    if slp1.endswith('za') or slp1.endswith('Sa') or slp1.endswith('sa'):
        s_form = slp1[:-2] + 's'
        if s_form not in variants:
            variants.append(s_form)
        z_form = slp1[:-1]
        if z_form not in variants:
            variants.append(z_form)
    return variants


def get_stem_display_dev(stem_slp1):
    # In Sanskrit grammar tradition and standard lexicons, is/us stems are presented as shakaranta (षकारान्त: आयुष्, धनुष्, हविष्, चक्षुष्, सर्पिष्, यजुष्, ज्योतिष्, वपुष्)
    if stem_slp1.endswith('is') or stem_slp1.endswith('us'):
        stem_z = stem_slp1[:-1] + 'z'
        return transliterate(stem_z, Scheme.Slp1, Scheme.Devanagari), stem_z
    return transliterate(stem_slp1, Scheme.Slp1, Scheme.Devanagari), stem_slp1


def fix_is_us_satva(stem_slp1, word_slp1):
    if stem_slp1.endswith('is') or stem_slp1.endswith('us'):
        base = stem_slp1[:-1]
        word_slp1 = re.sub(r'(' + re.escape(base) + r')s([aAiIuUeEoOM])', r'\1z\2', word_slp1)
        word_slp1 = re.sub(r'(' + re.escape(base) + r')ss([uU])', r'\1zz\2', word_slp1)
        if stem_slp1.endswith('us'):
            stem_root = stem_slp1[:-2]
            word_slp1 = re.sub(r'(' + re.escape(stem_root) + r')[uU][mM]si', r'\1UMzi', word_slp1)
            word_slp1 = re.sub(r'(' + re.escape(stem_root) + r')[uU][mM]zi', r'\1UMzi', word_slp1)
        elif stem_slp1.endswith('is'):
            stem_root = stem_slp1[:-2]
            word_slp1 = re.sub(r'(' + re.escape(stem_root) + r')[iI][mM]si', r'\1IMzi', word_slp1)
            word_slp1 = re.sub(r'(' + re.escape(stem_root) + r')[iI][mM]zi', r'\1IMzi', word_slp1)
    return word_slp1


def fix_is_us_satva_terms(stem_slp1, terms):
    if stem_slp1.endswith('is') or stem_slp1.endswith('us'):
        new_terms = list(terms)
        for i in range(len(new_terms)):
            if new_terms[i].endswith('s'):
                if i + 1 < len(new_terms) and new_terms[i+1] and (new_terms[i+1][0] in 'aAiIuUeEoOM' or new_terms[i+1].startswith('s')):
                    new_terms[i] = new_terms[i][:-1] + 'z'
        return new_terms
    return terms


@apps_bp.route('/shabda/decline', methods=['POST'])
def decline_shabda():
    data = request.json or {}
    stem_dev = data.get('stem', '').strip()
    linga_str = data.get('linga', '').strip() # 'Pum', 'Stri', 'Napumsaka'
    taddhita_str = data.get('taddhita', 'None')
    
    if not all([stem_dev, linga_str]):
        return jsonify({"success": False, "error": "Missing parameters"})
        
    # Convert stem to SLP1
    stem_slp1 = data.get('stem_slp1', '').strip()
    if not stem_slp1:
        stem_slp1 = transliterate(stem_dev, Scheme.Devanagari, Scheme.Slp1)
        
    # Support phonetic & grammatical variants (e.g. Ayuz/AyuH -> Ayus, Danuz -> Danus)
    if stem_slp1 not in shabda_stems:
        for v_slp1 in get_shabda_search_variants(stem_slp1):
            if v_slp1 in shabda_stems:
                stem_slp1 = v_slp1
                stem_dev = transliterate(stem_slp1, Scheme.Slp1, Scheme.Devanagari)
                break
                
    # Restrict to stems existing in the dictionary
    if stem_slp1 not in shabda_stems:
        return jsonify({
            "success": False,
            "error": f"The stem '{stem_dev}' is not found in the dictionary."
        })
        
    # Restrict to genders existing for this stem
    allowed_genders = shabda_stems[stem_slp1]
    if linga_str not in allowed_genders:
        if len(allowed_genders) == 1:
            linga_str = allowed_genders[0]
        else:
            gender_labels = {'Pum': 'Masculine (पुं.)', 'Stri': 'Feminine (स्त्री.)', 'Napumsaka': 'Neuter (नपुं.)'}
            allowed_labels = [gender_labels.get(g, g) for g in allowed_genders]
            return jsonify({
                "success": False,
                "error": f"The stem '{stem_dev}' is not available in {gender_labels.get(linga_str, linga_str)}. Available genders: {', '.join(allowed_labels)}."
            })
    
    # Hardcode Bavat (भवत्) pronoun since Vidyut Python wrapper lacks Dhatu constructor for dynamic Krdanta derivation
    if stem_slp1 == 'Bavat':
        forms = []
        if linga_str == 'Pum':
            forms = [
                ['BavAn', 'BavantO', 'BavantaH'],
                ['Bavantam', 'BavantO', 'BavataH'],
                ['BavatA', 'BavadByAm', 'BavadBiH'],
                ['Bavate', 'BavadByAm', 'BavadByaH'],
                ['BavataH', 'BavadByAm', 'BavadByaH'],
                ['BavataH', 'BavatoH', 'BavatAm'],
                ['Bavati', 'BavatoH', 'Bavatsu'],
                ['Bavan', 'BavantO', 'BavantaH']
            ]
        elif linga_str == 'Stri':
            # bhavatI is regular river-declension (nadI)
            stem_dev = transliterate('BavatI', Scheme.Slp1, Scheme.Devanagari)
        elif linga_str == 'Napumsaka':
            forms = [
                ['Bavat', 'BavatI', 'Bavanti'],
                ['Bavat', 'BavatI', 'Bavanti'],
                ['BavatA', 'BavadByAm', 'BavadBiH'],
                ['Bavate', 'BavadByAm', 'BavadByaH'],
                ['BavataH', 'BavadByAm', 'BavadByaH'],
                ['BavataH', 'BavatoH', 'BavatAm'],
                ['Bavati', 'BavatoH', 'Bavatsu'],
                ['Bavat', 'BavatI', 'Bavanti']
            ]
        
        if forms:
            grid = []
            vibhakti_names = ["Prathama", "Dvitiya", "Trtiya", "Caturthi", "Panchami", "Sasthi", "Saptami", "Sambodhana"]
            vacana_names = ["Eka", "Dvi", "Bahu"]
            for i, row_forms in enumerate(forms):
                row = []
                for j, form_slp1 in enumerate(row_forms):
                    row.append({
                        "word": transliterate(form_slp1, Scheme.Slp1, Scheme.Devanagari),
                        "vibhakti": vibhakti_names[i],
                        "vacana": vacana_names[j],
                        "steps": []
                    })
                grid.append(row)
            disp_stem_dev, _ = get_stem_display_dev(stem_slp1)
            return jsonify({"success": True, "stem": disp_stem_dev, "linga": linga_str, "grid": grid})

    try:
        linga = getattr(Linga, linga_str)
        v = processor.prakriya
        
        pe = shabda_pratipadikas.get(stem_slp1)
        if pe:
            try:
                p_args = pe.to_prakriya_args()
                prakriyas = v.derive(p_args)
                if prakriyas and prakriyas[0].text != stem_slp1:
                    pe = None
            except:
                pe = None

        # Special check: if stem is 'rE' (रै), we must use basic Pratipadika to avoid incorrect Krdanta derivation to 'rA'
        if stem_slp1 == 'rE':
            p = Pratipadika.basic(stem_slp1)
        elif pe:
            p = pe.to_prakriya_args()
        else:
            if linga == Linga.Stri and (stem_slp1.endswith('A') or stem_slp1.endswith('I')):
                p = Pratipadika.nyap(stem_slp1)
            else:
                p = Pratipadika.basic(stem_slp1)
        
        # Vidyut generator fails for Ugit stems (matup/vatup/SatR) due to missing constructors and bugs.
        # So we manually decline any stem ending in 'vat' or 'mat' for Pum/Napumsaka.
        if stem_slp1.endswith('vat') or stem_slp1.endswith('mat'):
            is_vat = stem_slp1.endswith('vat')
            base = stem_slp1[:-3] # everything before 'vat'/'mat'
            v_char = 'v' if is_vat else 'm'
            
            forms = []
            if linga_str == 'Pum':
                forms = [
                    [f"{base}{v_char}An", f"{base}{v_char}antO", f"{base}{v_char}antaH"],
                    [f"{base}{v_char}antam", f"{base}{v_char}antO", f"{base}{v_char}ataH"],
                    [f"{base}{v_char}atA", f"{base}{v_char}adByAm", f"{base}{v_char}adBiH"],
                    [f"{base}{v_char}ate", f"{base}{v_char}adByAm", f"{base}{v_char}adByaH"],
                    [f"{base}{v_char}ataH", f"{base}{v_char}adByAm", f"{base}{v_char}adByaH"],
                    [f"{base}{v_char}ataH", f"{base}{v_char}atoH", f"{base}{v_char}atAm"],
                    [f"{base}{v_char}ati", f"{base}{v_char}atoH", f"{base}{v_char}atsu"],
                    [f"{base}{v_char}an", f"{base}{v_char}antO", f"{base}{v_char}antaH"]
                ]
            elif linga_str == 'Napumsaka':
                forms = [
                    [f"{base}{v_char}at", f"{base}{v_char}atI", f"{base}{v_char}anti"],
                    [f"{base}{v_char}at", f"{base}{v_char}atI", f"{base}{v_char}anti"],
                    [f"{base}{v_char}atA", f"{base}{v_char}adByAm", f"{base}{v_char}adBiH"],
                    [f"{base}{v_char}ate", f"{base}{v_char}adByAm", f"{base}{v_char}adByaH"],
                    [f"{base}{v_char}ataH", f"{base}{v_char}adByAm", f"{base}{v_char}adByaH"],
                    [f"{base}{v_char}ataH", f"{base}{v_char}atoH", f"{base}{v_char}atAm"],
                    [f"{base}{v_char}ati", f"{base}{v_char}atoH", f"{base}{v_char}atsu"],
                    [f"{base}{v_char}at", f"{base}{v_char}atI", f"{base}{v_char}anti"]
                ]
            elif linga_str == 'Stri':
                # For feminine, convert -vat to -vatI and decline normally using Vidyut
                p = Pratipadika.nyap(stem_slp1 + 'I')
                # Clear forms so it drops through to the standard Vidyut generator
                forms = []
            
            if forms:
                grid = []
                vibhakti_names = ["Prathama", "Dvitiya", "Trtiya", "Caturthi", "Panchami", "Sasthi", "Saptami", "Sambodhana"]
                vacana_names = ["Eka", "Dvi", "Bahu"]
                for i, row_forms in enumerate(forms):
                    row = []
                    for j, form_slp1 in enumerate(row_forms):
                        row.append({
                            "word": transliterate(form_slp1, Scheme.Slp1, Scheme.Devanagari),
                            "vibhakti": vibhakti_names[i],
                            "vacana": vacana_names[j],
                            "steps": []
                        })
                    grid.append(row)
                disp_stem_dev, _ = get_stem_display_dev(stem_slp1)
                return jsonify({
                    "success": True, 
                    "stem": disp_stem_dev, 
                    "linga": linga_str, 
                    "grid": grid
                })
        
        if taddhita_str != 'None':
            taddhita_enum = getattr(Taddhita, taddhita_str)
            p = Pratipadika.taddhitanta(p, taddhita_enum)
        
        grid = []
        vibhakti_names = ["Prathama", "Dvitiya", "Trtiya", "Caturthi", "Panchami", "Sasthi", "Saptami", "Sambodhana"]
        vibhakti_enums = [Vibhakti.Prathama, Vibhakti.Dvitiya, Vibhakti.Trtiya, Vibhakti.Caturthi, Vibhakti.Panchami, Vibhakti.Sasthi, Vibhakti.Saptami, Vibhakti.Sambodhana]
        
        vacana_names = ["Eka", "Dvi", "Bahu"]
        vacana_enums = [Vacana.Eka, Vacana.Dvi, Vacana.Bahu]
        
        for vib_idx, vib_enum in enumerate(vibhakti_enums):
            row = []
            vib_str = vibhakti_names[vib_idx]
            for vac_idx, vac_enum in enumerate(vacana_enums):
                vac_str = vacana_names[vac_idx]
                try:
                    pada = Pada.Subanta(p, linga, vib_enum, vac_enum)
                    prakriyas = v.derive(pada)
                    if prakriyas:
                        words_list = []
                        all_steps = []
                        for prak in prakriyas:
                            fixed_text = fix_is_us_satva(stem_slp1, prak.text)
                            w_dev = transliterate(fixed_text, Scheme.Slp1, Scheme.Devanagari)
                            if w_dev not in words_list:
                                words_list.append(w_dev)
                            
                            if not all_steps:
                                has_satva_added = False
                                needs_satva = (stem_slp1.endswith('is') or stem_slp1.endswith('us')) and (fix_is_us_satva(stem_slp1, prak.text) != prak.text)
                                already_has_8_3_59 = any(step.code == '8.3.59' for step in prak.history)

                                for step in prak.history:
                                    if needs_satva and not already_has_8_3_59 and not has_satva_added and step.code == '8.4.68':
                                        last_terms = [x for x in step.result if x.strip()]
                                        fixed_terms = fix_is_us_satva_terms(stem_slp1, last_terms)
                                        all_steps.append({
                                            "code": "8.3.59",
                                            "sutra": transliterate(sutrapatha.get('8.3.59', 'AdeSapratyayayoH'), Scheme.Slp1, Scheme.Devanagari),
                                            "result": " + ".join([transliterate(x, Scheme.Slp1, Scheme.Devanagari) for x in fixed_terms])
                                        })
                                        has_satva_added = True

                                    valid_terms = [x for x in step.result if x.strip()]
                                    if has_satva_added:
                                        valid_terms = fix_is_us_satva_terms(stem_slp1, valid_terms)

                                    sutra_slp1 = sutrapatha.get(step.code, '')
                                    sutra_dev = transliterate(sutra_slp1, Scheme.Slp1, Scheme.Devanagari) if sutra_slp1 else ''
                                    result_dev = [transliterate(x, Scheme.Slp1, Scheme.Devanagari) for x in valid_terms]
                                    all_steps.append({
                                        "code": step.code,
                                        "sutra": sutra_dev,
                                        "result": " + ".join(result_dev)
                                    })
                                    
                        filtered_words = filter_citation_forms(words_list)
                        row.append({
                            "word": " / ".join(filtered_words),
                            "vibhakti": vib_str,
                            "vacana": vac_str,
                            "steps": all_steps
                        })
                    else:
                        row.append({"word": "-", "vibhakti": vib_str, "vacana": vac_str, "steps": []})
                except Exception as ex:
                    row.append({"word": "-", "vibhakti": vib_str, "vacana": vac_str, "steps": [], "error": str(ex)})
            grid.append(row)
            
        disp_stem_dev, _ = get_stem_display_dev(stem_slp1)
        return jsonify({
            "success": True,
            "stem": disp_stem_dev,
            "linga": linga_str,
            "grid": grid
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@apps_bp.route('/shabda/search', methods=['GET'])
def search_shabda():
    q = request.args.get('query', '').strip()
    exact = request.args.get('exact', 'false').lower() == 'true'
    if not q:
        return jsonify([])
        
    slp1_q = transliterate(q, Scheme.Devanagari, Scheme.Slp1)
    variants = get_shabda_search_variants(slp1_q)
    
    inflected_matches = []
    v = Vyakarana()
    stem_groups = {}
    
    for v_q in variants:
        try:
            entries = processor.kosha.get(v_q)
            for e in entries:
                if 'Subanta' in str(type(e)) and not e.is_avyaya:
                    try:
                        pe = e.pratipadika_entry
                        p_args = Pratipadika.basic(e.lemma) if e.lemma == 'rE' else pe.to_prakriya_args()
                        prakriyas = v.derive(p_args)
                        stem_slp1 = None
                        if prakriyas:
                            stem_slp1 = prakriyas[0].text
                        if not stem_slp1:
                            stem_slp1 = ''.join([c for c in e.lemma if c.isalpha()])
                            
                        linga_str = e.linga.name
                            
                        if stem_slp1 not in shabda_stems or linga_str not in shabda_stems[stem_slp1]:
                            continue
                            
                        key = (stem_slp1, linga_str)
                        if key not in stem_groups:
                            stem_groups[key] = set()
                        stem_groups[key].add(linga_str)
                    except:
                        continue
        except Exception:
            pass
                    
    # Ensure that if any variant is an exact stem, all its dictionary genders are represented
    for v_q in variants:
        if v_q in shabda_stems:
            for linga_str in shabda_stems[v_q]:
                key = (v_q, linga_str)
                if key not in stem_groups:
                    stem_groups[key] = set()
                    stem_groups[key].add(linga_str)
                    
    exact_stem_matches = []
    seen_exact = set()
    for v_q in variants:
        if v_q in shabda_stems and v_q not in seen_exact:
            seen_exact.add(v_q)
            disp_dev, disp_slp1 = get_stem_display_dev(v_q)
            exact_stem_matches.append({
                "stem": disp_dev,
                "stem_slp1": disp_slp1,
                "lingas": shabda_stems[v_q]
            })
            
    exact_stem_set = {m['stem_slp1'] for m in exact_stem_matches}
    for (stem_slp1, linga_str), lingas in stem_groups.items():
        disp_dev, disp_slp1 = get_stem_display_dev(stem_slp1)
        stem_z = transliterate(stem_slp1[:-1] + 'z', Scheme.Slp1, Scheme.Devanagari) if stem_slp1.endswith('s') else ''
        stem_H = transliterate(stem_slp1[:-1] + 'H', Scheme.Slp1, Scheme.Devanagari) if stem_slp1.endswith('s') else ''
        stem_s = transliterate(stem_slp1, Scheme.Slp1, Scheme.Devanagari)
        if (disp_slp1 in exact_stem_set or stem_slp1 in exact_stem_set) and q in [disp_dev, stem_z, stem_H, stem_s]:
            continue
        inflected_matches.append({
            "is_inflected": True,
            "word": q,
            "stem": disp_dev,
            "stem_slp1": disp_slp1,
            "lingas": [linga_str],
            "highlight": q
        })
        
    prefix_stem_matches = []
    containment_stem_matches = []
    
    if not exact:
        for lemma, lingas in shabda_stems.items():
            if lemma in seen_exact:
                continue
            disp_dev, disp_slp1 = get_stem_display_dev(lemma)
            if any(lemma.startswith(v_q) for v_q in variants) or any(disp_slp1.startswith(v_q) for v_q in variants):
                prefix_stem_matches.append({
                    "stem": disp_dev,
                    "stem_slp1": disp_slp1,
                    "lingas": lingas
                })
            elif any(v_q in lemma for v_q in variants) or any(v_q in disp_slp1 for v_q in variants):
                containment_stem_matches.append({
                    "stem": disp_dev,
                    "stem_slp1": disp_slp1,
                    "lingas": lingas
                })
            
    # Deduplicate matches while preserving order
    seen_keys = set()
    final_matches = []
    for item in (exact_stem_matches + inflected_matches + prefix_stem_matches[:10] + containment_stem_matches):
        k = (item.get('stem_slp1'), item.get('is_inflected', False), tuple(item.get('lingas', [])))
        if k not in seen_keys:
            seen_keys.add(k)
            final_matches.append(item)
            if len(final_matches) >= 20:
                break
                
    return jsonify(final_matches)


# -----------------------------------------------------------------------------
# 5. SMART SANSKRIT READER APIs
# -----------------------------------------------------------------------------
@apps_bp.route('/reader/analyze_word', methods=['POST'])
def analyze_word_reader():
    data = request.json or {}
    word = data.get('word', '').strip()
    context = data.get('context', '').strip()
    
    if not word:
        return jsonify({"success": False, "error": "No word provided"})
        
    try:
        slp1_text = transliterate(word, Scheme.Devanagari, Scheme.Slp1)
        cheda_result = processor.cheda.run(slp1_text)
        
        splits = []
        for t in cheda_result:
            base = t.lemma
            entries = processor.kosha.get(t.text)
            tag_desc = ""
            if entries:
                tag_desc = str(entries[0])
                if "pratipadika_entry" in tag_desc:
                    tag_desc = tag_desc.split("pratipadika_entry=")[0].strip()
                
            splits.append({
                "word": transliterate(t.text, Scheme.Slp1, Scheme.Devanagari),
                "lemma": transliterate(t.lemma, Scheme.Slp1, Scheme.Devanagari),
                "desc": tag_desc
            })
            
        # Call Gemini for meaning
        def run_generate(api_key):
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("models/gemini-3.5-flash")
            
            prompt = f"Given the Sanskrit word/phrase: \"{word}\"\n"
            if context:
                prompt += f"Context sentence: \"{context}\"\n"
            prompt += (
                "Provide a clear, brief English translation and grammatical breakdown (such as case, root, tense). "
                "Respond in clean, simple HTML format. Avoid markdown formatting inside the HTML. Keep it very concise (less than 100 words)."
            )
            res = model.generate_content(prompt)
            return res.text
            
        api_key = get_effective_gemini_key()
        if not api_key:
            fallback_key = os.environ.get('GEMINI_API_KEY')
            if not fallback_key:
                key_file = os.path.join(workspace_dir, 'sdl_web', 'gemini_key.json')
                if os.path.exists(key_file):
                    try:
                        with open(key_file, 'r') as kf:
                            kdata = json.load(kf)
                            fallback_key = kdata.get('api_key') or kdata.get('GEMINI_API_KEY')
                    except Exception:
                        pass
            api_key = fallback_key
        if not api_key:
            raise ValueError("No Gemini API key available")
        meaning_html = run_generate(api_key)
        
        return jsonify({
            "success": True,
            "word": word,
            "splits": splits,
            "meaning": meaning_html
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/sandhi/split_explain', methods=['POST'])
def sandhi_split_explain():
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({"success": False, "error": "No text provided"})
        
    try:
        alternatives = get_sandhi_alternatives(text)
        if not alternatives:
            return jsonify({
                "success": True,
                "original": text,
                "words": [text],
                "joins": [],
                "alternatives": []
            })
        top = alternatives[0]
        return jsonify({
            "success": True,
            "original": text,
            "words": top["words"],
            "joins": top["joins"],
            "alternatives": alternatives
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# -----------------------------------------------------------------------------
# 6. ASHTADHYAYI COMPANION & KOSHA APIs
# -----------------------------------------------------------------------------
import sqlite3

def get_vyakarana_db():
    db_path = os.path.join(workspace_dir, 'db', 'vyakarana_kosha.db')
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@apps_bp.route('/ashtadhyayi/sutras', methods=['GET'])
def get_ashtadhyayi_sutras():
    query = request.args.get('query', '').strip()
    order_by = request.args.get('order_by', 'ashtadhyayi').strip()
    if not query:
        return jsonify({"success": False, "error": "No query provided"})

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})

    try:
        cursor = conn.cursor()
        
        import re
        sk_range_match = re.match(r'^sk:(\d+)-(\d+)$', query)
        
        if sk_range_match:
            start_num = int(sk_range_match.group(1))
            end_num = int(sk_range_match.group(2))
            cursor.execute(
                "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE sk_number >= ? AND sk_number <= ? ORDER BY sk_number ASC",
                (start_num, end_num)
            )
        else:
            # 1. Check if query looks like a reference (e.g. 1.1.1 or 1.1)
            ref_match = re.match(r'^([1-8])(?:[\.\s]([1-4]))?(?:[\.\s](\d+))?$', query)
            
            if ref_match:
                a = ref_match.group(1)
                p = ref_match.group(2)
                n = ref_match.group(3)
                
                if a and p and n:
                    cursor.execute(
                        "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE adhyaya = ? AND pada = ? AND number = ?",
                        (int(a), int(p), int(n))
                    )
                elif a and p:
                    cursor.execute(
                        "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE adhyaya = ? AND pada = ? ORDER BY number ASC",
                        (int(a), int(p))
                    )
                else:
                    cursor.execute(
                        "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE adhyaya = ? ORDER BY pada ASC, number ASC",
                        (int(a),)
                    )
            else:
                # Transliterate query for SLP1 match
                query_slp1 = transliterate(query, Scheme.Devanagari, Scheme.Slp1)
                
                # Substring match on sutra Devanagari or SLP1
                if order_by == 'kaumudi':
                    cursor.execute(
                        "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE sutra LIKE ? OR sutra_slp1 LIKE ? OR padachheda LIKE ? ORDER BY (case when sk_number is null or sk_number = 0 then 999999 else sk_number end) ASC, adhyaya ASC, pada ASC, number ASC LIMIT 100",
                        (f"%{query}%", f"%{query_slp1}%", f"%{query}%")
                    )
                else:
                    cursor.execute(
                        "SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english FROM sutraani WHERE sutra LIKE ? OR sutra_slp1 LIKE ? OR padachheda LIKE ? ORDER BY adhyaya ASC, pada ASC, number ASC LIMIT 100",
                        (f"%{query}%", f"%{query_slp1}%", f"%{query}%")
                    )
            
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/sutra/<int:idx>', methods=['GET'])
def get_ashtadhyayi_sutra_detail(idx):
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sutraani WHERE idx = ?", (idx,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return jsonify({"success": False, "error": "Sutra not found"})

        sutra_dict = dict(row)

        # Build sutra reference string (e.g. "1.1.9")
        sutra_ref = f"{sutra_dict['adhyaya']}.{sutra_dict['pada']}.{sutra_dict['number']}"

        # Fetch vartikas for this sutra
        cursor.execute("SELECT vartika FROM vartikas WHERE sutra_ref = ?", (sutra_ref,))
        vartika_rows = cursor.fetchall()
        sutra_dict['vartikas'] = [r['vartika'] for r in vartika_rows]

        # Fetch prayogas (literary usage examples) for this sutra
        cursor.execute("SELECT word, source_text, loc, url, pada, ref FROM sutra_prayogas WHERE sutra_ref = ?", (sutra_ref,))
        prayoga_rows = cursor.fetchall()
        sutra_dict['prayogas'] = [dict(r) for r in prayoga_rows]

        # Fetch ganapatha entries associated with this sutra
        cursor.execute("SELECT name, words, vartika, type FROM ganapatha WHERE sutra = ?", (sutra_ref,))
        ganapatha_rows = cursor.fetchall()
        sutra_dict['ganapatha'] = [dict(r) for r in ganapatha_rows]

        conn.close()
        return jsonify({"success": True, "sutra": sutra_dict})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/sutra_by_ref/<ref>', methods=['GET'])
def get_ashtadhyayi_sutra_by_ref(ref):
    parts = ref.split('.')
    if len(parts) != 3:
        return jsonify({"success": False, "error": "Invalid sutra reference format"})
    
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
        
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT idx FROM sutraani WHERE adhyaya = ? AND pada = ? AND number = ?", (int(parts[0]), int(parts[1]), int(parts[2])))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": f"Sutra {ref} not found"})
        
        idx = row['idx']
        conn.close()
        return get_ashtadhyayi_sutra_detail(idx)
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/shivasutras', methods=['GET'])
def get_shivasutras():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM shivasutras ORDER BY id ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/ganapatha', methods=['GET'])
def get_ganapatha():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ind, name, sutra, vartika, words, type FROM ganapatha ORDER BY ind ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/unadipatha', methods=['GET'])
def get_unadipatha():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, sutra, pratyay, sk FROM unadipatha ORDER BY CAST(id as integer) ASC, id ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/linganushasanam', methods=['GET'])
def get_linganushasanam():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, adhikaar, sutra, sk FROM linganushasanam ORDER BY CAST(id as integer) ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/shiksha', methods=['GET'])
def get_shiksha():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, text, pc, anvaya, artha, tatparya FROM shiksha ORDER BY CAST(id as integer) ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/phitsutrani', methods=['GET'])
def get_phitsutrani():
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, p, n, s, sk FROM phitsutrani ORDER BY CAST(id as integer) ASC")
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/kosha/search', methods=['GET'])
def search_kosha():
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "error": "No query provided"})

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})

    try:
        cursor = conn.cursor()
        query_slp1 = transliterate(query, Scheme.Devanagari, Scheme.Slp1)
        
        # 1. Search in standard dictionaries
        # Exact match ONLY
        cursor.execute(
            "SELECT dict_name, word, entry_indices FROM kosha_words WHERE word = ? OR word_slp1 = ?",
            (query, query_slp1)
        )
        rows = cursor.fetchall()
            
        # All supported dictionary keys
        results = {
            "ap90": [],
            "mw": [],
            "skd": [],
            "abhyankar": [],
            "wil": [],
            "ben": [],
            "cae": [],
            "md": [],
            "shs": [],
            "yat": [],
            "vcp": [],
            "amara": [],
            "halayudha": [],
            "yaadavakosha": []
        }
        
        # Group word indices by dictionary
        indices_by_dict = {}
        for row in rows:
            dname = row["dict_name"]
            indices_str = row["entry_indices"]
            if not indices_str:
                continue
            if dname not in indices_by_dict:
                indices_by_dict[dname] = set()
            for idx_val in indices_str.split(','):
                indices_by_dict[dname].add(idx_val.strip())
                
        # Retrieve definitions for each dictionary
        for dname, indices in indices_by_dict.items():
            if not indices:
                continue
            if dname not in results:
                results[dname] = []
            # Chunk indices to prevent SQL expression limit errors (999 limit)
            indices_list = list(indices)
            chunk_size = 500
            for i in range(0, len(indices_list), chunk_size):
                chunk = indices_list[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(
                    f"SELECT entry_idx, definition FROM kosha_entries WHERE dict_name = ? AND entry_idx IN ({placeholders})",
                    [dname] + chunk
                )
                entry_rows = cursor.fetchall()
                for erow in entry_rows:
                    # Find which word maps to this definition
                    matched_words = [row["word"] for row in rows if row["dict_name"] == dname and erow["entry_idx"] in row["entry_indices"].split(',')]
                    results[dname].append({
                        "word": matched_words[0] if matched_words else query,
                        "definition": erow["definition"]
                    })

        # 2. Search in Amarakosha Synonym Verses
        # Exact match in the words_json list only
        cursor.execute(
            "SELECT num, text, words_json FROM amara_verses WHERE words_json LIKE ?",
            (f'%"{query}"%',)
        )
        amara_rows = cursor.fetchall()
        for arow in amara_rows:
            import json
            results["amara"].append({
                "num": arow["num"],
                "text": arow["text"],
                "synonyms": json.loads(arow["words_json"])
            })

        # 2b. Search in Halayudha Synonym Verses
        # Exact match in the words_json list only
        cursor.execute(
            "SELECT num, text, words_json FROM halayudha_verses WHERE words_json LIKE ?",
            (f'%"{query}"%',)
        )
        halayudha_rows = cursor.fetchall()
        for hrow in halayudha_rows:
            import json
            results["halayudha"].append({
                "num": hrow["num"],
                "text": hrow["text"],
                "synonyms": json.loads(hrow["words_json"])
            })

        # 2c. Search in Yadavakosha Synonym Verses
        # Exact match in the words_json list only
        cursor.execute(
            "SELECT num, text, words_json FROM yaadavakosha_verses WHERE words_json LIKE ?",
            (f'%"{query}"%',)
        )
        yaadava_rows = cursor.fetchall()
        for yrow in yaadava_rows:
            import json
            results["yaadavakosha"].append({
                "num": yrow["num"],
                "text": yrow["text"],
                "synonyms": json.loads(yrow["words_json"])
            })

        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/texts/<text_name>', methods=['GET'])
def get_text_list(text_name):
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        if text_name == 'mahabhashyam':
            cursor.execute("SELECT id, file_id, adhikarana_id, adhikarana_name, chunk_id FROM mahabhashyam ORDER BY file_id ASC, CAST(adhikarana_id AS INTEGER) ASC, CAST(chunk_id AS INTEGER) ASC")
        elif text_name == 'vakyapadeeyam':
            cursor.execute("SELECT id, kanda, samuddesh, adhikaar, verse_num, text FROM vakyapadeeyam ORDER BY CAST(kanda AS INTEGER) ASC, CASE WHEN samuddesh = '' THEN 0 ELSE CAST(samuddesh AS INTEGER) END ASC, id ASC")
        elif text_name == 'paribhashendushekhar':
            cursor.execute("SELECT id, num, paribhasha FROM paribhashendushekhar ORDER BY CAST(num AS INTEGER) ASC")
        elif text_name == 'bhushanasara':
            cursor.execute("SELECT id, num, section, kaarika FROM bhushanasara ORDER BY CAST(num AS INTEGER) ASC")
        elif text_name == 'paramalaghumanjoosha':
            cursor.execute("SELECT id, chapter, name FROM paramalaghumanjoosha ORDER BY CAST(chapter AS INTEGER) ASC")
        elif text_name == 'tarkasangraha':
            cursor.execute("SELECT id, item_id, topic, text FROM tarkasangraha ORDER BY CAST(item_id AS INTEGER) ASC")
        else:
            conn.close()
            return jsonify({"success": False, "error": "Unknown text"})

        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        conn.close()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})


@apps_bp.route('/ashtadhyayi/texts/<text_name>/<int:entry_id>', methods=['GET'])
def get_text_detail(text_name, entry_id):
    conn = get_vyakarana_db()
    if not conn:
        return jsonify({"success": False, "error": "Grammar database not compiled"})
    try:
        cursor = conn.cursor()
        if text_name == 'mahabhashyam':
            cursor.execute("SELECT id, file_id, adhikarana_id, adhikarana_name, chunk_id, bhashya, pradeep, uddyot FROM mahabhashyam WHERE id = ?", (entry_id,))
        elif text_name == 'vakyapadeeyam':
            cursor.execute("SELECT id, kanda, samuddesh, adhikaar, verse_num, text, artha, svopajna, ambakartri FROM vakyapadeeyam WHERE id = ?", (entry_id,))
        elif text_name == 'paribhashendushekhar':
            cursor.execute("SELECT id, num, prelude, paribhasha, text FROM paribhashendushekhar WHERE id = ?", (entry_id,))
        elif text_name == 'bhushanasara':
            cursor.execute("SELECT id, num, section_id, section, kaarika_id, prelude, kaarika, vyakhyaa FROM bhushanasara WHERE id = ?", (entry_id,))
        elif text_name == 'paramalaghumanjoosha':
            cursor.execute("SELECT id, chapter, name, text FROM paramalaghumanjoosha WHERE id = ?", (entry_id,))
        elif text_name == 'tarkasangraha':
            cursor.execute("SELECT id, item_id, category, topic, text, teeka FROM tarkasangraha WHERE id = ?", (entry_id,))
        else:
            conn.close()
            return jsonify({"success": False, "error": "Unknown text"})

        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify({"success": True, "data": dict(row)})
        else:
            return jsonify({"success": False, "error": "Entry not found"})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({"success": False, "error": str(e)})




# -----------------------------------------------------------------------------
# CHANDAS ADMIN APIs
# -----------------------------------------------------------------------------

_CHANDAS_SAMPLES_FILE = os.path.join(workspace_dir, 'apps', 'chandas', 'samples.json')
_CHANDAS_LAKSHANA_FILE = os.path.join(workspace_dir, 'apps', 'chandas', 'lakshana.json')


def _is_admin_session():
    """Verify if the current session belongs to an authorized admin."""
    return bool(session.get('logged_in') or session.get('admin_role') == 'super' or 'PERM_MANAGE_AI' in session.get('admin_permissions', []))


@apps_bp.route('/chandas/admin/samples', methods=['GET'])
def chandas_admin_get_samples():
    """Return saved sample verses for the Chandas admin panel."""
    try:
        if os.path.exists(_CHANDAS_SAMPLES_FILE):
            with open(_CHANDAS_SAMPLES_FILE, 'r', encoding='utf-8') as f:
                samples = json.load(f)
            return jsonify({"success": True, "samples": samples})
        return jsonify({"success": True, "samples": []})
    except Exception as e:
        logging.error(f"Chandas Admin: Error loading samples: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/chandas/admin/samples', methods=['POST'])
def chandas_admin_save_samples():
    """Save sample verses for the Chandas app."""
    if not _is_admin_session():
        return jsonify({"success": False, "error": "Admin login required"}), 401

    data = request.get_json(silent=True)
    if not data or "samples" not in data or not isinstance(data.get("samples"), list):
        return jsonify({"success": False, "error": "Invalid payload: 'samples' list is required"}), 400

    samples = data["samples"]
    if not all(isinstance(s, dict) for s in samples):
        return jsonify({"success": False, "error": "Each sample must be an object with verse details"}), 400

    try:
        os.makedirs(os.path.dirname(_CHANDAS_SAMPLES_FILE), exist_ok=True)
        with open(_CHANDAS_SAMPLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": "Sample verses saved successfully."})
    except Exception as e:
        logging.error(f"Chandas Admin: Error saving samples: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/chandas/admin/lakshana', methods=['GET'])
def chandas_admin_get_lakshana():
    """Return saved Lakshana presets for the Chandas admin panel."""
    try:
        if os.path.exists(_CHANDAS_LAKSHANA_FILE):
            with open(_CHANDAS_LAKSHANA_FILE, 'r', encoding='utf-8') as f:
                lakshana = json.load(f)
            return jsonify({"success": True, "lakshana": lakshana})
        return jsonify({"success": True, "lakshana": []})
    except Exception as e:
        logging.error(f"Chandas Admin: Error loading lakshana presets: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/chandas/admin/lakshana', methods=['POST'])
def chandas_admin_save_lakshana():
    """Save Lakshana presets for the Chandas app."""
    if not _is_admin_session():
        return jsonify({"success": False, "error": "Admin login required"}), 401

    data = request.get_json(silent=True)
    if not data or "lakshana" not in data or not isinstance(data.get("lakshana"), list):
        return jsonify({"success": False, "error": "Invalid payload: 'lakshana' list is required"}), 400

    lakshana = data["lakshana"]
    if not all(isinstance(l, dict) for l in lakshana):
        return jsonify({"success": False, "error": "Each lakshana preset must be an object"}), 400

    try:
        os.makedirs(os.path.dirname(_CHANDAS_LAKSHANA_FILE), exist_ok=True)
        with open(_CHANDAS_LAKSHANA_FILE, 'w', encoding='utf-8') as f:
            json.dump(lakshana, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": "Lakshana presets saved successfully."})
    except Exception as e:
        logging.error(f"Chandas Admin: Error saving lakshana presets: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# -----------------------------------------------------------------------------
# CHANDAS CUSTOM METER PATTERN APIs  (Laghu-Guru structure definitions)
# -----------------------------------------------------------------------------

_CHANDAS_METERS_FILE = os.path.join(workspace_dir, 'apps', 'chandas', 'custom_meters.json')

# Built-in Laghu-Guru patterns for reference (standard classical meters)
_BUILTIN_METER_PATTERNS = [
    {
        "key": "anushtubh",
        "name": "Anushtubh (अनुष्टुभ्)",
        "padas": 4,
        "syllables_per_pada": 8,
        "pattern": ["ल", "ल", "ग", "ल", "ग", "ग", "ल", "ग"],
        "description": "The most common Sanskrit meter, 8 syllables per pāda, 4 pādas. Positions 5-8: ˘ — — ˘ (fixed).",
        "builtin": True
    },
    {
        "key": "indravajra",
        "name": "Indravajra (इन्द्रवज्रा)",
        "padas": 4,
        "syllables_per_pada": 11,
        "pattern": ["ग", "ग", "ल", "ग", "ग", "ल", "ल", "ग", "ल", "ग", "ग"],
        "description": "11-syllable meter. Gaṇas: t-t-j-g-g (— — ˘ — | — ˘ ˘ — | ˘ — —).",
        "builtin": True
    },
    {
        "key": "vasantatilaka",
        "name": "Vasantatilaka (वसन्ततिलका)",
        "padas": 4,
        "syllables_per_pada": 14,
        "pattern": ["ग", "ग", "ल", "ग", "ल", "ल", "ल", "ग", "ल", "ग", "ल", "ग", "ग", "ग"],
        "description": "14-syllable meter. Gaṇas: t-bh-j-j-g (— — ˘ — | ˘ ˘ ˘ — | ˘ — ˘ — | — —).",
        "builtin": True
    },
    {
        "key": "mandakranta",
        "name": "Mandakranta (मन्दाक्रान्ता)",
        "padas": 4,
        "syllables_per_pada": 17,
        "pattern": ["ग", "ग", "ग", "ग", "ल", "ल", "ल", "ल", "ग", "ग", "ल", "ग", "ग", "ल", "ग", "ग", "ग"],
        "description": "17-syllable meter. Gaṇas: m-bh-n-t-t-g (— — — — | ˘ ˘ ˘ ˘ | — — ˘ — | — ˘ — —).",
        "builtin": True
    },
    {
        "key": "shardula",
        "name": "Shardulavikridita (शार्दूलविक्रीडित)",
        "padas": 4,
        "syllables_per_pada": 19,
        "pattern": ["ग", "ग", "ग", "ल", "ल", "ग", "ल", "ल", "ल", "ल", "ग", "ल", "ग", "ग", "ग", "ग", "ल", "ग", "ग"],
        "description": "19-syllable meter. Gaṇas: m-s-j-s-t-t-g (— — — ˘ ˘ — | ˘ ˘ ˘ ˘ — ˘ | — — — — ˘ — —).",
        "builtin": True
    }
]


@apps_bp.route('/chandas/admin/meters', methods=['GET'])
def chandas_admin_get_meters():
    """Return all custom meter pattern definitions (custom + built-in)."""
    try:
        custom = []
        if os.path.exists(_CHANDAS_METERS_FILE):
            with open(_CHANDAS_METERS_FILE, 'r', encoding='utf-8') as f:
                custom = json.load(f)

        # Merge: custom entries override built-ins with same key
        custom_keys = {m['key'] for m in custom}
        builtin = [m for m in _BUILTIN_METER_PATTERNS if m['key'] not in custom_keys]

        all_meters = builtin + custom
        return jsonify({"success": True, "meters": all_meters})
    except Exception as e:
        logging.error(f"Chandas Admin: Error loading meter patterns: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/chandas/admin/meters', methods=['POST'])
def chandas_admin_save_meters():
    """Save custom meter pattern definitions (only non-builtin ones persist)."""
    if not _is_admin_session():
        return jsonify({"success": False, "error": "Admin login required"}), 401

    data = request.get_json(silent=True)
    if not data or "meters" not in data or not isinstance(data.get("meters"), list):
        return jsonify({"success": False, "error": "Invalid payload: 'meters' list is required"}), 400

    meters = data["meters"]
    if not all(isinstance(m, dict) for m in meters):
        return jsonify({"success": False, "error": "Each meter definition must be an object"}), 400

    # Strip builtin flag before saving; only persist custom entries
    custom_only = [m for m in meters if not m.get('builtin')]

    try:
        os.makedirs(os.path.dirname(_CHANDAS_METERS_FILE), exist_ok=True)
        with open(_CHANDAS_METERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(custom_only, f, ensure_ascii=False, indent=2)
        return jsonify({"success": True, "message": f"Saved {len(custom_only)} custom meter pattern(s)."})
    except Exception as e:
        logging.error(f"Chandas Admin: Error saving meter patterns: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/chandas/admin/meters/match', methods=['POST'])
def chandas_admin_match_meter():
    """
    Analyze a verse with the chanda engine and compare each pāda's LG sequence
    against a provided custom meter pattern key. Returns similarity score and
    mismatched syllable positions.
    """
    data = request.get_json() or {}
    verse = data.get('verse', '').strip()
    meter_key = data.get('meter_key', '').strip()

    if not verse or not meter_key:
        return jsonify({"success": False, "error": "Both verse and meter_key are required."}), 400

    # Load the meter definition
    target_pattern = None
    if os.path.exists(_CHANDAS_METERS_FILE):
        try:
            with open(_CHANDAS_METERS_FILE, 'r', encoding='utf-8') as f:
                custom = json.load(f)
            for m in custom:
                if m['key'] == meter_key:
                    target_pattern = m
                    break
        except Exception:
            pass

    if target_pattern is None:
        for m in _BUILTIN_METER_PATTERNS:
            if m['key'] == meter_key:
                target_pattern = m
                break

    if target_pattern is None:
        return jsonify({"success": False, "error": f"Meter pattern '{meter_key}' not found."}), 404

    expected_lg = target_pattern.get('pattern', [])

    try:
        res = chanda.analyze_text(verse, verse_mode=True, fuzzy=True)
        res_dict = res.result.to_dict()

        pada_results = []
        for line_item in res_dict.get('line', []):
            line_res = line_item.get('result', {})
            actual_lg = line_res.get('lg', [])
            syllables = line_res.get('syllables', [])
            text = line_res.get('line', '')

            # Compare position by position
            mismatches = []
            matches = 0
            compare_len = min(len(actual_lg), len(expected_lg))

            for i in range(compare_len):
                if actual_lg[i] == expected_lg[i]:
                    matches += 1
                else:
                    mismatches.append({
                        "position": i + 1,
                        "syllable": syllables[i] if i < len(syllables) else "?",
                        "actual": actual_lg[i],
                        "expected": expected_lg[i]
                    })

            similarity = matches / len(expected_lg) if expected_lg else 0.0

            pada_results.append({
                "text": text,
                "syllables": syllables,
                "actual_lg": actual_lg,
                "expected_lg": expected_lg,
                "mismatches": mismatches,
                "match_count": matches,
                "similarity": round(similarity, 4),
                "is_perfect": len(mismatches) == 0 and len(actual_lg) == len(expected_lg)
            })

        return jsonify({
            "success": True,
            "meter_name": target_pattern['name'],
            "padas": pada_results
        })
    except Exception as e:
        logging.error(f"Chandas Admin: Error in meter match: {e}")
        return jsonify({"success": False, "error": str(e)}), 500




# =============================================================================
# SANSKRIT SPEECH-TO-TEXT (SAMSHODHANA STT BACKEND INTEGRATION)
# =============================================================================

@apps_bp.route('/stt/status', methods=['GET'])
def stt_status():
    """Check status of Samshodhana STT backend server on port 8091 and Telegram Bot."""
    import urllib.request
    stt_host = os.getenv("SAMSHODHANA_STT_HOST", os.getenv("STT_HOST", os.getenv("VEXYL_STT_HOST", "127.0.0.1")))
    stt_port = int(os.getenv("SAMSHODHANA_STT_PORT", os.getenv("STT_PORT", os.getenv("VEXYL_STT_PORT", "8091"))))
    if stt_host == "0.0.0.0":
        stt_host = "127.0.0.1"

    bot_status = {}
    try:
        bot_mgr = _get_bot_manager()
        bot_status = bot_mgr.get_full_bot_status()
    except Exception as b_err:
        bot_status = {"is_running": False, "status_code": "error", "error": str(b_err)}

    stt_api_url = os.getenv("SAMSHO_STT_API_URL", "http://localhost:5001/api/v1/stt")
    return jsonify({
        "success": True,
        "online": True,
        "loading": False,
        "status_text": "ready",
        "api_url": stt_api_url,
        "bot_status": bot_status,
        "mode": "cloud_api",
        "message": "Samshodhanam Central Cloud STT API is ready."
    })



@apps_bp.route('/stt/transcribe', methods=['POST'])
def stt_transcribe():
    """Proxy batch audio file transcription to Central Samshodhana Cloud STT API."""
    if not is_request_authenticated():
        return jsonify({
            "success": False, 
            "error": "Login required to upload audio and use Speech-to-Text. Please log in or enter a valid access code.", 
            "login_required": True
        }), 401

    lang = request.form.get('language') or request.form.get('language_code') or 'sa'
    bot_db = _get_bot_db()
    if not bot_db.is_language_enabled(lang):
        return jsonify({
            "success": False,
            "error": f"Language '{lang}' is currently disabled by administrator."
        }), 400
    
    if 'audio' not in request.files and 'file' not in request.files:
        return jsonify({"success": False, "error": "No audio file provided in request."}), 400

    audio_file = request.files.get('audio') or request.files.get('file')
    audio_bytes = audio_file.read()
    filename = audio_file.filename or 'speech.wav'

    try:
        from apps.sanskrit_stt.backend.stt_service import call_remote_stt_api
    except ImportError:
        try:
            import stt_service
            call_remote_stt_api = stt_service.call_remote_stt_api
        except ImportError:
            import requests
            def call_remote_stt_api(b, language_code, filename):
                url = os.getenv("SAMSHO_STT_API_URL", "http://localhost:5001/api/v1/stt")
                key = os.getenv("SAMSHO_STT_API_KEY", "")
                hdrs = {"User-Agent": "Samshodhanam-Backend"}
                if key:
                    hdrs["Authorization"] = f"Bearer {key}"
                    hdrs["X-API-Key"] = key
                r = requests.post(url, headers=hdrs, data={"language": language_code}, files={"file": (filename, b, "audio/wav")}, timeout=120)
                if r.status_code in (200, 201):
                    rj = r.json()
                    t = rj.get("text") or rj.get("transcript") or ""
                    return {"success": True, "text": t, "transcript": t, "raw": rj}
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

    try:
        result = call_remote_stt_api(audio_bytes, language_code=lang, filename=filename)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Cloud STT API error: {str(e)}"
        }), 500


# =============================================================================
# TELEGRAM BOT WEB ADMIN CONTROLS API
# =============================================================================

def _get_bot_db():
    return _get_stt_bot_db()

def _get_bot_manager():
    return _get_stt_bot_manager()

def _check_stt_admin_auth():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    is_logged_in = session.get('admin_logged_in', False)
    return is_logged_in and (is_super or 'PERM_MANAGE_AI' in user_perms)

@apps_bp.route('/stt/bot/overview', methods=['GET'])
def stt_bot_overview():
    """Return overview of Telegram bot status, token state, access code counts, and user stats."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        bot_mgr = _get_bot_manager()
        token = os.getenv("TELEGRAM_BOT_TOKEN") or bot_db.get_setting("telegram_bot_token", "")
        secret = os.getenv("ADMIN_SETUP_SECRET") or bot_db.get_setting("admin_setup_secret", "admin123")
        
        bot_status = bot_mgr.get_full_bot_status()

        codes = bot_db.list_access_codes()
        users = bot_db.list_users()
        logs = bot_db.get_recent_logs(50)

        active_codes = len([c for c in codes if c['status'] == 'active'])
        total_audio_sec = sum(u.get('total_used_seconds', 0) for u in users)

        stt_api_url = os.getenv("SAMSHO_STT_API_URL") or bot_db.get_setting("samsho_stt_api_url", "http://localhost:5001/api/v1/stt")
        stt_api_key = os.getenv("SAMSHO_STT_API_KEY") or bot_db.get_setting("samsho_stt_api_key", "")

        return jsonify({
            "success": True,
            "has_token": bool(token),
            "masked_token": f"{token[:8]}...{token[-4:]}" if len(token) > 12 else ("Configured" if token else "Not Set"),
            "bot_status": bot_status,
            "setup_secret": secret,
            "stt_api_url": stt_api_url,
            "has_api_key": bool(stt_api_key),
            "total_codes": len(codes),
            "active_codes": active_codes,
            "total_users": len(users),
            "total_transcriptions": len(logs),
            "total_audio_sec": total_audio_sec,
            "total_audio_min": math.ceil(total_audio_sec / 60) if 'math' in globals() else int(total_audio_sec // 60)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/action', methods=['POST'])
def stt_bot_action():
    """Start, stop, or restart the Telegram bot process."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_mgr = _get_bot_manager()
        data = request.json or {}
        action = data.get('action', '').strip().lower()

        if action == 'start':
            success, msg = bot_mgr.start_bot()
        elif action == 'stop':
            success, msg = bot_mgr.stop_bot()
        elif action == 'restart':
            success, msg = bot_mgr.restart_bot()
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400

        status = bot_mgr.get_full_bot_status()
        return jsonify({"success": success, "message": msg, "bot_status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/raw_logs', methods=['GET'])
def stt_bot_logs():
    """Retrieve recent lines from telegram_bot.log."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_mgr = _get_bot_manager()
        lines = int(request.args.get('lines', 50))
        logs_text = bot_mgr.get_bot_logs(lines)
        return jsonify({"success": True, "logs": logs_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/config', methods=['POST'])
def stt_bot_config():
    """Save Telegram Bot Token, Admin Setup Secret, and Central Cloud STT API configuration."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        token = data.get('token', '').strip()
        secret = data.get('secret', '').strip()
        stt_api_url = data.get('stt_api_url', '').strip()
        stt_api_key = data.get('stt_api_key', '').strip()

        if token:
            bot_db.set_setting('telegram_bot_token', token)
            os.environ['TELEGRAM_BOT_TOKEN'] = token
        if secret:
            bot_db.set_setting('admin_setup_secret', secret)
            os.environ['ADMIN_SETUP_SECRET'] = secret
        if stt_api_url:
            bot_db.set_setting('samsho_stt_api_url', stt_api_url)
            os.environ['SAMSHO_STT_API_URL'] = stt_api_url
        if stt_api_key:
            bot_db.set_setting('samsho_stt_api_key', stt_api_key)
            os.environ['SAMSHO_STT_API_KEY'] = stt_api_key

        return jsonify({"success": True, "message": "STT & Bot configuration saved successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/stt/bot/codes', methods=['GET'])
def stt_bot_list_codes():
    """List all Telegram Access Codes."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        codes = bot_db.list_access_codes()
        return jsonify({"success": True, "codes": codes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/codes/create', methods=['POST'])
def stt_bot_create_code():
    """Generate a new Telegram Access Code with daily max limit in minutes."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        code = data.get('code', '').strip().upper()
        max_minutes = float(data.get('max_minutes', 100))

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        new_code = bot_db.create_access_code(code, daily_max_minutes=max_minutes)
        return jsonify({"success": True, "code": new_code, "message": f"Access code '{code}' created successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/codes/revoke', methods=['POST'])
def stt_bot_revoke_code():
    """Revoke or deactivate an access code."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        code = data.get('code', '').strip().upper()

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        bot_db.revoke_access_code(code)
        return jsonify({"success": True, "message": f"Access code '{code}' revoked."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/codes/limit', methods=['POST'])
def stt_bot_update_code_limit():
    """Update daily max limit for an access code."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        code = data.get('code', '').strip().upper()
        daily_max_minutes = float(data.get('max_minutes', data.get('daily_max_minutes', 100)))

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        updated_code = bot_db.update_access_code_limit(code, daily_max_minutes)
        return jsonify({"success": True, "code": updated_code, "message": f"Daily limit for '{code}' updated to {daily_max_minutes} mins."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/send_message', methods=['POST'])
def stt_bot_send_message():
    """Send text or file message to Telegram user(s) via bot."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        import requests
        bot_db = _get_bot_db()
        token = os.getenv("TELEGRAM_BOT_TOKEN") or bot_db.get_setting("telegram_bot_token", "")

        if not token:
            return jsonify({"success": False, "error": "Telegram Bot Token is not configured."}), 400

        target = request.form.get('telegram_id') or (request.json.get('telegram_id') if request.is_json else None)
        message = request.form.get('message') or (request.json.get('message') if request.is_json else '')
        message = (message or '').strip()

        file_obj = request.files.get('file') if request.files else None

        if not target:
            return jsonify({"success": False, "error": "Recipient Telegram ID or 'broadcast' is required."}), 400
        if not message and not file_obj:
            return jsonify({"success": False, "error": "Please provide a message or attach a file."}), 400

        target_ids = []
        if str(target).lower() == 'broadcast':
            users = bot_db.list_users()
            target_ids = [u['telegram_id'] for u in users if u.get('telegram_id')]
        else:
            try:
                target_ids = [int(target)]
            except ValueError:
                return jsonify({"success": False, "error": "Invalid Telegram ID."}), 400

        if not target_ids:
            return jsonify({"success": False, "error": "No registered Telegram users found."}), 404

        success_count = 0
        fail_count = 0
        errors = []

        file_bytes = file_obj.read() if file_obj else None
        filename = file_obj.filename if file_obj else None
        content_type = file_obj.content_type if file_obj else 'application/octet-stream'

        for tid in target_ids:
            try:
                if file_bytes:
                    files_payload = {'document': (filename, file_bytes, content_type)}
                    data_payload = {'chat_id': tid, 'caption': message}
                    res = requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data=data_payload, files=files_payload, timeout=15)
                else:
                    data_payload = {'chat_id': tid, 'text': message, 'parse_mode': 'HTML'}
                    res = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data=data_payload, timeout=15)

                res_json = res.json()
                if res_json.get('ok'):
                    success_count += 1
                else:
                    fail_count += 1
                    errors.append(f"ID {tid}: {res_json.get('description', 'Telegram API error')}")
            except Exception as ex:
                fail_count += 1
                errors.append(f"ID {tid}: {str(ex)}")

        return jsonify({
            "success": success_count > 0,
            "sent_count": success_count,
            "fail_count": fail_count,
            "errors": errors,
            "message": f"Message sent to {success_count} user(s)." + (f" ({fail_count} failed)" if fail_count > 0 else "")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/stt/bot/users', methods=['GET'])
def stt_bot_list_users():
    """List all registered Telegram Bot users and usage stats."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        users = bot_db.list_users()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/logs', methods=['GET'])
def stt_bot_list_logs():
    """Fetch recent transcription audit logs, or raw console logs if 'lines' param is provided."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        # If client passes lines query param, dispatch to raw console logs
        if 'lines' in request.args:
            bot_mgr = _get_bot_manager()
            lines = int(request.args.get('lines', 50))
            logs_text = bot_mgr.get_bot_logs(lines)
            return jsonify({"success": True, "logs": logs_text})

        bot_db = _get_bot_db()
        limit = int(request.args.get('limit', 50))
        logs = bot_db.get_recent_logs(limit)
        return jsonify({"success": True, "logs": logs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/audio/<path:filename>', methods=['GET'])
def stt_get_audio(filename):
    """Audio retention and playback disabled for user privacy."""
    return jsonify({"success": False, "error": "Audio log retrieval has been permanently disabled for user privacy."}), 410

@apps_bp.route('/stt/languages', methods=['GET'])
def stt_languages():
    """Public endpoint returning default language, enabled languages list, and dictionary of all languages."""
    try:
        bot_db = _get_bot_db()
        enabled = bot_db.get_enabled_languages()
        def_lang = bot_db.get_default_language()
        all_langs = bot_db.ALL_LANGUAGES
        
        return jsonify({
            "success": True,
            "default": def_lang,
            "enabled": enabled,
            "all_languages": all_langs
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/languages', methods=['POST'])
def stt_bot_languages_config():
    """Admin endpoint to update default language and enabled languages list."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        enabled_list = data.get('enabled', [])
        default_code = data.get('default', 'sa')

        if not isinstance(enabled_list, list) or len(enabled_list) == 0:
            return jsonify({"success": False, "error": "At least one language must be enabled."}), 400

        bot_db.set_enabled_languages(enabled_list)
        bot_db.set_default_language(default_code)

        return jsonify({
            "success": True,
            "default": bot_db.get_default_language(),
            "enabled": bot_db.get_enabled_languages(),
            "message": "Language controls updated successfully!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/scripts', methods=['GET'])
@apps_bp.route('/api/stt/scripts', methods=['GET'])
def stt_scripts():
    """Public endpoint returning default script, enabled scripts list, and dictionary of all scripts."""
    try:
        bot_db = _get_bot_db()
        enabled = bot_db.get_enabled_scripts()
        def_script = bot_db.get_default_script()
        all_scripts = bot_db.ALL_SCRIPTS
        
        return jsonify({
            "success": True,
            "default": def_script,
            "enabled": enabled,
            "all_scripts": all_scripts
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/bot/scripts', methods=['POST'])
@apps_bp.route('/api/stt/bot/scripts', methods=['POST'])
def stt_bot_scripts_config():
    """Admin endpoint to update default script and enabled scripts list."""
    if not _check_stt_admin_auth():
        return jsonify({"success": False, "error": "Unauthorized access. Admin login required."}), 403
    try:
        bot_db = _get_bot_db()
        data = request.json or {}
        enabled_list = data.get('enabled', [])
        default_code = data.get('default', 'devanagari')

        if not isinstance(enabled_list, list) or len(enabled_list) == 0:
            return jsonify({"success": False, "error": "At least one script must be enabled."}), 400

        bot_db.set_enabled_scripts(enabled_list)
        bot_db.set_default_script(default_code)

        return jsonify({
            "success": True,
            "default": bot_db.get_default_script(),
            "enabled": bot_db.get_enabled_scripts(),
            "message": "Script controls updated successfully!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/stt/transliterate', methods=['POST'])
def stt_transliterate_api():
    """Transliterate text between Devanagari, IAST, Tamil, Telugu, Kannada, Malayalam, ISO 15919, SLP1."""
    try:
        data = request.json or {}
        text = data.get('text', '').strip()
        from_scheme_name = (data.get('from', 'devanagari') or 'devanagari').lower()
        to_scheme_name = (data.get('to', 'iast') or 'iast').lower()

        if not text:
            return jsonify({"success": True, "transliterated": ""})

        scheme_map = {
            "devanagari": Scheme.Devanagari,
            "sa": Scheme.Devanagari,
            "iast": Scheme.Iast,
            "tamil": Scheme.Tamil,
            "ta": Scheme.Tamil,
            "telugu": Scheme.Telugu,
            "te": Scheme.Telugu,
            "kannada": Scheme.Kannada,
            "kn": Scheme.Kannada,
            "malayalam": Scheme.Malayalam,
            "ml": Scheme.Malayalam,
            "slp1": Scheme.Slp1,
            "iso": Scheme.Iso15919,
            "iso15919": Scheme.Iso15919,
            "grantha": Scheme.Grantha,
            "hk": Scheme.HarvardKyoto,
        }

        from_scheme = scheme_map.get(from_scheme_name, Scheme.Devanagari)
        to_scheme = scheme_map.get(to_scheme_name, Scheme.Iast)

        if from_scheme == to_scheme:
            return jsonify({"success": True, "transliterated": text})

        transliterated_result = transliterate(text, from_scheme, to_scheme)
        return jsonify({
            "success": True,
            "original": text,
            "from": from_scheme_name,
            "to": to_scheme_name,
            "transliterated": transliterated_result
        })
    except Exception as e:
        logging.error(f"Transliteration error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ─── STT AI Clean (Gemini Phonetic Proofreader) ──────────────────────────────

def _get_stt_bot_db_safe():
    try:
        return _get_stt_bot_db()
    except Exception as _e:
        logging.warning(f"Could not load bot_db in backend.py: {_e}")
        return None

DEFAULT_STT_CLEAN_PROMPT = """You are a highly specialized Speech-to-Text (STT) Proofreading Assistant for Sanskrit and Indic languages.
The input text was generated by a Speech-to-Text (STT) voice recognition model and contains acoustic mishearings, phonetic typos, missing or incorrect visargas (ः), anusvāras (ं), sandhi boundaries, or grammatical slips.

STRICT INSTRUCTIONS:
1. Proofread and replace words ONLY with phonetically and grammatically correct versions.
2. Correct grammatical case endings (vibhakti), lakāras, missing visargas (ः), anusvāras (ं), and avagrahas (ऽ) so the text is syntactically sound.
3. Apply standard Sanskrit Sandhi rules for smooth reading, keeping words readable and clear.
4. Do NOT change words into non-phonetically similar synonyms or alter named entities unless they are misspellings/mishearings.
5. Preserve standard Sanskrit punctuation (dandas । and ॥) and format verses/ślokas with clean line breaks.
6. Cleanly remove stutters, hesitations, and filler sounds (e.g. 'umm', 'aah'). Preserve legitimate non-Sanskrit words if part of lecture text.
7. Output ONLY the cleaned, corrected text in Devanāgarī script without markdown code blocks, explanations, or commentary."""

@apps_bp.route('/stt/ai_clean', methods=['POST'])
@apps_bp.route('/api/stt/ai_clean', methods=['POST'])
def stt_ai_clean():
    """Clean raw STT transcript using Gemini with strict phonetic proofreading instructions."""
    bot_db = _get_stt_bot_db_safe()
    if not is_request_authenticated():
        return jsonify({
            "success": False, 
            "error": "Login required to use AI features. Please log in or enter a valid access code.", 
            "login_required": True
        }), 401
    try:
        data = request.json or {}
        text = data.get('text', '').strip()
        lang_code = data.get('language_code', 'sa-IN')
        log_id = data.get('log_id')
        access_code = (data.get('access_code') or '').strip().upper()

        if bot_db is not None and access_code:
            code_obj = bot_db.get_access_code(access_code)
            if code_obj and code_obj.get('allow_ai_clean') == 0:
                return jsonify({
                    "success": False,
                    "permission_denied": True,
                    "error": "Access Restricted: AI Clean feature is disabled for your access code. Please contact system administrator to request access."
                }), 403

        if not text:
            return jsonify({"success": False, "error": "No text provided"}), 400

        sys_prompt = DEFAULT_STT_CLEAN_PROMPT
        model_name = "models/gemini-3.5-flash"
        if bot_db is not None:
            sys_prompt = bot_db.get_setting('stt_ai_clean_prompt', DEFAULT_STT_CLEAN_PROMPT)
            m = bot_db.get_setting('stt_ai_clean_model', 'models/gemini-3.5-flash')
            if m:
                model_name = m if m.startswith("models/") else f"models/{m}"

        prompt = f"Language: {lang_code}\nSpeech-to-Text Raw Output:\n{text}\n\nProvide the phonetically proofread text:"

        def run_gen(key):
            import google.generativeai as genai
            genai.configure(api_key=key)
            gen_config = genai.types.GenerationConfig(temperature=0.1)
            model = genai.GenerativeModel(model_name, generation_config=gen_config, system_instruction=sys_prompt)
            return model.generate_content(prompt)

        try:
            cleaned_text = run_gen(get_effective_gemini_key()).text.strip()
            import re
            if cleaned_text.startswith("```") and cleaned_text.endswith("```"):
                cleaned_text = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned_text)
                cleaned_text = re.sub(r"\n?```$", "", cleaned_text).strip()
        except Exception as gem_err:
            logging.error(f"Gemini STT clean error: {gem_err}")
            return jsonify({"success": False, "error": f"AI Clean failed: {str(gem_err)}"}), 500

        if log_id and bot_db is not None:
            try:
                bot_db.update_cleaned_transcript(int(log_id), cleaned_text)
            except Exception as db_err:
                logging.error(f"Failed to update cleaned transcript in DB: {db_err}")

        return jsonify({
            "success": True,
            "original_text": text,
            "cleaned_text": cleaned_text,
            "model_used": model_name
        })
    except Exception as e:
        logging.error(f"stt_ai_clean endpoint error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/stt/ai_assist', methods=['POST'])
@apps_bp.route('/api/stt/ai_assist', methods=['POST'])
def stt_ai_assist():
    """Multimodal Audio + Text proofreading endpoint using Gemini."""
    bot_db = _get_stt_bot_db_safe()
    if not is_request_authenticated():
        return jsonify({
            "success": False, 
            "error": "Login required to use AI features. Please log in or enter a valid access code.", 
            "login_required": True
        }), 401
    try:
        audio_file = request.files.get('audio')
        text = request.form.get('text', '').strip()
        lang_code = request.form.get('language_code', 'sa-IN')
        access_code = (request.form.get('access_code') or '').strip().upper()

        if bot_db is not None and access_code:
            code_obj = bot_db.get_access_code(access_code)
            if code_obj and code_obj.get('allow_ai_assist') == 0:
                return jsonify({
                    "success": False,
                    "permission_denied": True,
                    "error": "Access Restricted: AI Assist feature is disabled for your access code. Please contact system administrator to request access."
                }), 403

        if not text and not audio_file:
            return jsonify({"success": False, "error": "No text or audio provided"}), 400

        temp_audio_path = None
        if audio_file:
            import tempfile
            ext = os.path.splitext(audio_file.filename or 'audio.wav')[1] or '.wav'
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            audio_file.save(tf.name)
            tf.close()
            temp_audio_path = tf.name

        m_setting = "gemini-3.6-flash"
        if bot_db is not None:
            sys_prompt = bot_db.get_setting('stt_ai_assist_prompt', bot_db.DEFAULT_AI_ASSIST_PROMPT)
            m_setting = bot_db.get_setting('stt_ai_assist_model', 'gemini-3.6-flash') or "gemini-3.6-flash"

        raw_m = m_setting.replace("models/", "") if m_setting else "gemini-3.6-flash"
        model_candidates = []
        for cand in [raw_m, f"models/{raw_m}", "gemini-3.6-flash", "models/gemini-3.6-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-flash-latest"]:
            if cand not in model_candidates:
                model_candidates.append(cand)

        def run_gen(key):
            import google.generativeai as genai
            genai.configure(api_key=key)
            gen_config = genai.types.GenerationConfig(temperature=0.1)

            parts = []
            uploaded = None
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    uploaded = genai.upload_file(temp_audio_path)
                    parts.append(uploaded)
                except Exception as up_err:
                    logging.warning(f"Audio upload error: {up_err}")

            p_text = f"Language: {lang_code}\nSpeech-to-Text Raw Output Reference:\n{text}\n\nListen to audio and provide exact phonetically proofread text:"
            parts.append(p_text)

            last_err = None
            for m_name in model_candidates:
                try:
                    model = genai.GenerativeModel(m_name, generation_config=gen_config, system_instruction=sys_prompt)
                    res = model.generate_content(parts)
                    if uploaded:
                        try:
                            genai.delete_file(uploaded.name)
                        except Exception:
                            pass
                    return res
                except Exception as gen_err:
                    last_err = gen_err
                    err_str = str(gen_err)
                    if "404" in err_str or "not found" in err_str.lower():
                        logging.warning(f"Gemini model '{m_name}' unavailable/404, trying fallback model...")
                        continue
                    if uploaded:
                        try:
                            genai.delete_file(uploaded.name)
                        except Exception:
                            pass
                    raise gen_err

            if uploaded:
                try:
                    genai.delete_file(uploaded.name)
                except Exception:
                    pass
            if last_err:
                raise last_err

        try:
            assist_text = run_gen(get_effective_gemini_key()).text.strip()
            import re
            if assist_text.startswith("```") and assist_text.endswith("```"):
                assist_text = re.sub(r"^```[a-zA-Z]*\n?", "", assist_text)
                assist_text = re.sub(r"\n?```$", "", assist_text).strip()
        finally:
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.remove(temp_audio_path)
                except Exception:
                    pass

        log_id = request.form.get('log_id') or (request.json or {}).get('log_id')
        if log_id and bot_db is not None:
            try:
                bot_db.update_assisted_transcript(int(log_id), assist_text)
            except Exception as db_err:
                logging.error(f"Failed to update assisted transcript in DB: {db_err}")

        return jsonify({
            "success": True,
            "original_text": text,
            "assisted_text": assist_text,
            "model_used": model_name
        })
    except Exception as e:
        logging.error(f"stt_ai_assist endpoint error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@apps_bp.route('/stt/admin/ai_clean_config', methods=['GET', 'POST'])
@apps_bp.route('/api/stt/admin/ai_clean_config', methods=['GET', 'POST'])
def stt_admin_ai_clean_config():
    """Get or update STT AI Clean prompt and model configuration."""
    bot_db = _get_stt_bot_db_safe()
    if bot_db is None:
        return jsonify({"success": False, "error": "bot_db unavailable"}), 500

    if request.method == 'GET':
        prompt = bot_db.get_setting('stt_ai_clean_prompt', DEFAULT_STT_CLEAN_PROMPT)
        model = bot_db.get_setting('stt_ai_clean_model', 'models/gemini-3.5-flash')
        return jsonify({
            "success": True,
            "prompt": prompt,
            "model": model,
            "default_prompt": DEFAULT_STT_CLEAN_PROMPT
        })
    
    # POST
    data = request.json or {}
    new_prompt = data.get('prompt')
    new_model = data.get('model')

    if new_prompt is not None:
        bot_db.set_setting('stt_ai_clean_prompt', new_prompt.strip())
    if new_model is not None:
        bot_db.set_setting('stt_ai_clean_model', new_model.strip())

    return jsonify({"success": True, "message": "AI Clean configuration updated successfully."})


# =============================================================================
# TELEGRAM OCR BOT WEB ADMIN API
# =============================================================================

def _get_ocr_bot_manager():
    p = os.path.join(os.path.dirname(__file__), 'ocr_bot', 'bot_manager.py')
    return _load_isolated_module('apps_ocr_bot_bot_manager', p)

@apps_bp.route('/ocr_bot/status', methods=['GET'])
@apps_bp.route('/api/ocr_bot/status', methods=['GET'])
def ocr_bot_api_status():
    """Get real-time status of Telegram OCR Bot."""
    try:
        bm = _get_ocr_bot_manager()
        return jsonify({"success": True, "data": bm.get_bot_status()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/ocr_bot/action', methods=['POST'])
@apps_bp.route('/api/ocr_bot/action', methods=['POST'])
def ocr_bot_api_action():
    """Perform process actions: start, stop, restart."""
    try:
        bm = _get_ocr_bot_manager()
        data = request.json or {}
        action = data.get('action', '').lower().strip()
        if action == 'start':
            success, msg = bm.start_bot()
        elif action == 'stop':
            success, msg = bm.stop_bot()
        elif action == 'restart':
            success, msg = bm.restart_bot()
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400
        return jsonify({"success": success, "message": msg, "data": bm.get_bot_status()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/ocr_bot/logs', methods=['GET'])
@apps_bp.route('/api/ocr_bot/logs', methods=['GET'])
def ocr_bot_api_logs():
    """Retrieve recent lines from telegram_ocr_bot.log."""
    try:
        bm = _get_ocr_bot_manager()
        lines = int(request.args.get('lines', 50))
        return jsonify({"success": True, "logs": bm.get_logs(lines)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/ocr_bot/config', methods=['POST'])
@apps_bp.route('/api/ocr_bot/config', methods=['POST'])
def ocr_bot_api_config():
    """Update Telegram OCR Bot Token."""
    try:
        data = request.json or {}
        token = data.get('token', '').strip()
        env_file = os.path.join(os.path.dirname(__file__), 'ocr_bot', '.env')

        env_lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()

        new_lines = []
        updated_token = False
        for line in env_lines:
            if line.startswith('TELEGRAM_OCR_BOT_TOKEN='):
                new_lines.append(f'TELEGRAM_OCR_BOT_TOKEN="{token}"\n')
                updated_token = True
            elif line.startswith('TELEGRAM_BOT_TOKEN='):
                new_lines.append(f'TELEGRAM_BOT_TOKEN="{token}"\n')
            else:
                new_lines.append(line)

        if not updated_token and token:
            new_lines.append(f'TELEGRAM_OCR_BOT_TOKEN="{token}"\n')
            new_lines.append(f'TELEGRAM_BOT_TOKEN="{token}"\n')

        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        os.environ['TELEGRAM_OCR_BOT_TOKEN'] = token
        os.environ['TELEGRAM_BOT_TOKEN'] = token

        try:
            bm = _get_ocr_bot_manager()
            if hasattr(bm, 'config') and hasattr(bm.config, 'get_telegram_token'):
                bm.config.get_telegram_token()
        except Exception:
            pass

        return jsonify({"success": True, "message": "OCR Bot configuration updated successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@apps_bp.route('/ocr_bot/set_api_config', methods=['POST'])
@apps_bp.route('/api/ocr_bot/set_api_config', methods=['POST'])
def ocr_bot_set_api_config():
    """Configure Samshodhanam Cloud OCR API endpoint and key."""
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        api_url = (data.get('api_url') or '').strip()
        api_key = (data.get('api_key') or '').strip()

        env_path = os.path.join(workspace_dir, '.env')
        lines = []
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        new_lines = []
        keys_set = set()
        for line in lines:
            if line.startswith('SAMSHO_OCR_API_URL='):
                new_lines.append(f"SAMSHO_OCR_API_URL={api_url}\n")
                keys_set.add('SAMSHO_OCR_API_URL')
            elif line.startswith('SAMSHO_OCR_API_KEY='):
                new_lines.append(f"SAMSHO_OCR_API_KEY={api_key}\n")
                keys_set.add('SAMSHO_OCR_API_KEY')
            else:
                new_lines.append(line)

        if 'SAMSHO_OCR_API_URL' not in keys_set and api_url:
            new_lines.append(f"SAMSHO_OCR_API_URL={api_url}\n")
        if 'SAMSHO_OCR_API_KEY' not in keys_set and api_key:
            new_lines.append(f"SAMSHO_OCR_API_KEY={api_key}\n")

        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        if api_url: os.environ['SAMSHO_OCR_API_URL'] = api_url
        if api_key: os.environ['SAMSHO_OCR_API_KEY'] = api_key

        return jsonify({"success": True, "message": "OCR API settings updated successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# 14. RIGVEDA COMPREHENSIVE ARCHIVE APIS
# ==========================================

_RIGVEDA_DIR = os.path.join(workspace_dir, 'apps', 'rigveda')
_RIGVEDA_DB = os.path.join(_RIGVEDA_DIR, 'rigveda.db')
_RIGVEDA_AUDIO_DIR = os.path.join(_RIGVEDA_DIR, 'audio')

_rigveda_extract_lock = threading.Lock()

def _ensure_rigveda_schema(conn):
    """Ensure pratika, pratika_svara, and first_char columns and indexes exist in the Rigveda database."""
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(riks)")
        cols = {row[1] for row in cur.fetchall()}
        missing = [c for c in ('pratika', 'pratika_svara', 'first_char') if c not in cols]
        if missing:
            logging.warning(f"Rigveda DB missing columns {missing}. Running automatic in-place schema migration...")
            for col in missing:
                cur.execute(f"ALTER TABLE riks ADD COLUMN {col} TEXT")
            
            import re
            cur.execute("SELECT id, samhita FROM riks")
            rows = cur.fetchall()
            updates = []
            for r in rows:
                samhita = r['samhita'] or ''
                plain = re.sub(r'[\u0951\u0952\u1CD0-\u1CFF\uA8E0-\uA8FF\u0300-\u036F]', '', samhita)
                first_letter = ''
                for ch in plain:
                    if '\u0900' <= ch <= '\u097F' and ch not in ('\u0901', '\u0902', '\u0903', '\u093C', '\u093D', '\u094D', '।', '॥'):
                        first_letter = ch
                        break
                p_svara = samhita.split('।')[0].split('॥')[0].strip()[:60]
                p_plain = plain.split('।')[0].split('॥')[0].strip()[:60]
                updates.append((p_plain, p_svara, first_letter, r['id']))
            cur.executemany("UPDATE riks SET pratika = ?, pratika_svara = ?, first_char = ? WHERE id = ?", updates)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_riks_pratika ON riks(first_char, pratika)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_riks_ashtaka_full ON riks(ashtaka, adhyaya, varga, varga_rik)")
            conn.commit()
            logging.info("Rigveda DB automatic schema migration completed successfully.")
    except Exception as e:
        logging.error(f"Error checking/migrating Rigveda schema: {e}")

def _get_rigveda_conn():
    gz_path = _RIGVEDA_DB + '.gz'
    alt_db = os.path.join(workspace_dir, 'db', 'rigveda.db')
    alt_gz = alt_db + '.gz'
    target_gz = gz_path if os.path.exists(gz_path) else (alt_gz if os.path.exists(alt_gz) else None)

    needs_extract = False
    if not os.path.exists(_RIGVEDA_DB) or os.path.getsize(_RIGVEDA_DB) == 0:
        needs_extract = True
    elif target_gz and os.path.exists(target_gz):
        try:
            # If the .gz archive is newer than the extracted database, re-extract
            if os.path.getmtime(target_gz) > os.path.getmtime(_RIGVEDA_DB):
                needs_extract = True
            else:
                # Check if the existing database has the required schema
                test_conn = sqlite3.connect(_RIGVEDA_DB)
                t_cur = test_conn.cursor()
                t_cur.execute("PRAGMA table_info(riks)")
                cols = {r[1] for r in t_cur.fetchall()}
                test_conn.close()
                if 'first_char' not in cols or 'pratika' not in cols or 'pratika_svara' not in cols:
                    logging.warning(f"Rigveda DB {_RIGVEDA_DB} is missing pratika/first_char columns. Triggering auto-extract from {target_gz}...")
                    needs_extract = True
        except Exception:
            needs_extract = True

    if needs_extract and target_gz:
        with _rigveda_extract_lock:
            # Check condition again inside lock to prevent concurrent extractions
            re_check = False
            if not os.path.exists(_RIGVEDA_DB) or os.path.getsize(_RIGVEDA_DB) == 0:
                re_check = True
            elif os.path.getmtime(target_gz) > os.path.getmtime(_RIGVEDA_DB):
                re_check = True
            else:
                try:
                    test_conn = sqlite3.connect(_RIGVEDA_DB)
                    t_cur = test_conn.cursor()
                    t_cur.execute("PRAGMA table_info(riks)")
                    cols = {r[1] for r in t_cur.fetchall()}
                    test_conn.close()
                    if 'first_char' not in cols or 'pratika' not in cols or 'pratika_svara' not in cols:
                        re_check = True
                except Exception:
                    re_check = True

            if re_check:
                try:
                    import gzip
                    import shutil
                    logging.info(f"Extracting Rigveda database from {target_gz}...")
                    os.makedirs(os.path.dirname(_RIGVEDA_DB), exist_ok=True)
                    tmp_db = _RIGVEDA_DB + '.tmp'
                    with gzip.open(target_gz, 'rb') as f_in:
                        with open(tmp_db, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.replace(tmp_db, _RIGVEDA_DB)
                    logging.info(f"Rigveda database successfully extracted to {_RIGVEDA_DB}")
                except Exception as e:
                    logging.error(f"Failed to auto-extract Rigveda database: {e}")

    try:
        if os.path.exists(_RIGVEDA_DB) and os.path.getsize(_RIGVEDA_DB) > 0:
            conn = sqlite3.connect(_RIGVEDA_DB)
            conn.row_factory = sqlite3.Row
            _ensure_rigveda_schema(conn)
            return conn
        elif os.path.exists(alt_db) and os.path.getsize(alt_db) > 0:
            conn = sqlite3.connect(alt_db)
            conn.row_factory = sqlite3.Row
            _ensure_rigveda_schema(conn)
            return conn
        return None
    except Exception as e:
        logging.error(f"Failed to open Rigveda database: {e}")
        return None

@apps_bp.route('/rigveda/stats', methods=['GET'])
def rigveda_get_stats():
    """Return counts of mandalas, suktas, riks, and audio files."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Rigveda database not initialized yet."}), 404
    try:
        cur = conn.cursor()
        riks_count = cur.execute("SELECT COUNT(*) FROM riks").fetchone()[0]
        suktas_count = cur.execute("SELECT COUNT(DISTINCT mandala || '.' || sukta) FROM riks").fetchone()[0]
        mandalas_count = cur.execute("SELECT COUNT(DISTINCT mandala) FROM riks").fetchone()[0]
        
        audio_count = 0
        if os.path.exists(_RIGVEDA_AUDIO_DIR):
            for root, _, files in os.walk(_RIGVEDA_AUDIO_DIR):
                audio_count += sum(1 for f in files if f.endswith('.mp3'))

        return jsonify({
            "success": True,
            "mandalas": mandalas_count,
            "suktas": suktas_count,
            "riks": riks_count,
            "audio_files": audio_count
        })
    finally:
        conn.close()

@apps_bp.route('/rigveda/tree', methods=['GET'])
def rigveda_get_tree():
    """Return Mandala hierarchy with Sukta counts."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT mandala, sukta, COUNT(rik) as total_riks
            FROM riks
            GROUP BY mandala, sukta
            ORDER BY mandala, sukta
        """)
        rows = cur.fetchall()
        tree = {}
        for r in rows:
            m = str(r['mandala'])
            if m not in tree:
                tree[m] = []
            tree[m].append({
                "sukta": r['sukta'],
                "total_riks": r['total_riks']
            })
        return jsonify({"success": True, "tree": tree})
    finally:
        conn.close()

@apps_bp.route('/rigveda/sukta/<int:mandala>/<int:sukta>', methods=['GET'])
def rigveda_get_sukta(mandala, sukta):
    """Return all Riks for a given Mandala and Sukta with full details."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                   rishi, devata, chandas, samhita, padapatha, sayana_bhashya,
                   audio_url, audio_file
            FROM riks
            WHERE mandala = ? AND sukta = ?
            ORDER BY rik ASC
        """, (mandala, sukta))
        rows = cur.fetchall()
        riks = []
        for r in rows:
            local_audio_exists = bool(r['audio_file'] and os.path.exists(os.path.join(_RIGVEDA_AUDIO_DIR, r['audio_file'])))
            riks.append({
                "id": r['id'],
                "mandala": r['mandala'],
                "sukta": r['sukta'],
                "rik": r['rik'],
                "ashtaka": r['ashtaka'],
                "adhyaya": r['adhyaya'],
                "varga": r['varga'],
                "anuvaka": r['anuvaka'],
                "rishi": r['rishi'],
                "devata": r['devata'],
                "chandas": r['chandas'],
                "samhita": r['samhita'],
                "padapatha": r['padapatha'],
                "sayana_bhashya": r['sayana_bhashya'],
                "audio_url": f"/apps/api/rigveda/audio/{r['mandala']}/{r['sukta']}/{r['rik']}",
                "local_audio": local_audio_exists
            })
        return jsonify({"success": True, "mandala": mandala, "sukta": sukta, "total": len(riks), "riks": riks})
    finally:
        conn.close()

@apps_bp.route('/rigveda/rik/<int:mandala>/<int:sukta>/<int:rik>', methods=['GET'])
def rigveda_get_rik(mandala, sukta, rik):
    """Return a single Rik with all details."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                   rishi, devata, chandas, samhita, padapatha, sayana_bhashya,
                   audio_url, audio_file
            FROM riks
            WHERE mandala = ? AND sukta = ? AND rik = ?
        """, (mandala, sukta, rik))
        r = cur.fetchone()
        if not r:
            return jsonify({"success": False, "error": "Rik not found"}), 404

        local_audio_exists = bool(r['audio_file'] and os.path.exists(os.path.join(_RIGVEDA_AUDIO_DIR, r['audio_file'])))
        data = {
            "id": r['id'],
            "mandala": r['mandala'],
            "sukta": r['sukta'],
            "rik": r['rik'],
            "ashtaka": r['ashtaka'],
            "adhyaya": r['adhyaya'],
            "varga": r['varga'],
            "anuvaka": r['anuvaka'],
            "rishi": r['rishi'],
            "devata": r['devata'],
            "chandas": r['chandas'],
            "samhita": r['samhita'],
            "padapatha": r['padapatha'],
            "sayana_bhashya": r['sayana_bhashya'],
            "audio_url": f"/apps/api/rigveda/audio/{r['mandala']}/{r['sukta']}/{r['rik']}",
            "local_audio": local_audio_exists
        }
        return jsonify({"success": True, "rik": data})
    finally:
        conn.close()

@apps_bp.route('/rigveda/audio/<int:mandala>/<int:sukta>/<int:rik>', methods=['GET'])
def rigveda_stream_audio(mandala, sukta, rik):
    """Stream audio with byte-range HTTP 206 support, falling back to remote CDN."""
    from flask import send_file, redirect
    local_path = os.path.join(_RIGVEDA_AUDIO_DIR, f"{mandala:03d}", f"{sukta:03d}", f"{rik:03d}.mp3")
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        return send_file(local_path, mimetype='audio/mpeg', conditional=True)
    # Fallback to remote CDN
    remote_url = f"https://rigveda.sanatana.in/rigveda-audio/{mandala:03d}/{sukta:03d}/{rik:03d}.mp3"
    return redirect(remote_url, code=302)

@apps_bp.route('/rigveda/search', methods=['GET'])
def rigveda_search():
    """Full-text search across Samhita, Padapatha, Sayana Bhashya using FTS5."""
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({"success": True, "results": [], "total": 0})
    
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))

    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        clean_q = q.replace('"', '""')
        match_expr = f'"{clean_q}"'
        try:
            cur.execute("""
                SELECT id, mandala, sukta, rik,
                       highlight(riks_fts, 4, '<mark>', '</mark>') as samhita_hl,
                       highlight(riks_fts, 5, '<mark>', '</mark>') as padapatha_hl,
                       snippet(riks_fts, 6, '<mark>', '</mark>', '...', 25) as bhashya_snip,
                       rishi, devata, chandas
                FROM riks_fts
                WHERE riks_fts MATCH ?
                LIMIT ? OFFSET ?
            """, (match_expr, limit, offset))
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            cur.execute("""
                SELECT id, mandala, sukta, rik,
                       highlight(riks_fts, 4, '<mark>', '</mark>') as samhita_hl,
                       highlight(riks_fts, 5, '<mark>', '</mark>') as padapatha_hl,
                       snippet(riks_fts, 6, '<mark>', '</mark>', '...', 25) as bhashya_snip,
                       rishi, devata, chandas
                FROM riks_fts
                WHERE riks_fts MATCH ?
                LIMIT ? OFFSET ?
            """, (clean_q, limit, offset))
            rows = cur.fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r['id'],
                "mandala": r['mandala'],
                "sukta": r['sukta'],
                "rik": r['rik'],
                "samhita_hl": r['samhita_hl'],
                "padapatha_hl": r['padapatha_hl'],
                "bhashya_snip": r['bhashya_snip'],
                "rishi": r['rishi'],
                "devata": r['devata'],
                "chandas": r['chandas']
            })
        return jsonify({"success": True, "query": q, "total": len(results), "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@apps_bp.route('/rigveda/indices/<attr>', methods=['GET'])
def rigveda_get_index(attr):
    """Return distinct Rishi, Devata, or Chandas with verse counts."""
    valid_attrs = {'rishi': 'rishi', 'devata': 'devata', 'chandas': 'chandas'}
    if attr not in valid_attrs:
        return jsonify({"success": False, "error": f"Invalid attribute: {attr}. Use rishi, devata, or chandas."}), 400

    col = valid_attrs[attr]
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT {col} as name, COUNT(*) as count
            FROM riks
            WHERE {col} IS NOT NULL AND {col} != ''
            GROUP BY {col}
            ORDER BY count DESC, {col} ASC
        """)
        rows = cur.fetchall()
        items = [{"name": r['name'], "count": r['count']} for r in rows]
        return jsonify({"success": True, "attribute": attr, "total": len(items), "items": items})
    finally:
        conn.close()

@apps_bp.route('/rigveda/by_attr/<attr>', methods=['GET'])
def rigveda_get_by_attr(attr):
    """Return all verses associated with a specific Rishi, Devata, or Chandas."""
    valid_attrs = {'rishi': 'rishi', 'devata': 'devata', 'chandas': 'chandas'}
    if attr not in valid_attrs:
        return jsonify({"success": False, "error": f"Invalid attribute: {attr}. Use rishi, devata, or chandas."}), 400

    val = request.args.get('val', '').strip()
    if not val:
        return jsonify({"success": False, "error": "Missing 'val' query parameter."}), 400

    col = valid_attrs[attr]
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT id, mandala, sukta, rik, rishi, devata, chandas,
                   substr(samhita, 1, 90) as samhita_snip
            FROM riks
            WHERE {col} = ?
            ORDER BY mandala ASC, sukta ASC, rik ASC
        """, (val,))
        rows = cur.fetchall()
        verses = [{
            "id": r['id'],
            "mandala": r['mandala'],
            "sukta": r['sukta'],
            "rik": r['rik'],
            "rishi": r['rishi'],
            "devata": r['devata'],
            "chandas": r['chandas'],
            "samhita_snip": (r['samhita_snip'] or '') + ('...' if len(r['samhita_snip'] or '') >= 90 else '')
        } for r in rows]
        return jsonify({
            "success": True,
            "attribute": attr,
            "value": val,
            "total": len(verses),
            "verses": verses
        })
    finally:
        conn.close()

@apps_bp.route('/rigveda/ancillary/<text_name>', methods=['GET'])
def rigveda_get_ancillary(text_name):
    """Return content for Niruktam, Aitareya Brahmana, or Brihaddevata."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, text_name, section, title, content
            FROM ancillary_texts
            WHERE text_name = ?
        """, (text_name,))
        rows = cur.fetchall()
        sections = [{"id": r['id'], "section": r['section'], "title": r['title'], "content": r['content']} for r in rows]
        return jsonify({"success": True, "text_name": text_name, "sections": sections})
    finally:
        conn.close()

@apps_bp.route('/rigveda/ashtaka_tree', methods=['GET'])
def rigveda_get_ashtaka_tree():
    """Return the hierarchical tree of Ashtakas (1-8), Adhyayas (1-8), and total Vargas."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT ashtaka, adhyaya, COUNT(DISTINCT varga) as total_vargas, COUNT(*) as total_riks
            FROM riks
            WHERE ashtaka IS NOT NULL
            GROUP BY ashtaka, adhyaya
            ORDER BY ashtaka, adhyaya
        """)
        rows = cur.fetchall()
        ashtakas = {}
        for r in rows:
            ash = r['ashtaka']
            if ash not in ashtakas:
                ashtakas[ash] = {
                    "ashtaka": ash,
                    "total_vargas": 0,
                    "total_riks": 0,
                    "adhyayas": []
                }
            ashtakas[ash]["adhyayas"].append({
                "adhyaya": r['adhyaya'],
                "total_vargas": r['total_vargas'],
                "total_riks": r['total_riks']
            })
            ashtakas[ash]["total_vargas"] += r['total_vargas']
            ashtakas[ash]["total_riks"] += r['total_riks']
        return jsonify({"success": True, "ashtakas": list(ashtakas.values())})
    except Exception as e:
        logging.error(f"Error in rigveda_get_ashtaka_tree: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@apps_bp.route('/rigveda/varga/<int:ashtaka>/<int:adhyaya>/<int:varga>', methods=['GET'])
def rigveda_get_varga(ashtaka, adhyaya, varga):
    """Return all riks in a specific Ashtaka-Adhyaya-Varga."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                   rishi, devata, chandas, samhita, padapatha, pratika_svara, pratika
            FROM riks
            WHERE ashtaka = ? AND adhyaya = ? AND varga = ?
            ORDER BY mandala ASC, sukta ASC, rik ASC
        """, (ashtaka, adhyaya, varga))
        rows = cur.fetchall()
        if not rows:
            return jsonify({"success": False, "error": f"Varga {ashtaka}.{adhyaya}.{varga} not found"}), 404
        riks = []
        for idx, r in enumerate(rows, 1):
            riks.append({
                "id": r['id'],
                "varga_rik": idx,
                "mandala": r['mandala'],
                "sukta": r['sukta'],
                "rik": r['rik'],
                "ashtaka": r['ashtaka'],
                "adhyaya": r['adhyaya'],
                "varga": r['varga'],
                "anuvaka": r['anuvaka'],
                "rishi": r['rishi'],
                "devata": r['devata'],
                "chandas": r['chandas'],
                "pratika_svara": r['pratika_svara'] or (r['samhita'][:60] if r['samhita'] else ''),
                "pratika": r['pratika'] or (r['samhita'][:60] if r['samhita'] else '')
            })
        return jsonify({
            "success": True,
            "ashtaka": ashtaka,
            "adhyaya": adhyaya,
            "varga": varga,
            "total_riks": len(riks),
            "riks": riks
        })
    except Exception as e:
        logging.error(f"Error in rigveda_get_varga: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@apps_bp.route('/rigveda/ashtaka_to_mandala', methods=['GET'])
def rigveda_ashtaka_to_mandala():
    """Convert (ashtaka, adhyaya, varga, varga_rik) into (mandala, sukta, rik)."""
    ashtaka = request.args.get('ashtaka', type=int)
    adhyaya = request.args.get('adhyaya', type=int)
    varga = request.args.get('varga', type=int)
    v_rik = request.args.get('rik', default=1, type=int)
    if not (ashtaka and adhyaya and varga):
        return jsonify({"success": False, "error": "Missing ashtaka, adhyaya, or varga parameters"}), 400

    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka
            FROM riks
            WHERE ashtaka = ? AND adhyaya = ? AND varga = ?
            ORDER BY mandala ASC, sukta ASC, rik ASC
        """, (ashtaka, adhyaya, varga))
        rows = cur.fetchall()
        if not rows:
            return jsonify({"success": False, "error": "Varga not found"}), 404

        target_idx = max(0, min(v_rik - 1, len(rows) - 1))
        target = rows[target_idx]
        return jsonify({
            "success": True,
            "id": target['id'],
            "mandala": target['mandala'],
            "sukta": target['sukta'],
            "rik": target['rik'],
            "ashtaka": target['ashtaka'],
            "adhyaya": target['adhyaya'],
            "varga": target['varga'],
            "varga_rik": target_idx + 1,
            "total_in_varga": len(rows)
        })
    except Exception as e:
        logging.error(f"Error in rigveda_ashtaka_to_mandala: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@apps_bp.route('/rigveda/pratika_letters', methods=['GET'])
def rigveda_get_pratika_letters():
    """Return all starting letters in Sanskrit Varnamala order with mantra counts."""
    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT first_char, COUNT(*) as count
            FROM riks
            WHERE first_char IS NOT NULL AND first_char != ''
            GROUP BY first_char
        """)
        counts = {r['first_char']: r['count'] for r in cur.fetchall()}
        vowels = ['अ', 'आ', 'इ', 'ई', 'उ', 'ऊ', 'ऋ', 'ॠ', 'ए', 'ऐ', 'ओ', 'औ']
        consonants = ['क', 'ख', 'ग', 'घ', 'ङ', 'च', 'छ', 'ज', 'झ', 'ञ', 'ट', 'ठ', 'ड', 'ढ', 'ण', 'त', 'थ', 'द', 'ध', 'न', 'प', 'फ', 'ब', 'भ', 'म', 'य', 'र', 'ल', 'व', 'श', 'ष', 'स', 'ह']
        ordered_letters = []
        for ch in (vowels + consonants):
            if ch in counts:
                ordered_letters.append({"letter": ch, "count": counts[ch]})
        return jsonify({"success": True, "total_letters": len(ordered_letters), "letters": ordered_letters})
    except Exception as e:
        logging.error(f"Error in rigveda_get_pratika_letters: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@apps_bp.route('/rigveda/pratika', methods=['GET'])
def rigveda_get_pratika():
    """Return mantras starting with a specific Sanskrit letter or matching a search string."""
    letter = request.args.get('letter', '').strip()
    q = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 1500)), 2000)

    conn = _get_rigveda_conn()
    if not conn:
        return jsonify({"success": False, "error": "Database not initialized"}), 404
    try:
        cur = conn.cursor()
        if q:
            import re
            clean_q = re.sub(r'[\u0951\u0952\u1CD0-\u1CFF\uA8E0-\uA8FF\u0300-\u036F]', '', q).strip()
            cur.execute("""
                SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                       rishi, devata, chandas, pratika, pratika_svara
                FROM riks
                WHERE pratika LIKE ? OR samhita LIKE ?
                ORDER BY mandala ASC, sukta ASC, rik ASC
                LIMIT ?
            """, (f"%{clean_q}%", f"%{clean_q}%", limit))
        elif letter:
            cur.execute("""
                SELECT id, mandala, sukta, rik, ashtaka, adhyaya, varga, anuvaka,
                       rishi, devata, chandas, pratika, pratika_svara
                FROM riks
                WHERE first_char = ?
                ORDER BY pratika ASC, mandala ASC, sukta ASC, rik ASC
                LIMIT ?
            """, (letter, limit))
        else:
            return jsonify({"success": False, "error": "Provide either 'letter' or 'q' parameter."}), 400

        rows = cur.fetchall()
        items = []
        for r in rows:
            items.append({
                "id": r['id'],
                "mandala": r['mandala'],
                "sukta": r['sukta'],
                "rik": r['rik'],
                "ashtaka": r['ashtaka'],
                "adhyaya": r['adhyaya'],
                "varga": r['varga'],
                "anuvaka": r['anuvaka'],
                "rishi": r['rishi'],
                "devata": r['devata'],
                "chandas": r['chandas'],
                "pratika": r['pratika'] or '',
                "pratika_svara": r['pratika_svara'] or r['pratika'] or ''
            })
        return jsonify({"success": True, "total": len(items), "items": items})
    except Exception as e:
        logging.error(f"Error in rigveda_get_pratika: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()









