"""
Sanskrit Digital Library - OCR Web App

A Flask web application for searching OCR'd text.
Features:
- Admin panel for bulk uploading folders with txt and metadata files
- Public search page with highlighting
- Metadata integration for browsing and searching
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, Response, send_file, make_response
from functools import wraps
import requests
import os
import re
import zipfile
import shutil
import tempfile
import urllib.request
import urllib.parse
import json
from datetime import datetime
import csv
import math
import time
import io
import openpyxl
from openpyxl.styles import Protection
from werkzeug.utils import secure_filename
import threading
import uuid
import gzip
import zstandard as zstd
import config
import hashlib
import gzip

import config
import time
import sanskrit_utils
from ocr import register_ocr_routes
from db import common_db, quiz_db, katha_db, articles_db, play_db
from admin_pipeline import register_pipeline_routes
from admin_chunking import register_chunking_routes
import api_v1

def log_change(*args, **kwargs):
    """No-op stub: System Audit Logging has been permanently removed."""
    pass

def generate_text_diff(old_text, new_text):
    import difflib
    old_lines = old_text.splitlines() if old_text else []
    new_lines = new_text.splitlines() if new_text else []
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile='Before', tofile='After', lineterm=''))
    return '\n'.join(diff)

def get_logs():
    return []

def clear_logs():
    return True

def import_logs(logs_data):
    return True

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'static'))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_COOKIE_PATH'] = '/'
SERVER_STARTUP_ID = str(uuid.uuid4())
common_db.init_db()
katha_db.init_db()
quiz_db.init_db()
articles_db.init_db()
play_db.init_db()

# Auto-seed quiz questions from static JSON if database table is empty
_quiz_count = quiz_db.get_quiz_question_count()
if _quiz_count == 0:
    _quiz_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'quiz', 'questions.json')
    if os.path.exists(_quiz_json_path):
        _seeded = quiz_db.reset_quiz_questions_from_json(_quiz_json_path)
        print(f"Auto-imported {_seeded} quiz questions from questions.json into SQLite")
    else:
        print("Warning: quiz/questions.json not found, quiz_questions table is empty")
else:
    print(f"Quiz questions database: {_quiz_count} questions loaded")

register_ocr_routes(app)
register_pipeline_routes(app)
register_chunking_routes(app)
app.register_blueprint(api_v1.api_bp, url_prefix='/api/v1')

@app.errorhandler(404)
def handle_api_404(e):
    if request.path.startswith('/api/'):
        app.logger.warning(f"API 404 Error: {request.method} {request.path}")
        return jsonify({"error": "Route not found", "path": request.path}), 404
    return e

app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH


@app.after_request
def add_header(response):
    """Disable browser caching for all UI routes to ensure fresh data after login/updates and handle CORS dynamically."""
    content_type = response.headers.get('Content-Type', '')
    if 'text/html' in content_type or 'application/json' in content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
    
    # Dynamic CORS Handling for External API Routes
    origin = request.headers.get('Origin')
    if origin:
        allowed = False
        origin_lower = origin.lower()
        # Allow localhost for local development
        if "localhost" in origin_lower or "127.0.0.1" in origin_lower:
            allowed = True
        # Same-origin requests from the unified site don't need CORS,
        # but allow samshodhanamandiram.in for any edge cases
        elif origin_lower.endswith("samshodhanamandiram.in"):
            allowed = True
            
        if allowed:
            response.headers['Access-Control-Allow-Origin'] = origin
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-User-Token'
            response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, DELETE, PUT'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            
    return response


@app.route('/favicon.ico')
def favicon():
    return send_file(os.path.join(app.root_path, 'favicon.ico'), mimetype='image/x-icon')

@app.route('/transliterator')
def transliterator_page():
    return render_template('public/transliterator.html')


@app.route('/api/transliterator/status', methods=['GET'])
def transliterator_bot_status_public():
    """Public status endpoint for Transliterator Telegram Bot."""
    try:
        from admin_shared import _get_transliterator_bot_manager
        bot_mgr = _get_transliterator_bot_manager()
        status_info = bot_mgr.get_bot_status_info()
        return jsonify({
            'success': True,
            'running': status_info.get('running', False),
            'bot_username': status_info.get('bot_username', 'TVSM_Translatorator_Bot')
        })
    except Exception as e:
        return jsonify({'success': False, 'running': False, 'bot_username': 'TVSM_Translatorator_Bot'})


@app.route('/varga-panchama')
def varga_panchama_page():
    return render_template('public/varga_panchama.html')

# Persistent cache paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = tempfile.gettempdir()
ZIP_TASKS_DIR = os.path.join(TEMP_DIR, 'sdl_zip_tasks')
BROWSE_CACHE_FILE = os.path.join(APP_DIR, 'sdl_browse_cache.json')
os.makedirs(ZIP_TASKS_DIR, exist_ok=True)

# Persistent mobile catalog cache
CATALOG_CACHE_FILE = os.path.join(APP_DIR, 'sdl_mobile_catalog_cache.json')
WARMUP_STATUS_FILE = os.path.join(APP_DIR, 'warmup_status.txt')
CATALOG_METADATA_CACHE = {}
_warmup_running = False
_warmup_lock = threading.Lock()

# Fixed compression level (optimal for standard and ARM instances)
CURRENT_ZSTD_LEVEL = 7

# Feedback file
FEEDBACK_FILE = os.path.join(app.config['UPLOAD_FOLDER'], 'feedback.json')


def get_feedback_data():
    """Load feedback data from file"""
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}


def get_book_sort_key(book_id, feedback_data):
    """Generate a sort key for a book based on feedback: Up > Neutral > Down"""
    stats = feedback_data.get(book_id, {'up': 0, 'down': 0})
    up = stats.get('up', 0)
    down = stats.get('down', 0)
    
    # Category: 1 (Up), 0 (Neutral), -1 (Down)
    if up > down:
        category = 1
    elif up < down:
        category = -1
    else:
        category = 0
        
    net_score = up - down
    
    # Sort by: category descending, then net score descending, then book name ascending
    return (-category, -net_score, book_id.lower())


_catalog_cache_mtime = 0

def load_catalog_cache():
    global CATALOG_METADATA_CACHE, _catalog_cache_mtime
    if os.path.exists(CATALOG_CACHE_FILE):
        try:
            mtime = os.path.getmtime(CATALOG_CACHE_FILE)
            if mtime > _catalog_cache_mtime:
                with open(CATALOG_CACHE_FILE, 'r', encoding='utf-8') as f:
                    CATALOG_METADATA_CACHE = json.load(f)
                _catalog_cache_mtime = mtime
                print(f"Loaded {len(CATALOG_METADATA_CACHE)} items from persistent catalog cache.")
        except Exception as e:
            print(f"Error loading catalog cache: {e}")
    else:
        CATALOG_METADATA_CACHE = {}
        _catalog_cache_mtime = 0

def save_catalog_cache():
    global _catalog_cache_mtime
    try:
        with open(CATALOG_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(CATALOG_METADATA_CACHE, f)
        if os.path.exists(CATALOG_CACHE_FILE):
            _catalog_cache_mtime = os.path.getmtime(CATALOG_CACHE_FILE)
    except Exception as e:
        print(f"Error saving catalog cache: {e}")

def get_zip_task(task_id):
    path = os.path.join(ZIP_TASKS_DIR, f"{task_id}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_zip_task(task_id, data):
    path = os.path.join(ZIP_TASKS_DIR, f"{task_id}.json")
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except Exception:
        pass

def delete_zip_task(task_id):
    path = os.path.join(ZIP_TASKS_DIR, f"{task_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def get_browse_cache():
    if os.path.exists(BROWSE_CACHE_FILE):
        try:
            with open(BROWSE_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'items': [], 'identifiers': [], 'last_updated': 0}

def save_browse_cache(data):
    tmp_path = BROWSE_CACHE_FILE + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp_path, BROWSE_CACHE_FILE)
    except Exception:
        pass


# =============================================================================
# AUTHENTICATION
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            if 'user_logged_in' in session:
                return redirect('/user/sdl-profile')
            return redirect(url_for('unified_login'))
        return f(*args, **kwargs)
    return decorated_function

def user_login_required(f):
    """Decorator for routes that require public user login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_logged_in' not in session and not (session.get('logged_in') and session.get('admin_role') == 'super'):
            if request.path.startswith('/api/') or request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Login required to download or access this resource.', 'login_required': True}), 401
            return redirect(url_for('unified_login'))
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('unified_login'))
            
            # Super-admin has all permissions
            if session.get('admin_role') == 'super':
                return f(*args, **kwargs)
            
            # Check for low-level admin permissions
            user_perms = session.get('admin_permissions', [])
            if permission in user_perms:
                return f(*args, **kwargs)
            
            # Permission denied
            return render_template('admin/forbidden.html', permission=permission), 403
        return decorated_function
    return decorator


# =============================================================================
# ARCHIVE.ORG API FUNCTIONS
# =============================================================================

def search_archive_org(query, rows=20, page=1, sort='downloads desc', texts_only=True):
    """Search for items using the metadata provider API"""
    try:
        # Build search query
        if texts_only:
            full_query = f'({query}) AND mediatype:texts'
        else:
            full_query = f'({query})'
        
        # API endpoint
        base_url = 'https://archive.org/advancedsearch.php'
        params = {
            'q': full_query,
            'fl[]': ['identifier', 'title', 'creator', 'description', 'subject', 'date', 
                     'downloads', 'mediatype', 'collection', 'language'],
            'sort[]': sort,
            'rows': rows,
            'page': page,
            'output': 'json'
        }
        
        # Build URL with params
        param_str = urllib.parse.urlencode(params, doseq=True)
        url = f'{base_url}?{param_str}'
        
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())
        
        return {
            'success': True,
            'numFound': data.get('response', {}).get('numFound', 0),
            'docs': data.get('response', {}).get('docs', [])
        }
    except Exception as e:
        return {'success': False, 'error': str(e), 'numFound': 0, 'docs': []}


def get_archive_item_metadata(identifier):
    """Get full metadata for an archive.org item"""
    try:
        url = f'https://archive.org/metadata/{identifier}'
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read().decode())
        return {'success': True, 'data': data}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_featured_collections():
    """Get featured text collections for Sanskrit Digital Library browse section"""
    collections = [
        {'id': 'द्वैत', 'name': 'द्वैत', 'icon': '🕉️', 'query_type': 'subject'},
        {'id': 'अद्वैत', 'name': 'अद्वैत', 'icon': '🕉️', 'query_type': 'subject'},
        {'id': 'विशिष्टाद्वैत', 'name': 'विशिष्टाद्वैत', 'icon': '🕉️', 'query_type': 'subject'},
        {'id': 'न्यायशास्त्र', 'name': 'न्यायशास्त्र', 'icon': '⚖️', 'query_type': 'subject'},
        {'id': 'व्याकरणशास्त्र', 'name': 'व्याकरणशास्त्र', 'icon': '📖', 'query_type': 'subject'},
        {'id': 'शास्त्र', 'name': 'शास्त्र', 'icon': '📜', 'query_type': 'subject'},
        {'id': 'इतिहास', 'name': 'इतिहास', 'icon': '🏛️', 'query_type': 'subject'},
        {'id': 'पुराण', 'name': 'पुराण', 'icon': '🔱', 'query_type': 'subject'},
        {'id': 'स्मृति', 'name': 'स्मृति', 'icon': '📿', 'query_type': 'subject'},
        {'id': 'स्तोत्र', 'name': 'स्तोत्र', 'icon': '🙏', 'query_type': 'subject'},
    ]
    return collections


def get_local_identifiers():
    """Extract archive.org identifiers from local books' metadata.txt"""
    identifiers = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    if os.path.exists(upload_folder):
        for folder_name in os.listdir(upload_folder):
            folder_path = os.path.join(upload_folder, folder_name)
            if os.path.isdir(folder_path):
                metadata = get_metadata_from_folder(folder_path)
                source_url = metadata.get('source', '')
                idx = None
                if source_url:
                    # Extract identifier from URL
                    # Usually: https://archive.org/details/IDENTIFIER
                    parsed_url = urllib.parse.urlparse(source_url)
                    path_parts = parsed_url.path.strip('/').split('/')
                    if 'details' in path_parts:
                        idx_pos = path_parts.index('details')
                        if idx_pos + 1 < len(path_parts):
                            idx = path_parts[idx_pos + 1]
                    elif path_parts:
                        idx = path_parts[-1]
                
                if not idx:
                    idx = folder_name
                
                identifiers.append(idx.lower())
    
    return list(set(identifiers))


def fetch_metadata_batches(identifiers, batch_size=30):
    """Fetch metadata from archive.org in batches to avoid URL length limits"""
    all_docs = []
    
    for i in range(0, len(identifiers), batch_size):
        batch = identifiers[i:i + batch_size]
        # More compact query: (identifier:id1 OR identifier:id2 ...)
        id_query = " OR ".join([f'identifier:"{idx}"' for idx in batch])
        
        # We only need specific fields for browse
        result = search_archive_org(id_query, rows=batch_size, page=1, texts_only=False)
        if result['success']:
            all_docs.extend(result.get('docs', []))
            
    return all_docs


# =============================================================================
# LOCAL SEARCH FUNCTIONS (from search_ocr.pyw)
# =============================================================================

def extract_proofreading_percentage(notes_str):
    """Extract proofreading completion percentage from notes.
    Only matches the exact format 'proofreading_done_X%' where X is digits.
    """
    if not notes_str:
        return 0
    match = re.search(r'proofreading_done_(\d+)%', notes_str)
    if match:
        return int(match.group(1))
    return 0


def get_all_books(bypass_cache=False, include_unpublished=False):
    """Get list of all uploaded books/folders"""
    load_catalog_cache()
    books = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    if os.path.exists(upload_folder):
        for folder_name in os.listdir(upload_folder):
            folder_path = os.path.join(upload_folder, folder_name)
            if os.path.isdir(folder_path):
                txt_files = [f for f in os.listdir(folder_path) 
                            if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
                metadata = get_metadata_from_folder(folder_path, bypass_cache=bypass_cache)
                
                is_published = metadata.get('published', True)
                if not include_unpublished and not is_published:
                    continue
                    
                notes_str = metadata.get('notes', '')
                pct = extract_proofreading_percentage(notes_str)
                
                books.append({
                    'name': folder_name,
                    'path': folder_path,
                    'has_txt': len(txt_files) > 0,
                    'archive_url': metadata.get('source', ''),
                    'tags': metadata.get('tags', ''),
                    'subbooks': metadata.get('subbooks_raw', ''),
                    'notes': notes_str,
                    'proofread_pct': pct,
                    'published': is_published,
                    'verification': metadata.get('verification', 'verified'),
                    'is_community': metadata.get('is_community', False),
                    'contributor': metadata.get('contributor', ''),
                    'author': metadata.get('author', '')
                })
    
    return books


def get_filtered_book_names(filters):
    """Get list of book names matching the specified search filters"""
    all_books = get_all_books(bypass_cache=True, include_unpublished=True)
    
    feedback_data = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass

    q_name = filters.get('name', '').strip().lower()
    q_tag = filters.get('tag', '').strip().lower()
    q_neg_tag = filters.get('neg_tag', '').strip().lower()
    q_subbook = filters.get('subbook', '').strip().lower()
    q_ocr = filters.get('ocr', '').strip().lower()
    q_status = filters.get('status', '').strip().lower()
    q_proofread = filters.get('proofread', '').strip().lower()
    q_feedback = filters.get('feedback', '').strip().lower()
    q_community = filters.get('community', '').strip().lower()
    
    neg_terms = [t.strip() for t in q_neg_tag.split(',') if t.strip()]

    filtered_books = []
    for book in all_books:
        name_match = not q_name or q_name in book['name'].lower()
        tag_match = not q_tag or q_tag in (book.get('tags') or '').lower()
        
        neg_tag_match = True
        if neg_terms:
            book_tags = (book.get('tags') or '').lower()
            book_name = book['name'].lower()
            if any(term in book_tags or term in book_name for term in neg_terms):
                neg_tag_match = False

        subbook_match = not q_subbook or q_subbook in (book.get('subbooks') or '').lower()
        
        ocr_match = True
        if q_ocr == 'digitized':
            ocr_match = book.get('has_txt', False)
        elif q_ocr == 'text_only':
            ocr_match = book.get('has_txt', False) and not book.get('archive_url')
        elif q_ocr == 'pdf_only':
            ocr_match = bool(book.get('archive_url')) and not book.get('has_txt', False)
            
        status_match = True
        if q_status == 'published':
            status_match = book.get('published', True)
        elif q_status == 'draft':
            status_match = not book.get('published', True)

        pct = book.get('proofread_pct')
        proofread_match = True
        if q_proofread == 'not_started':
            proofread_match = not pct or pct == 0
        elif q_proofread == 'in_progress':
            proofread_match = bool(pct and 0 < pct < 100)
        elif q_proofread == 'completed':
            proofread_match = bool(pct and pct >= 100)

        fb = feedback_data.get(book['name'], {'up': 0, 'down': 0, 'comments': []})
        up_cnt = fb.get('up', 0)
        down_cnt = fb.get('down', 0)
        comments_cnt = len(fb.get('comments', []))

        feedback_match = True
        if q_feedback == 'has_up':
            feedback_match = up_cnt > 0
        elif q_feedback == 'has_down':
            feedback_match = down_cnt > 0
        elif q_feedback == 'has_comments':
            feedback_match = comments_cnt > 0
        elif q_feedback == 'any':
            feedback_match = (up_cnt > 0 or down_cnt > 0 or comments_cnt > 0)
            
        community_match = True
        if q_community == 'only':
            community_match = book.get('is_community', False)
        elif q_community == 'exclude':
            community_match = not book.get('is_community', False)

        if name_match and tag_match and neg_tag_match and subbook_match and ocr_match and status_match and proofread_match and feedback_match and community_match:
            filtered_books.append(book['name'])
            
    return filtered_books



AVATARS = [
    {'emoji': '🦢', 'gradient': 'linear-gradient(135deg, #a5b4fc, #818cf8)'}, # Indigo
    {'emoji': '🦚', 'gradient': 'linear-gradient(135deg, #059669, #10b981)'}, # Emerald
    {'emoji': '🐘', 'gradient': 'linear-gradient(135deg, #64748b, #475569)'}, # Slate
    {'emoji': '🦁', 'gradient': 'linear-gradient(135deg, #f59e0b, #d97706)'}, # Amber
    {'emoji': '🦉', 'gradient': 'linear-gradient(135deg, #7c3aed, #6d28d9)'}, # Purple
    {'emoji': '🧘', 'gradient': 'linear-gradient(135deg, #ec4899, #db2777)'}, # Pink
    {'emoji': '🌅', 'gradient': 'linear-gradient(135deg, #f97316, #ea580c)'}, # Orange
    {'emoji': '🦄', 'gradient': 'linear-gradient(135deg, #f472b6, #c084fc)'}, # Pastel Purple
    {'emoji': '🐬', 'gradient': 'linear-gradient(135deg, #06b6d4, #0891b2)'}, # Cyan
    {'emoji': '🦊', 'gradient': 'linear-gradient(135deg, #f97316, #d97706)'}, # Orange/Amber
    {'emoji': '🐯', 'gradient': 'linear-gradient(135deg, #f59e0b, #b45309)'}, # Warm Gold
    {'emoji': '🦜', 'gradient': 'linear-gradient(135deg, #10b981, #84cc16)'}  # Lime/Green
]

def get_avatar_for_id(user_id, avatar_idx=None):
    if avatar_idx is None:
        if not user_id:
            return AVATARS[0]
        try:
            avatar_idx = int(user_id) % len(AVATARS)
        except (ValueError, TypeError):
            avatar_idx = 0
    try:
        idx = int(avatar_idx) % len(AVATARS)
        return AVATARS[idx]
    except (ValueError, TypeError):
        return AVATARS[0]


def check_semantic_search_access():
    is_admin = session.get('logged_in', False)
    is_super = session.get('admin_role') == 'super'
    user_id = session.get('user_id')

    role = 'non_logged_in'
    if is_admin:
        role = 'admin'
    elif user_id:
        role = 'logged_in'

    if is_super:
        return True

    override = None
    if user_id:
        try:
            override = common_db.get_user_ai_override(user_id)
        except Exception:
            pass

    if override and override.get('semantic_search_access') in ('allow', 'block'):
        return override['semantic_search_access'] == 'allow'

    try:
        return common_db.get_system_setting(f'role_{role}_semantic_search_access', 'allow') == 'allow'
    except Exception:
        return True


def is_admin_user_session():
    """Returns True if the current session belongs to an admin user (super or low-level / logged-in admin)."""
    return bool(session.get('logged_in') and (session.get('admin_role') in ('super', 'low-level') or session.get('admin_username')))


@app.context_processor
def inject_global_vars():
    is_admin_user = is_admin_user_session()
    local_books = get_all_books(include_unpublished=is_admin_user)
    user_id = session.get('user_id')
    is_admin = is_admin_user
    
    if not user_id and is_admin:
        admin_username = session.get('admin_username', '').upper()
        admin_email = f"{admin_username.lower()}@system.local"
        try:
            conn = common_db.get_db()
            row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
            conn.close()
            if row:
                user_id = row['id']
        except Exception:
            pass

    user_avatar = None
    user_profile_pic_url = None
    
    if user_id:
        user = common_db.get_user_by_id(user_id)
        avatar_idx = 0
        profile_pic = None
        if user:
            avatar_idx = user.get('avatar_idx', 0)
            profile_pic = user.get('profile_pic')
            session['user_avatar_idx'] = avatar_idx
            session['user_profile_pic'] = profile_pic
                
        user_avatar = get_avatar_for_id(user_id, avatar_idx)
        if profile_pic:
            filepath = os.path.join(app.root_path, 'static', 'uploads', 'profile_pics', profile_pic)
            if os.path.exists(filepath):
                user_profile_pic_url = url_for('static', filename='uploads/profile_pics/' + profile_pic)
            
    return {
        'local_books_count': len(local_books),
        'user_logged_in': session.get('user_logged_in', False) or is_admin,
        'user_display_name': session.get('user_display_name', '') or session.get('admin_username', ''),
        'user_id': user_id,
        'user_avatar': user_avatar,
        'user_profile_pic_url': user_profile_pic_url,
        'AVATARS': AVATARS,
        'server_startup_id': SERVER_STARTUP_ID,
        'ai_search_enabled': check_semantic_search_access(),
        'google_client_id': getattr(config, 'GOOGLE_CLIENT_ID', '')
    }


def get_metadata_from_folder(folder_path, bypass_cache=False):
    """Read metadata from metadata.txt, using memory cache if available"""
    folder_name = os.path.basename(folder_path)
    if not bypass_cache and folder_name in CATALOG_METADATA_CACHE:
        cached = CATALOG_METADATA_CACHE[folder_name]
        levels_map = parse_level_field(cached.get('levels_raw', '')) if cached.get('levels_raw') else cached.get('levels', {})
        verif = cached.get('verification', 'verified')
        return {
            'source': cached.get('source', ''),
            'tags': cached.get('tags', ''),
            'subbooks': cached.get('subbooks', []),
            'subbooks_raw': cached.get('subbooks_raw', ''),
            'levels': levels_map,
            'levels_raw': cached.get('levels_raw', ''),
            'notes': cached.get('notes', ''),
            'published': cached.get('published', True),
            'verification': verif,
            'is_community': (verif == 'unverified'),
            'contributor': cached.get('contributor', ''),
            'author': cached.get('author', '')
        }

    metadata = {
        'source': '', 'tags': '', 'subbooks': [], 'subbooks_raw': '', 
        'notes': '', 'published': True, 'levels': {}, 'levels_raw': '',
        'verification': 'verified', 'is_community': False,
        'contributor': '', 'author': ''
    }
    metadata_path = os.path.join(folder_path, 'metadata.txt')
    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('Source:'):
                        metadata['source'] = line.replace('Source:', '').strip()
                    elif line.startswith('Tags:'):
                        metadata['tags'] = line.replace('Tags:', '').strip()
                    elif line.startswith('Subbook:'):
                        # Ignore Subbook line completely
                        pass
                    elif line.startswith('Level:'):
                        raw = line.split(':', 1)[1].strip()
                        metadata['levels_raw'] = raw
                        metadata['levels'] = parse_level_field(raw)
                    elif line.startswith('Notes:'):
                        metadata['notes'] = line.replace('Notes:', '').strip().replace('\\n', '\n')
                    elif line.startswith('Published:'):
                        metadata['published'] = line.replace('Published:', '').strip().lower() == 'true'
                    elif line.startswith('Verification:'):
                        metadata['verification'] = line.replace('Verification:', '').strip().lower()
                        metadata['is_community'] = (metadata['verification'] == 'unverified')
                    elif line.startswith('Contributor:'):
                        metadata['contributor'] = line.replace('Contributor:', '').strip()
                    elif line.startswith('Author:'):
                        metadata['author'] = line.replace('Author:', '').strip()
        except:
            pass
    
    # Write back to in-memory cache so subsequent non-bypass calls get fresh data
    existing = CATALOG_METADATA_CACHE.get(folder_name, {})
    existing.update({
        'source': metadata['source'],
        'tags': metadata['tags'],
        'subbooks': metadata['subbooks'],
        'subbooks_raw': metadata['subbooks_raw'],
        'levels': metadata.get('levels', {}),
        'levels_raw': metadata.get('levels_raw', ''),
        'notes': metadata['notes'],
        'published': metadata['published'],
        'verification': metadata['verification'],
        'is_community': metadata['is_community'],
        'contributor': metadata['contributor'],
        'author': metadata['author']
    })
    CATALOG_METADATA_CACHE[folder_name] = existing

    return metadata


def parse_level_field(raw_str):
    """Parse a Level: field string into a dictionary mapping level codes to human-readable names.
    Format example: '1- "ब्रह्मसूत्रम्", 1.1-"प्रथमाध्यायः", 3.1-"अनुव्याख्यानम् १", 4.1-“मङ्गलाचरणम्”'
    Supports standard quotes, double quotes, single quotes, smart quotes (“ ” ‘ ’), and unquoted strings.
    """
    levels = {}
    if not raw_str:
        return levels
        
    pattern = r'(\d+(?:\.\d+)*)\s*[-:=]\s*["\'“”‘’]?([^"\'“”‘’,\n]+)["\'“”‘’]?'
    for match in re.finditer(pattern, str(raw_str)):
        code = match.group(1).strip()
        name = match.group(2).strip()
        name = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', name).strip()
        if code and name:
            levels[code] = name
            
    if not levels:
        for item in str(raw_str).split(','):
            if '-' in item or ':' in item or '=' in item:
                parts = re.split(r'[-:=]', item, 1)
                if len(parts) == 2:
                    code = parts[0].strip()
                    name = parts[1].strip()
                    name = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', name).strip()
                    if code and name:
                        levels[code] = name
    return levels



def parse_books_field(raw_str):
    """Parse a Books: field string into a list of sub-book dicts.
    
    Format: '1-50:BookName1, 51-120:BookName2, 200:SinglePageBook, ...'
    Supports both ranges (1-50) and single pages (200).
    Returns: [{'start': 1, 'end': 50, 'name': 'BookName1'}, ...]
    """
    subbooks = []
    if not raw_str:
        return subbooks
    
    for entry in raw_str.split(','):
        entry = entry.strip()
        if not entry or ':' not in entry:
            continue
        # Split on first colon only (book name may contain colons)
        range_part, name = entry.split(':', 1)
        name = name.strip()
        range_part = range_part.strip()
        
        try:
            if '-' in range_part:
                start_str, end_str = range_part.split('-', 1)
                start = int(start_str.strip())
                end = int(end_str.strip())
            else:
                # Single page number
                start = int(range_part)
                end = start
            if name:
                subbooks.append({'start': start, 'end': end, 'name': name})
        except (ValueError, TypeError):
            continue
    
    return subbooks


def get_subbook_for_page(page, subbooks_list):
    """Given a page number and a list of sub-book dicts, return the sub-book name or None."""
    if not subbooks_list or not isinstance(page, int) or page <= 0:
        return None
    
    for book in subbooks_list:
        if book['start'] <= page <= book['end']:
            return book['name']
    
    return None


def parse_sdl_blocks(content):
    """
    Parses decompressed text content containing $level$ markers into structured blocks.
    Supports levels like $3.4$ and section sub-markers like $3.4.nameofsection$.
    Example input:
        $3.1$
        (न्यायसुधा-मङ्गलाचरणम् तथा उपोद्घातः...)
        $3.4.मङ्गलाचरणम्$
        अथातो ब्रह्मजिज्ञासा ॥ १.१.१ ॥
        $2$
        अथातो ब्रह्मजिज्ञासा इत्यस्य सूत्रस्य व्याख्यानम्...
    Returns list of dicts:
        [{'level': '3.1', 'text': '...'}, {'level': '3.4.मङ्गलाचरणम्', 'text': '...'}, ...]
    """
    if not content or '$' not in content:
        return [{'level': '1', 'text': content or ''}]
    
    parts = re.split(r'\$(\d+(?:\.[^\$\r\n]+)*)\$\n?', content)
    blocks = []
    
    if parts[0].strip():
        blocks.append({'level': '1', 'text': parts[0].strip()})
        
    for i in range(1, len(parts), 2):
        level_code = parts[i].strip()
        text_content = parts[i+1].strip() if i+1 < len(parts) else ''
        if text_content:
            blocks.append({'level': level_code, 'text': text_content})
            
    return blocks


def get_level_map(text):
    """Scans text for $level$ tags and returns list of (start_idx, level_code)."""
    map_list = []
    if not text or '$' not in text:
        return map_list
    for m in re.finditer(r'\$(\d+(?:\.[^\$\r\n]+)*)\$', text):
        map_list.append((m.start(), m.group(1).strip()))
    return map_list


def get_level_for_index(idx, level_map):
    """Returns the active level code for a given character index position."""
    if not level_map:
        return None
    current_level = None
    for start_idx, level_code in level_map:
        if idx >= start_idx:
            current_level = level_code
        else:
            break
    return current_level


def get_level_display_name_py(code, levels_map):
    """Returns human readable level name for code, including dot hierarchy and section name fallback."""
    if not code:
        return ''
    code_str = str(code).strip()
    if not levels_map:
        return code_str
    if code_str in levels_map:
        return str(levels_map[code_str]).strip()
    
    prefix = code_str
    suffix_parts = []
    while '.' in prefix:
        last_dot = prefix.rfind('.')
        suffix_parts.insert(0, prefix[last_dot+1:])
        prefix = prefix[:last_dot]
        if prefix in levels_map:
            base_name = str(levels_map[prefix]).strip()
            suffix_str = '.'.join(suffix_parts)
            return f"{base_name} - {suffix_str}" if suffix_str else base_name
            
    return code_str


def get_full_level_path_py(code, levels_map):
    """
    Returns full ancestor level hierarchy path for a given level code.
    Includes only true prefix ancestors and exact matches from levels_map.
    """
    if not code:
        return ''
    code_str = str(code).strip()
    if not levels_map:
        return code_str

    path_names = []
    seen = set()

    sorted_keys = sorted(levels_map.keys(), key=lambda k: (len(str(k).split('.')), str(k)))

    matched_key = None
    for k in sorted_keys:
        k_str = str(k).strip()
        if code_str == k_str or code_str.startswith(k_str + '.'):
            name = str(levels_map[k]).strip()
            clean = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', name).strip()
            if clean and clean not in seen:
                path_names.append(clean)
                seen.add(clean)
                matched_key = k_str

    parts = code_str.split('.')
    if matched_key:
        matched_parts_len = len(matched_key.split('.'))
        if len(parts) > matched_parts_len:
            section_name = '.'.join(parts[matched_parts_len:])
            clean_sec = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', section_name).strip()
            if clean_sec and clean_sec not in seen:
                path_names.append(clean_sec)
                seen.add(clean_sec)
    elif len(parts) >= 3 and code_str not in levels_map:
        section_name = '.'.join(parts[2:])
        clean_sec = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', section_name).strip()
        if clean_sec and clean_sec not in seen:
            path_names.append(clean_sec)
            seen.add(clean_sec)

    return ' > '.join(path_names) if path_names else get_level_display_name_py(code_str, levels_map)


def get_level_theme_py(code):
    """Returns CSS variable-based theme colors for level cards."""
    try:
        tier = int(str(code).split('.')[0])
    except Exception:
        tier = 1

    if tier == 1:
        return {
            'border': 'rgba(244, 63, 94, 0.3)',
            'bg': 'rgba(244, 63, 94, 0.03)',
            'headerBg': 'rgba(244, 63, 94, 0.15)',
            'textColor': '#f43f5e'
        }
    elif tier == 2:
        return {
            'border': 'rgba(56, 189, 248, 0.3)',
            'bg': 'rgba(56, 189, 248, 0.03)',
            'headerBg': 'rgba(56, 189, 248, 0.15)',
            'textColor': '#38bdf8'
        }
    elif tier == 3:
        return {
            'border': 'rgba(16, 185, 129, 0.3)',
            'bg': 'rgba(16, 185, 129, 0.03)',
            'headerBg': 'rgba(16, 185, 129, 0.15)',
            'textColor': '#10b981'
        }
    else:
        return {
            'border': 'rgba(245, 158, 11, 0.3)',
            'bg': 'rgba(245, 158, 11, 0.03)',
            'headerBg': 'rgba(245, 158, 11, 0.15)',
            'textColor': '#f59e0b'
        }


def render_structured_ocr_html(raw_html, levels_map):
    """
    Pre-renders $level$ tags in OCR text into structured hierarchical collapsible details cards on the server
    so the initial HTML paint has exact heading titles, nesting tree structure, and collapsibility.
    """
    if not raw_html or '$' not in str(raw_html):
        return raw_html or ''

    tag_regex = re.compile(r'(?:\$|&#36;|&dollar;)\s*(\d+(?:\.[^\$\r\n]+)*)\s*(?:\$|&#36;|&dollar;)(?:<br\s*/?>)?\n?', re.IGNORECASE)
    matches = list(tag_regex.finditer(str(raw_html)))
    if not matches:
        return raw_html

    html_parts = []
    intro = str(raw_html)[:matches[0].start()].strip()
    if intro:
        html_parts.append(f'<div class="intro-text" style="white-space: pre-line; line-height: 1.8; margin-bottom: 16px; text-align: center; width: 100%;">{intro}</div>')

    for i, m in enumerate(matches):
        code = m.group(1).strip()
        start_pos = m.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(raw_html)
        content = str(raw_html)[start_pos:end_pos].strip()
        content = re.sub(r'^(?:<br\s*/?>|\s)+|(?:<br\s*/?>|\s)+$', '', content, flags=re.IGNORECASE).strip()

        try:
            tier = int(code.split('.')[0])
        except Exception:
            tier = 1

        heading_name = get_level_display_name_py(code, levels_map)
        clean_name = re.sub(r'^[\s【\[\(]+|[\s】\]\)]+$', '', heading_name).strip() if heading_name else ''
        is_moolam = (tier == 1)
        theme = get_level_theme_py(code)
        card_title = f'📖 {clean_name}' if clean_name else (f'📖 Section {code}' if is_moolam else f'Layer {code}')

        html_parts.append(f'''
        <details class="sutra-card commentary-card level-{tier} layer-block layer-code-{code}" data-code="{code}" open style="margin-bottom: 16px; width: 100%; border: 1px solid {theme['border']}; border-radius: 8px; background: {theme['bg']}; overflow: hidden;">
            <summary class="moolam-header" onclick="toggleDetailsCard(event, this)" style="padding: 12px 18px; background: {theme['headerBg']}; font-weight: 700; color: {theme['textColor']}; cursor: pointer; user-select: none; width: 100%;">
                <div style="display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 12px;">
                    <span style="font-weight: 700; flex: 1; text-align: left;">{card_title}</span>
                    <span class="card-toggle-arrow" style="font-size: 13px; opacity: 0.85; flex-shrink: 0; margin-left: auto;">▼</span>
                </div>
            </summary>
            <div class="sutra-contents" style="padding: 16px; display: flex; flex-direction: column; width: 100%;">
                <div class="moolam-body" style="white-space: pre-line; line-height: 1.8; margin-bottom: 10px; text-align: center; width: 100%;">{content}</div>
            </div>
        </details>
        ''')

    return ''.join(html_parts)


def get_book_sections(subbooks, total_pages):
    """
    Given a list of defined subbooks (with start, end, name) and total_pages,
    returns a sorted list of sections (both defined subbooks and the gaps/non-mentioned sections).
    """
    if not total_pages or total_pages <= 0:
        return []
        
    # Sort subbooks by start page
    sorted_subs = sorted(subbooks, key=lambda x: x.get('start', 0))
    
    sections = []
    current = 1
    
    for sb in sorted_subs:
        start = sb.get('start', 0)
        end = sb.get('end', 0)
        name = sb.get('name', '')
        
        # If start is less than current, adjust or skip
        if start < current:
            if end < current:
                continue
            start = current
            
        if start > current:
            # There is an unmentioned gap before this subbook!
            gap_end = start - 1
            if gap_end == current:
                sections.append({
                    'start': current,
                    'end': gap_end,
                    'name': f'Page {current}',
                    'is_subbook': False
                })
            else:
                sections.append({
                    'start': current,
                    'end': gap_end,
                    'name': f'Pages {current} - {gap_end}',
                    'is_subbook': False
                })
        
        # Add the defined subbook
        sections.append({
            'start': start,
            'end': end,
            'name': name,
            'is_subbook': True
        })
        
        current = end + 1
        
    # Add any remaining gap at the end
    if current <= total_pages:
        if current == total_pages:
            sections.append({
                'start': current,
                'end': total_pages,
                'name': f'Page {current}',
                'is_subbook': False
            })
        else:
            sections.append({
                'start': current,
                'end': total_pages,
                'name': f'Pages {current} - {total_pages}',
                'is_subbook': False
            })
            
    return sections


def get_page_map(text_content):
    """
    Build a map of character indices to page numbers.
    Returns a list of tuples: (start_index, page_number)
    """
    page_map = []
    page_pattern = r'\{\[\((\d+)\)\]\}'
    
    for match in re.finditer(page_pattern, text_content):
        end = match.end()
        try:
            page_num = int(match.group(1))
            page_map.append((end, page_num))
        except ValueError:
            pass
            
    return page_map


def get_page_for_index(index, page_map):
    """Find the page number corresponding to a character index"""
    if not page_map:
        return 0
    
    current_page = 0
    for start_pos, page_num in page_map:
        if start_pos <= index:
            current_page = page_num
        else:
            break
    return current_page


# =============================================================================
# FILE CONTENT CACHE
# =============================================================================
_file_content_cache = {}
_FILE_CACHE_MAX = 500

def get_cached_file_content(file_path):
    """Read file content with LRU cache keyed by path+mtime. Auto-invalidates on file change. Supports .sdl Zstd decompression."""
    global _file_content_cache
    try:
        mtime = os.path.getmtime(file_path)
    except OSError:
        # Fallback if mtime fails
        if file_path.endswith('.sdl'):
            with open(file_path, 'rb') as f:
                data = f.read()
            if data.startswith(b'SDL\x03'):
                import zstandard as zstd
                dctx = zstd.ZstdDecompressor()
                return dctx.decompress(data[4:]).decode('utf-8')
            return ""
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    
    cache_key = f"{file_path}:{mtime}"
    if cache_key in _file_content_cache:
        return _file_content_cache[cache_key]
    
    if file_path.endswith('.sdl'):
        with open(file_path, 'rb') as f:
            data = f.read()
        if data.startswith(b'SDL\x03'):
            import zstandard as zstd
            dctx = zstd.ZstdDecompressor()
            content = dctx.decompress(data[4:]).decode('utf-8')
        else:
            content = ""
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    
    if len(_file_content_cache) >= _FILE_CACHE_MAX:
        oldest = next(iter(_file_content_cache))
        del _file_content_cache[oldest]
    _file_content_cache[cache_key] = content
    return content


def remove_spaces_and_hyphens(text):
    """Remove spaces and hyphens from text for searching"""
    return re.sub(r'[\s\-]', '', text)


def smart_search(text_content, query, sanskrit_normalize=False, custom_rules=None, search_mode='contains', allowed_ranges=None):
    """
    Search for query ignoring spaces and hyphens.
    Yields dicts: {'page': num, 'text': context} or None (ping)
    
    Args:
        text_content: The text to search in
        query: The query string
        sanskrit_normalize: If True, apply Sanskrit linguistic normalization
        custom_rules: Dict of custom rules for Sanskrit normalization
        search_mode: 'contains', 'exact', 'starts_with', or 'ends_with'
    """
    if not query:
        return

    # Generate bidirectional variants based on custom rules
    if sanskrit_normalize and custom_rules:
        query_variants = sanskrit_utils.get_custom_variants(query, custom_rules)
    else:
        query_variants = [query]

    # Remove spaces and hyphens from query variants
    query_variants_clean = [remove_spaces_and_hyphens(q) for q in query_variants]
    query_variants_clean = [q for q in query_variants_clean if q] # Filter out empty ones

    if not query_variants_clean:
        return

    # Pattern to allow spaces and hyphens between characters
    # This makes the search ignore spaces and hyphens like {[(123)]} page separators
    noise_pattern = r'[\s\-]*'
    
    variant_patterns = []
    for q_clean in query_variants_clean:
        escaped_query = re.escape(q_clean)
        
        search_pattern_parts = []
        for i, char in enumerate(escaped_query):
            search_pattern_parts.append(char)
            if i < len(escaped_query) - 1:
                search_pattern_parts.append(noise_pattern)
                
        variant_patterns.append(''.join(search_pattern_parts))
        
    # Boundary for Devanagari characters
    # Boundary for Sanskrit word characters (Devanagari letters/marks + Roman letters + digits)
    # We explicitly exclude Dandas (\u0964, \u0965) and Devanagari digits (\u0966-\u096F)
    # as they are common verse markers.
    sanskrit_word_chars = r'\u0900-\u0963\u0970-\u097Fa-zA-Z0-9'
    
    wrapped_patterns = []
    for p in variant_patterns:
        if search_mode == 'exact':
            wrapped_patterns.append(f'(?<![{sanskrit_word_chars}]){p}(?![{sanskrit_word_chars}])')
        elif search_mode == 'starts_with':
            wrapped_patterns.append(f'(?<![{sanskrit_word_chars}]){p}')
        elif search_mode == 'ends_with':
            wrapped_patterns.append(f'{p}(?![{sanskrit_word_chars}])')
        else: # contains
            wrapped_patterns.append(p)

    search_regex = r'(?:' + '|'.join(wrapped_patterns) + r')'
    
    try:
        compiled_re = re.compile(search_regex, re.IGNORECASE | re.UNICODE)
    except re.error:
        return

    # Build page map and level map
    page_map = get_page_map(text_content)
    level_map = get_level_map(text_content)

    for i, match in enumerate(compiled_re.finditer(text_content)):
        # Aggressive Stop: Yield None every few matches to check connection
        if i > 0 and i % 20 == 0:
            yield None

        start_idx = match.start()
        
        # Determine page number and level code
        page_num = get_page_for_index(start_idx, page_map)
        level_code = get_level_for_index(start_idx, level_map)

        # Filter by allowed sub-book range if active
        if allowed_ranges:
            if not any(start <= page_num <= end for start, end in allowed_ranges):
                continue
        
        # Extract context
        context_start = max(0, start_idx - 100)
        context_end = min(len(text_content), match.end() + 100)
        raw_context = text_content[context_start:context_end]
        
        # Clean up context
        clean_context = re.sub(r'\{\[\((\d+)\)\]\}', ' ', raw_context)
        clean_context = re.sub(r'(?:\$|&#36;|&dollar;)\s*(\d+(?:\.[^\$\r\n]+)*)\s*(?:\$|&#36;|&dollar;)', ' ', clean_context)
        clean_context = re.sub(r'\s+', ' ', clean_context).strip()
        
        yield {
            'page': page_num,
            'text': f"...{clean_context}...",
            'start_idx': start_idx,
            'level_code': level_code
        }


def search_in_folder(folder_path, text_queries, logic='or', sanskrit_normalize=False, custom_rules=None, max_results=0, search_mode='contains', allowed_ranges=None):
    """
    Search for terms in all txt files in folder.
    Yields matches or None (ping)
    
    Args:
        folder_path: Path to the folder containing txt files
        text_queries: List of queries to search for
        logic: 'or' or 'and' logic for multiple queries
        sanskrit_normalize: If True, apply Sanskrit linguistic normalization
        custom_rules: Dict of custom rules for Sanskrit normalization
        max_results: Maximum number of real matches to yield (0 = unlimited)
        search_mode: Mode for smart_search ('contains', 'exact', etc.)
        allowed_ranges: List of (start, end) page ranges to restrict search to
    """
    result_count = 0
    txt_files = [f for f in os.listdir(folder_path) if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
    total_files = len(txt_files)
    
    for i, file in enumerate(txt_files):
        txt_path = os.path.join(folder_path, file)
        # Aggressive Stop and Progress Indicator
        yield {'type': 'progress', 'current': i + 1, 'total': total_files}
        try:
            content = get_cached_file_content(txt_path)
            
            if logic == 'and':
                file_matches = []
                has_all = True
                for q in text_queries:
                    matches = []
                    gen = smart_search(content, q, sanskrit_normalize, custom_rules, search_mode=search_mode, allowed_ranges=allowed_ranges)
                    
                    for m in gen:
                        if m is None:
                            yield {'type': 'progress', 'current': i + 1, 'total': total_files} # Propagate heartbeat
                        else:
                            matches.append(m)
                    
                    if not matches:
                        has_all = False
                        break
                    file_matches.extend(matches)
                
                if has_all:
                    file_matches.sort(key=lambda x: x['page'])
                    for m in file_matches:
                        yield m
                        result_count += 1
                        if max_results > 0 and result_count >= max_results:
                            return
            else:
                for q in text_queries:
                    gen = smart_search(content, q, sanskrit_normalize, custom_rules, search_mode=search_mode, allowed_ranges=allowed_ranges)
                    
                    for m in gen:
                        if m is None:
                            yield {'type': 'progress', 'current': i + 1, 'total': total_files} # Propagate heartbeat
                        else:
                            yield m
                            result_count += 1
                            if max_results > 0 and result_count >= max_results:
                                return
            
        except Exception as e:
            print(f"Error reading {txt_path}: {e}")


def highlight_text(text, search_terms, custom_rules=None, search_mode='contains'):
    """Add HTML highlighting to search terms, ignoring spaces and hyphens"""
    if not search_terms:
        return text
    
    if isinstance(search_terms, str):
        search_terms = [search_terms]

    # Expand search terms to include all bidirectional variants based on custom rules
    if custom_rules:
        all_variants = []
        for term in search_terms:
            all_variants.extend(sanskrit_utils.get_custom_variants(term, custom_rules))
        search_terms = list(set(all_variants)) # Remove duplicates

    # Exact highlighting: use regex pattern that ignores spaces and hyphens
    regexes = []
    noise_pattern = r'[\s\-]*'
    
    for term in search_terms:
        term = term.strip()
        if not term: continue
        term_clean = remove_spaces_and_hyphens(term)
        escaped_query = re.escape(term_clean)
        pattern_parts = []
        for i, char in enumerate(escaped_query):
            pattern_parts.append(char)
            if i < len(escaped_query) - 1:
                pattern_parts.append(noise_pattern)
        regexes.append(''.join(pattern_parts))
        
    if not regexes:
        return text
        
    sanskrit_word_chars = r'\u0900-\u0963\u0970-\u097Fa-zA-Z0-9'
    wrapped_regexes = []
    for r in regexes:
        if search_mode == 'exact':
            wrapped_regexes.append(f'(?<![{sanskrit_word_chars}]){r}(?![{sanskrit_word_chars}])')
        elif search_mode == 'starts_with':
            wrapped_regexes.append(f'(?<![{sanskrit_word_chars}]){r}')
        elif search_mode == 'ends_with':
            wrapped_regexes.append(f'{r}(?![{sanskrit_word_chars}])')
        else:
            wrapped_regexes.append(r)

    combined_regex = '|'.join(f'({wr})' for wr in wrapped_regexes)
    
    try:
        pattern = re.compile(combined_regex, re.IGNORECASE | re.UNICODE)
        return pattern.sub(lambda m: f'<mark class="highlight">{m.group()}</mark>', text)
    except:
        return text


def clean_preview_level_tags_py(text, levels_map=None):
    """Strips raw $level_code$ tags from preview text snippets."""
    if not text or '$' not in str(text):
        return text or ''
    tag_regex = re.compile(r'(?:\$|&#36;|&dollar;)\s*(\d+(?:\.[^\$\r\n]+)*)\s*(?:\$|&#36;|&dollar;)(?:<br\s*/?>)?\n?', re.IGNORECASE)
    return tag_regex.sub(' ', str(text))


# =============================================================================
# PUBLIC ROUTES
# =============================================================================

@app.before_request
def handle_sso_token():
    sso_token = request.args.get('sso_token')
    if sso_token and request.method == 'GET' and request.endpoint and not request.endpoint.startswith('static'):
        user_id = common_db.verify_user_token(sso_token)
        if user_id:
            user = common_db.get_user_by_id(user_id)
            if user:
                if user['email'].endswith('@system.local'):
                    # Admin SSO login
                    username = user['display_name'].upper()
                    session['logged_in'] = True
                    session['admin_username'] = username
                    if username == 'SUPERADMIN':
                        session['admin_role'] = 'super'
                        session['admin_permissions'] = common_db.ALL_PERMISSIONS
                    else:
                        session['admin_role'] = 'low-level'
                        stored_username, admin_data = common_db.get_admin_by_username(username)
                        session['admin_permissions'] = admin_data.get('permissions', []) if admin_data else []
                    common_db.update_last_login(username)
                else:
                    # Regular user SSO login
                    session['user_logged_in'] = True
                    session['user_id'] = user['id']
                    session['user_email'] = user['email']
                    session['user_display_name'] = user['display_name'] or user['email'].split('@')[0]
                
                # Clean URL redirect
                args = dict(request.args)
                args.pop('sso_token', None)
                try:
                    return redirect(url_for(request.endpoint, **args))
                except Exception:
                    return redirect(url_for('index'))

@app.route('/')
def index():
    """Redirect to search page (consolidated landing page)"""
    return redirect(url_for('search_page'))


@app.route('/library')
def search_page():
    """Advanced search page with Sanskrit input and tag chips"""
    collections = get_featured_collections()
    is_admin_user = is_admin_user_session()
    local_books = get_all_books(include_unpublished=is_admin_user)
    initial_query = request.args.get('q', '')
    return render_template('public/index.html', 
                         collections=collections,
                         local_books=local_books,
                         initial_query=initial_query)



@app.route('/search/local')
def search_local():
    """Search local OCR'd texts and return ALL raw matches (ungrouped, unpaginated)"""
    tags_query = request.args.get('tags_query', '').strip()
    text_query = request.args.get('text_query', '').strip()
    tags_logic = request.args.get('tags_logic', 'or').strip().lower()
    text_logic = request.args.get('text_logic', 'or').strip().lower()
    search_mode = request.args.get('search_mode', 'contains').strip().lower()
    
    # Sanskrit normalization toggle
    sanskrit_normalize = request.args.get('sanskrit_normalize', 'false').lower() == 'true'
    
    # Parse custom rules if provided
    custom_rules = None
    if sanskrit_normalize:
        custom_rules_str = request.args.get('custom_rules', '').strip()
        if custom_rules_str:
            try:
                custom_rules = json.loads(custom_rules_str)
            except json.JSONDecodeError:
                custom_rules = None
    
    
    # Max results per book (0 = unlimited, used for multi-book speed optimization)
    try:
        max_per_book = int(request.args.get('max_per_book', 0))
        max_per_book = max(0, max_per_book)
    except (ValueError, TypeError):
        max_per_book = 0
    
    tag_queries = [t.strip().lower() for t in tags_query.split(',') if t.strip()]
    text_queries = [t.strip() for t in text_query.split(',') if t.strip()]
    
    # Negative tags - exclude books matching these terms
    negative_tags_query = request.args.get('negative_tags_query', '').strip()
    neg_tag_queries = [t.strip().lower() for t in negative_tags_query.split(',') if t.strip()]
    
    if text_queries and any(len(q) < 2 for q in text_queries):
        return jsonify({'error': 'Each text search term must be at least 2 characters', 'results': []})
    
    start_time = time.time()
    all_results = []
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Get all matching folders first
    matching_folders = []
    exact_book = request.args.get('exact_book', '').strip()
    
    is_admin_user = is_admin_user_session()

    if exact_book:
        exact_path = os.path.join(upload_folder, exact_book)
        if os.path.exists(exact_path) and os.path.isdir(exact_path):
            metadata = get_metadata_from_folder(exact_path)
            if is_admin_user or metadata.get('published', True):
                matching_folders.append((exact_book, exact_path, metadata))
                tag_queries = [] # Ignore tag queries
    elif os.path.exists(upload_folder):
        for folder_name in os.listdir(upload_folder):
            folder_path = os.path.join(upload_folder, folder_name)
            if os.path.isdir(folder_path):
                metadata = get_metadata_from_folder(folder_path)
                if not is_admin_user and not metadata.get('published', True):
                    continue
                tags = metadata.get('tags', '').lower()
                book_name = folder_name.lower()
                
                def matches_query(q, t, bn, br):
                    if '>' in q:
                        parts = [p.strip() for p in q.split('>', 1)]
                        if len(parts) == 2:
                            return parts[0] in bn and (parts[1] in t or parts[1] in br)
                        return False
                    return q in t or q in bn or q in br

                def matches_sb(q, bn, sbn):
                    if '>' in q:
                        parts = [p.strip() for p in q.split('>', 1)]
                        if len(parts) == 2:
                            return parts[0] in bn and parts[1] in sbn
                        return False
                    return q in sbn

                # Check negative tags - skip if any negative query matches
                if neg_tag_queries:
                    subbooks_raw = metadata.get('subbooks_raw', '').lower()
                    if any(matches_query(nq, tags, book_name, subbooks_raw) for nq in neg_tag_queries):
                        continue
                
                tags_match = True
                allowed_ranges = []
                if tag_queries:
                    subbooks_raw = metadata.get('subbooks_raw', '').lower()
                    if tags_logic == 'and':
                        tags_match = all(matches_query(q, tags, book_name, subbooks_raw) for q in tag_queries)
                    else:
                        tags_match = any(matches_query(q, tags, book_name, subbooks_raw) for q in tag_queries)
                    
                    # If matched, calculate allowed ranges for sub-book filtering
                    if tags_match:
                        for sb in metadata.get('subbooks', []):
                            sb_name = sb.get('name', '').lower()
                            if any(matches_sb(q, book_name, sb_name) for q in tag_queries):
                                allowed_ranges.append((sb.get('start', 0), sb.get('end', 999999)))

                if tags_match:
                    matching_folders.append((folder_name, folder_path, metadata, allowed_ranges))
        
        # Sort folders by feedback: Thumbs Up > Neutral > Thumbs Down
        feedback_data = get_feedback_data()
        matching_folders.sort(key=lambda x: get_book_sort_key(x[0], feedback_data))
        
        for folder_name, folder_path, metadata, allowed_ranges in matching_folders:
            # If text query provided, search text
            if text_queries:
                # Convert generator to list and filter out pings/progress
                matches = [m for m in search_in_folder(folder_path, text_queries, text_logic, sanskrit_normalize, custom_rules, 
                                                     max_results=effective_max, search_mode=search_mode, 
                                                     allowed_ranges=allowed_ranges if allowed_ranges else None) 
                          if m is not None and not (isinstance(m, dict) and m.get('type') == 'progress')]
                
                if matches:
                    # Return ALL individual matches
                    levels_map = metadata.get('levels', {})
                    subbooks_list = metadata.get('subbooks', [])
                    for match in matches:
                        sub_book = get_subbook_for_page(match['page'], subbooks_list)
                        raw_highlight = highlight_text(match['text'], text_queries, custom_rules, search_mode=search_mode)
                        clean_highlight = clean_preview_level_tags_py(raw_highlight, levels_map)
                        result_item = {
                            'book': folder_name,
                            'page': match['page'],
                            'text': match['text'],
                            'highlighted_text': clean_highlight,
                            'archive_url': metadata.get('source', '')
                        }
                        if match.get('level_code'):
                            result_item['level_code'] = match['level_code']
                            level_disp = get_full_level_path_py(match['level_code'], levels_map)
                            if level_disp:
                                result_item['level_display'] = level_disp
                        if sub_book:
                            result_item['sub_book'] = sub_book
                        all_results.append(result_item)
            else:
                # No text query, return book info
                all_results.append({
                    'book': folder_name,
                    'page': 'N/A',
                    'text': "Full text available.",
                    'highlighted_text': "Full text available.",
                    'archive_url': metadata.get('source', '')
                })
    
    # Return all results unpaginated to let the client handle grouping and pagination
    elapsed_time = round(time.time() - start_time, 1)
    return jsonify({
        'tags_query': tags_query,
        'text_query': text_query,
        'count': len(all_results),
        'results': all_results,
        'search_time_sec': elapsed_time
    })


@app.route('/search/local/stream')
def search_local_stream():
    """Search local OCR'd texts with SSE progress streaming, returning ALL raw matches"""
    from flask import stream_with_context

    tags_query = request.args.get('tags_query', '').strip()
    text_query = request.args.get('text_query', '').strip()
    text_logic = request.args.get('text_logic', 'or').strip().lower()
    search_mode = request.args.get('search_mode', 'contains').strip().lower()
    
    # Sanskrit normalization toggle
    sanskrit_normalize = request.args.get('sanskrit_normalize', 'false').lower() == 'true'
    
    # Parse custom rules if provided
    custom_rules = None
    if sanskrit_normalize:
        custom_rules_str = request.args.get('custom_rules', '').strip()
        if custom_rules_str:
            try:
                custom_rules = json.loads(custom_rules_str)
            except json.JSONDecodeError:
                custom_rules = None


    # Max results per book (0 = unlimited, used for multi-book speed optimization)
    try:
        max_per_book = int(request.args.get('max_per_book', 0))
        max_per_book = max(0, max_per_book)
    except (ValueError, TypeError):
        max_per_book = 0

    tag_queries = [t.strip().lower() for t in tags_query.split(',') if t.strip()]
    text_queries = [t.strip() for t in text_query.split(',') if t.strip()]
    
    # Negative tags - exclude books matching these terms
    negative_tags_query = request.args.get('negative_tags_query', '').strip()
    neg_tag_queries = [t.strip().lower() for t in negative_tags_query.split(',') if t.strip()]

    def generate():
        nonlocal max_per_book
        start_time = time.time()
        if text_queries and any(len(q) < 2 for q in text_queries):
            yield f"event: result\ndata: {json.dumps({'error': 'Each text search term must be at least 2 characters', 'results': []})}\n\n"
            return

        total_count = 0
        upload_folder = app.config['UPLOAD_FOLDER']
        
        # 1. Count total folders to search and determine which match tags
        folders_to_search = []
        matching_count = 0
        active_tag_queries = list(tag_queries)
        is_admin_user = is_admin_user_session()
        exact_book = request.args.get('exact_book', '').strip()
        if exact_book:
            exact_path = os.path.join(upload_folder, exact_book)
            if os.path.exists(exact_path) and os.path.isdir(exact_path):
                metadata = get_metadata_from_folder(exact_path)
                if is_admin_user or metadata.get('published', True):
                    folders_to_search = [(exact_book, exact_path)]
                    matching_count = 1
        elif os.path.exists(upload_folder):
            for folder_name in os.listdir(upload_folder):
                folder_path = os.path.join(upload_folder, folder_name)
                if os.path.isdir(folder_path):
                    metadata = get_metadata_from_folder(folder_path)
                    if not is_admin_user and not metadata.get('published', True):
                        continue
                    folders_to_search.append((folder_name, folder_path))
                    if active_tag_queries:
                        metadata = get_metadata_from_folder(folder_path)
                        tags = metadata.get('tags', '').lower()
                        book_name_lower = folder_name.lower()
                        subbooks_raw = metadata.get('subbooks_raw', '').lower()
                        def matches_query(q, t, bn, br):
                            if '>' in q:
                                parts = [p.strip() for p in q.split('>', 1)]
                                if len(parts) == 2:
                                    return parts[0] in bn and (parts[1] in t or parts[1] in br)
                                return False
                            return q in t or q in bn or q in br

                        if any(matches_query(q, tags, book_name_lower, subbooks_raw) for q in active_tag_queries):
                            matching_count += 1
                    else:
                        matching_count += 1
            
            # Sort folders by feedback: Thumbs Up > Neutral > Thumbs Down
            feedback_data = get_feedback_data()
            folders_to_search.sort(key=lambda x: get_book_sort_key(x[0], feedback_data))

        # 2. Determine search mode
        direct_page_view = request.args.get('direct_page_view', 'false').lower() == 'true'
        # If only one book matches in group mode, keep it as group mode (unlimited)
        # Only apply 500 limit if user explicitly requested ungrouped mode
        if matching_count == 1 and not direct_page_view:
            # Single book in group mode - fetch all results (no preview limit)
            max_per_book = 0 # Fetch all matches for this single book
            # Don't set direct_page_view = True here - keeps it unlimited in group mode
            
        GLOBAL_LIMIT = 500 if direct_page_view else 0

        total_folders = len(folders_to_search)
        searched = 0
        
        for folder_name, folder_path in folders_to_search:
            metadata = get_metadata_from_folder(folder_path)
            tags = metadata.get('tags', '').lower()
            book_name_lower = folder_name.lower()

            # Check tags/book name match if provided
            tags_match = True
            subbooks_raw = metadata.get('subbooks_raw', '').lower()
            if active_tag_queries:
                def matches_query(q, t, bn, br):
                    if '>' in q:
                        parts = [p.strip() for p in q.split('>', 1)]
                        if len(parts) == 2:
                            return parts[0] in bn and (parts[1] in t or parts[1] in br)
                        return False
                    return q in t or q in bn or q in br

                tags_match = any(matches_query(q, tags, book_name_lower, subbooks_raw) for q in active_tag_queries)
            
            # Check negative tags - skip if any negative query matches
            if neg_tag_queries:
                if any(nq in tags or nq in book_name_lower or nq in subbooks_raw for nq in neg_tag_queries):
                    tags_match = False

            if tags_match:
                # Calculate allowed page ranges if sub-book filter is active
                allowed_ranges = []
                if active_tag_queries:
                    subbooks = metadata.get('subbooks', [])
                    for sb in subbooks:
                        sb_name = sb.get('name', '').lower()
                        
                        def matches_sb(q, bn, sbn):
                            if '>' in q:
                                parts = [p.strip() for p in q.split('>', 1)]
                                if len(parts) == 2:
                                    return parts[0] in bn and parts[1] in sbn
                                return False
                            return q in sbn

                        if any(matches_sb(q, book_name_lower, sb_name) for q in active_tag_queries):
                            allowed_ranges.append((sb.get('start', 0), sb.get('end', 999999)))
                
                # If text query provided, search text
                if text_queries:
                    # Process matches as they come from the generator
                    for match in search_in_folder(folder_path, text_queries, text_logic, sanskrit_normalize, custom_rules, 
                                                max_results=max_per_book, search_mode=search_mode, 
                                                allowed_ranges=allowed_ranges if allowed_ranges else None):
                        if match is None:
                            continue
                            
                        if isinstance(match, dict) and match.get('type') == 'progress':
                            # Emit a generic heartbeat to keep connection alive
                            yield ": heartbeat\n\n"
                            continue
                        
                        levels_map = metadata.get('levels', {})
                        sub_book = get_subbook_for_page(match['page'], metadata.get('subbooks', []))
                        match_data = {
                            'book': folder_name,
                            'page': match['page'],
                            'text': match['text'],
                            'highlighted_text': highlight_text(match['text'], text_queries, custom_rules, search_mode=search_mode),
                            'archive_url': metadata.get('source', ''),
                            'limited': max_per_book > 0
                        }
                        if match.get('level_code'):
                            match_data['level_code'] = match['level_code']
                            level_disp = get_full_level_path_py(match['level_code'], levels_map)
                            if level_disp:
                                match_data['level_display'] = level_disp
                        if sub_book:
                            match_data['sub_book'] = sub_book
                        
                        # Streaming: yield individual matches immediately instead of buffering per book
                        # This gives the "aggressive stop" a chance to break EVERY time a match is found
                        total_count += 1
                        yield f"event: book_result\ndata: {json.dumps({'book_results': [match_data]})}\n\n"
                        
                        if GLOBAL_LIMIT > 0 and total_count >= GLOBAL_LIMIT:
                            yield f"event: progress\ndata: {json.dumps({'type': 'limit_reached', 'limit': GLOBAL_LIMIT})}\n\n"
                            break
                else:
                    # No text query, return book info
                    book_result = {
                        'book': folder_name,
                        'page': 'N/A',
                        'text': "Full text available.",
                        'highlighted_text': "Full text available.",
                        'archive_url': metadata.get('source', '')
                    }
                    total_count += 1
                    yield f"event: book_result\ndata: {json.dumps({'book_results': [book_result]})}\n\n"

            searched += 1
            if GLOBAL_LIMIT > 0 and total_count >= GLOBAL_LIMIT:
                break

            # Emit progress event in group mode (even with 1 book) or in ungrouped with multiple books
            if not direct_page_view or (direct_page_view and total_folders > 1):
                progress_data = json.dumps({
                    'type': 'books',
                    'searched': searched,
                    'total': total_folders,
                    'book_name': folder_name
                })
                yield f"event: progress\ndata: {progress_data}\n\n"

        # Final result event signals completion (results already streamed via book_result)
        elapsed_time = round(time.time() - start_time, 1)
        result_data = json.dumps({
            'tags_query': tags_query,
            'text_query': text_query,
            'count': total_count,
            'done': True,
            'search_time_sec': elapsed_time
        })
        yield f"event: result\ndata: {result_data}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive'
    })


@app.route('/search/archive')
def search_archive():
    """Search archive.org API"""
    query = request.args.get('q', '').strip()
    collection = request.args.get('collection', '')
    language = request.args.get('language', '')
    sort = request.args.get('sort', 'downloads desc')
    page = int(request.args.get('page', 1))
    rows = int(request.args.get('rows', 20))
    
    if not query:
        return jsonify({'error': 'Please enter a search term', 'results': []})
    
    # Build advanced query
    advanced_query = query
    if collection:
        advanced_query += f' AND collection:{collection}'
    if language:
        advanced_query += f' AND language:{language}'
    
    result = search_archive_org(advanced_query, rows, page, sort)
    
    return jsonify({
        'query': query,
        'count': result.get('numFound', 0),
        'results': result.get('docs', []),
        'error': result.get('error', None)
    })


@app.route('/browse')
def browse():
    """Browse archive.org collections - filtered and paginated locally for performance"""
    collection_id = request.args.get('collection', '').strip()
    category_id = request.args.get('category', '').strip()
    sort_key = request.args.get('sort', 'downloads desc')
    page = int(request.args.get('page', 1))
    per_page = 24
    
    # Load taxonomy data
    taxonomy_data = load_taxonomy()
    nodes = taxonomy_data.get('nodes', [])
    
    # Identify target category node and tag
    target_category_node = None
    selected_tag = None
    
    if category_id and category_id != 'all':
        target_category_node = next((n for n in nodes if n.get('id') == category_id), None)
        
    if collection_id and collection_id != 'all':
        # Check if collection_id is a category ID
        matched_cat = next((n for n in nodes if n.get('id') == collection_id), None)
        if matched_cat:
            target_category_node = matched_cat
        else:
            selected_tag = collection_id
            if not target_category_node:
                for n in nodes:
                    if collection_id in n.get('tags', []):
                        target_category_node = n
                        break

    # Get current local identifiers
    current_identifiers = set(get_local_identifiers())
    
    # Check if cache needs update
    browse_cache = get_browse_cache()
    cached_identifiers = set(browse_cache.get('identifiers', []))
    if not browse_cache.get('items') or cached_identifiers != current_identifiers:
        # Update cache
        new_items = fetch_metadata_batches(list(current_identifiers))
        fetched_ids = {str(item.get('identifier', '')).lower(): item for item in new_items}
        
        all_items = []
        local_books = get_all_books(include_unpublished=is_admin_user_session())
        
        for b in local_books:
            folder_name = b['name']
            idx = None
            source_url = b.get('archive_url', '')
            if source_url:
                parsed = urllib.parse.urlparse(source_url)
                parts = parsed.path.strip('/').split('/')
                if 'details' in parts:
                    idx_pos = parts.index('details')
                    if idx_pos + 1 < len(parts):
                        idx = parts[idx_pos + 1]
                if not idx and parts:
                    idx = parts[-1]
            if not idx:
                idx = folder_name
                
            tags_str = b.get('tags', '')
            tags = [t.strip() for t in tags_str.split(',') if t.strip()]
            
            item = fetched_ids.get(idx.lower())
            if item:
                item_copy = dict(item)
                if 'subject' not in item_copy:
                    item_copy['subject'] = []
                elif not isinstance(item_copy['subject'], list):
                    item_copy['subject'] = [item_copy['subject']]
                item_copy['subject'].extend(tags)
                
                # Always use the local folder name so sub-volumes show their specific name
                item_copy['title'] = folder_name
                    
                item_copy['folder_name'] = folder_name
                item_copy['has_archive_link'] = True
                all_items.append(item_copy)
            else:
                all_items.append({
                    'identifier': '',  # Empty identifier means no archive link
                    'folder_name': folder_name,
                    'title': folder_name,
                    'creator': '',
                    'downloads': 0,
                    'subject': tags,
                    'collection': [],
                    'has_archive_link': False
                })
        
        browse_cache = {
            'items': all_items,
            'identifiers': list(current_identifiers),
            'last_updated': time.time()
        }
        save_browse_cache(browse_cache)
    
    # 1. Start with all cached items
    items = list(browse_cache.get('items', []))
    is_admin_user = is_admin_user_session()
    if not is_admin_user:
        items = [
            item for item in items
            if get_metadata_from_folder(os.path.join(app.config['UPLOAD_FOLDER'], item['folder_name'])).get('published', True)
        ]
    
    def match_item_tag(item, tag_query):
        if not tag_query:
            return True
        t_lower = tag_query.lower()
        
        # Check subject / tags list
        subjects = item.get('subject', [])
        if isinstance(subjects, list):
            for s in subjects:
                if t_lower in str(s).lower():
                    return True
        elif t_lower in str(subjects).lower():
            return True
            
        # Check title as fallback
        title = str(item.get('title', '')).lower()
        if t_lower in title:
            return True
            
        return False

    local_books_meta = {}
    try:
        local_books_meta = {b['name']: b for b in get_all_books(include_unpublished=True)}
    except Exception:
        pass

    # 2. Filter by selected tag OR category node OR community
    if collection_id == 'community':
        items = [item for item in items if local_books_meta.get(item.get('folder_name', ''), {}).get('is_community')]
    elif selected_tag:
        items = [item for item in items if match_item_tag(item, selected_tag)]
    elif target_category_node:
        cat_tags = target_category_node.get('tags', [])
        cat_id = target_category_node.get('id', '')
        items = [
            item for item in items
            if any(match_item_tag(item, t) for t in cat_tags) or match_item_tag(item, cat_id)
        ]

    # 3. Sort items
    if sort_key == 'downloads desc':
        items.sort(key=lambda x: int(x.get('downloads', 0)), reverse=True)
    elif sort_key == 'week desc':
        items.sort(key=lambda x: int(x.get('downloads', 0)), reverse=True)
    elif sort_key == 'publicdate desc':
        items.sort(key=lambda x: x.get('date', '') or x.get('publicdate', ''), reverse=True)
    elif sort_key == 'titleSorter asc':
        items.sort(key=lambda x: x.get('title', '').lower())
        
    # 4. Paginate
    total = len(items)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_items = items[start_idx:end_idx]
    
    from ai_search import get_embedded_book_names
    from db import common_db
    embedded_books = set(get_embedded_book_names() or [])
    
    user_id = session.get('user_id')
    user_reqs = {}
    if user_id:
        try:
            user_reqs = {r['book_name']: r['status'] for r in common_db.get_user_vector_requests(user_id)}
        except Exception:
            pass
            
    for item in paginated_items:
        folder_name = item.get('folder_name', '')
        b_info = local_books_meta.get(folder_name, {})
        item['has_vector'] = folder_name in embedded_books
        item['vector_status'] = user_reqs.get(folder_name, 'none')
        item['proofread_pct'] = b_info.get('proofread_pct', 0)
        item['is_community'] = b_info.get('is_community', False)
        item['verification'] = b_info.get('verification', 'verified')
        item['contributor'] = b_info.get('contributor', '')
        
    cur_cat = target_category_node['id'] if target_category_node else (category_id or 'all')
    cur_col = selected_tag if selected_tag else (collection_id or 'all')

    return render_template('public/browse.html',
                         collections=get_featured_collections(),
                         current_collection=cur_col,
                         current_category=cur_cat,
                         items=paginated_items,
                         total=total,
                         page=page,
                         sort=sort_key)


@app.route('/item/<identifier>')
def view_item(identifier):
    """View archive.org item details"""
    result = get_archive_item_metadata(identifier)
    
    if not result['success']:
        return render_template('public/error.html', error=result.get('error', 'Unknown error'))
    
    return render_template('public/item.html', item=result['data'])


# =============================================================================
# AUTOCOMPLETE API
# =============================================================================

@app.route('/api/suggestions')
def api_suggestions():
    """Return tag and book name suggestions for autocomplete, optionally filtered by context"""
    query = request.args.get('q', '').strip().lower()
    context_str = request.args.get('context', '').strip().lower()
    
    # If no context, we need at least 2 chars for query
    # If context is present, we can show suggestions for empty query (related terms)
    if not context_str and len(query) < 2:
        return jsonify({'suggestions': []})
    
    # Parse context terms
    context_terms = [t.strip() for t in re.split(r'[\s,]+', context_str) if t.strip()]
    
    suggestions = []
    seen_books = set()
    seen_tags = set()
    seen_subbooks = set()
    upload_folder = app.config['UPLOAD_FOLDER']
    
    is_admin_user = is_admin_user_session()
    if os.path.exists(upload_folder):
        for folder_name in os.listdir(upload_folder):
            folder_path = os.path.join(upload_folder, folder_name)
            if not os.path.isdir(folder_path):
                continue
            
            metadata = get_metadata_from_folder(folder_path)
            if not is_admin_user and not metadata.get('published', True):
                continue
            book_name_lower = folder_name.lower()
            tags_str = metadata.get('tags', '').lower()
            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
            subbooks_list = [sb.get('name', '').lower() for sb in metadata.get('subbooks', []) if sb.get('name')]
            
            # Check if this book matches ALL context terms
            if context_terms:
                matches_context = True
                for term in context_terms:
                    # Check book name
                    if term in book_name_lower:
                        continue
                    # Check tags
                    if any(term in t for t in tags_list):
                        continue
                    # Check subbooks
                    if any(term in sb for sb in subbooks_list):
                        continue
                    
                    # If none matched, the book doesn't fit the context
                    matches_context = False
                    break
                
                if not matches_context:
                    continue

            # If we're here, the book matches the context (or there is no context)
            # Now extract suggestions from this book
            
            # 1. Book name suggestion
            if book_name_lower not in seen_books:
                if query in book_name_lower:
                    suggestions.append({'type': 'book', 'value': folder_name})
                    seen_books.add(book_name_lower)
            
            # 2. Tag suggestions
            for tag in tags_list:
                tag_lower = tag.lower()
                if tag_lower in seen_tags:
                    continue
                if query in tag_lower:
                    # Re-extract the original casing if possible, or just use the lower if needed.
                    # Metadata get_metadata_from_folder already gives us original casing.
                    # Wait, tags_list came from tags_str.split(',') where tags_str was lowered.
                    # I should use the original casing from metadata.
                    orig_tags = metadata.get('tags', '').split(',')
                    for orig_tag in orig_tags:
                        orig_tag = orig_tag.strip()
                        if orig_tag.lower() == tag_lower:
                            suggestions.append({'type': 'tag', 'value': orig_tag})
                            break
                    seen_tags.add(tag_lower)
            
            # 3. Sub-book suggestions
            for sb in metadata.get('subbooks', []):
                sb_name = sb.get('name', '')
                if not sb_name: continue
                sb_name_lower = sb_name.lower()
                # Create a unique key for subbook suggestions to avoid duplicates across books
                # Wait, actually sub-books should probably stay linked to their parent in suggestions
                sugg_value = f"{folder_name} > {sb_name}"
                sugg_key = sugg_value.lower()
                
                if sugg_key in seen_subbooks:
                    continue
                    
                if query in sb_name_lower:
                    suggestions.append({'type': 'book', 'value': sugg_value})
                    seen_subbooks.add(sugg_key)
    
    # Sort: exact prefix first, then substring
    def sort_key(s):
        val = s['value'].lower()
        # For "Book > Sub-book", check if the sub-book name starts with query
        if ' > ' in val:
            parts = val.split(' > ')
            if len(parts) == 2 and parts[1].startswith(query):
                return (0, val)
        
        if val.startswith(query):
            return (0, val)
        elif query in val:
            return (1, val)
        else:
            return (2, val)
    
    suggestions.sort(key=sort_key)
    
    return jsonify({'suggestions': suggestions[:8]})


# =============================================================================
# BOOK SEARCH (SEARCH PAGE) - Name/tag matching
# =============================================================================

@app.route('/search/books')
def search_books():
    """Search books by name and tags"""
    query = ""
    try:
        query = request.args.get('q', '').strip()
        logic = request.args.get('logic', 'or').strip().lower()
        
        if not query or len(query) < 1:
            return jsonify({'error': 'Please enter a search term', 'results': []})
        
        query_lower = query.lower()
        # For multi-word queries, we want to ensure most words are somewhat relevant
        # Use regex to split by whitespace or commas
        query_terms = [t.strip().lower() for t in re.split(r'[\s,]+', query) if len(t.strip()) > 1]
        
        results = []
        upload_folder = app.config['UPLOAD_FOLDER']
        
        if not os.path.exists(upload_folder):
            return jsonify({'results': [], 'count': 0})
        
        is_admin_user = is_admin_user_session()
        
        from ai_search import get_embedded_book_names
        from db import common_db
        embedded_books = set(get_embedded_book_names() or [])
        
        user_id = session.get('user_id')
        user_reqs = {}
        if user_id:
            try:
                user_reqs = {r['book_name']: r['status'] for r in common_db.get_user_vector_requests(user_id)}
            except Exception:
                pass

        for folder_name in os.listdir(upload_folder):
            folder_path = os.path.join(upload_folder, folder_name)
            if not os.path.isdir(folder_path):
                continue
            
            metadata = get_metadata_from_folder(folder_path)
            if not is_admin_user and not metadata.get('published', True):
                continue
                
            book_name_lower = folder_name.lower()
            tags_str = metadata.get('tags', '').lower()
            subbooks_str = metadata.get('subbooks_raw', '').lower()
            
            def matches_query(q, bn, ts, ss):
                if '>' in q:
                    parts = [p.strip() for p in q.split('>', 1)]
                    if len(parts) == 2:
                        return parts[0] in bn and (parts[1] in ts or parts[1] in ss)
                    return False
                return q in bn or q in ts or q in ss

            score = 0
            # If the entire raw query (including commas) matches as a substring, that's a very strong match
            if matches_query(query_lower, book_name_lower, tags_str, subbooks_str):
                score += 100
            
            # For multi-term queries, calculate score based on individual terms
            term_matches = 0
            if len(query_terms) > 0:
                for term in query_terms:
                    if matches_query(term, book_name_lower, tags_str, subbooks_str):
                        term_matches += 1
                        score += 50 # Significant score for each term match
                    else:
                        # Fallback: check if term exists as a distinct word in folder name or tags
                        searchable = (folder_name + " " + tags_str + " " + subbooks_str).lower()
                        words = re.split(r'[\s,_\-]+', searchable)
                        if term in words:
                            score += 30
                            term_matches += 1
                
                if logic == 'and':
                    if term_matches < len(query_terms):
                        continue
                else: # 'or' logic
                    if term_matches == 0:
                        continue
                        
                # Minimal threshold for multi-term matches
                if score < 30:
                    continue
            else:
                # Single word search (should have been caught by query_terms but just in case)
                if score < 40:
                    continue

            # Get tag list for display metadata (not displayed in UI but returned)
            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
            
            # Extract archive.org identifier for cover image and download
            archive_url = metadata.get('source', '')
            identifier = ''
            if archive_url:
                parsed_url = urllib.parse.urlparse(archive_url)
                path_parts = parsed_url.path.strip('/').split('/')
                if 'details' in path_parts:
                    idx_pos = path_parts.index('details')
                    if idx_pos + 1 < len(path_parts):
                        identifier = path_parts[idx_pos + 1]
                elif path_parts:
                    identifier = path_parts[-1]
            
            pct = extract_proofreading_percentage(metadata.get('notes', ''))
            results.append({
                'book': folder_name,
                'tags': tags_list,
                'archive_url': archive_url,
                'identifier': identifier,
                'score': score,
                'proofread_pct': pct,
                'has_vector': folder_name in embedded_books,
                'vector_status': user_reqs.get(folder_name, 'none')
            })
        
        # Sort by relevance score
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Remove score from response
        for r in results:
            del r['score']
        
        return jsonify({
            'results': results,
            'count': len(results),
            'query': query
        })
    except Exception as e:
        print(f"Search Books Error: {e}")
        return jsonify({
            'results': [],
            'count': 0,
            'query': query,
            'error': str(e)
        }), 500




# =============================================================================
# EMBEDDED READER
# =============================================================================

def get_book_page_ocr(book_name, page):
    """Helper to extract OCR text and total pages for a book/page"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    ocr_text = ""
    total_pages = 0
    is_pageless = False
    if os.path.exists(folder_path):
        txt_files = [f for f in sorted(os.listdir(folder_path)) 
                    if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
        
        full_text = ""
        for txt_file in txt_files:
            try:
                full_text += get_cached_file_content(os.path.join(folder_path, txt_file)) + "\n"
            except:
                pass
        
        if full_text:
            # Get total pages
            all_pages = re.findall(r'\{\[\((\d+)\)\]\}', full_text)
            if all_pages:
                total_pages = max([int(p) for p in all_pages])
                # Get specific page
                page_marker = f'{{[({page})]}}'
                start_match = re.search(re.escape(page_marker), full_text)
                if start_match:
                    start_pos = start_match.end()
                    next_marker_match = re.search(r'\{\[\(\d+\)\]\}', full_text[start_pos:])
                    if next_marker_match:
                        ocr_text = full_text[start_pos : start_pos + next_marker_match.start()].strip()
                    else:
                        ocr_text = full_text[start_pos:].strip()
            else:
                # Text-only file without explicit {[ (N) ]} page markers -> smart level-boundary chunking
                is_pageless = True
                chunks = split_text_into_smart_chunks(full_text.strip(), target_chars=8000)
                total_pages = len(chunks)
                if 1 <= page <= total_pages:
                    ocr_text = chunks[page - 1]
                else:
                    ocr_text = chunks[0] if chunks else full_text.strip()
    return ocr_text, total_pages, is_pageless

@app.route('/api/ocr/<book_name>/<int:page>')
def api_get_ocr(book_name, page):
    """API to get OCR text for a page (used for previews)"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    if os.path.exists(folder_path):
        is_admin_user = is_admin_user_session()
        metadata = get_metadata_from_folder(folder_path)
        if not is_admin_user and not metadata.get('published', True):
            return jsonify({'error': 'Permission denied: This book is currently in draft status'}), 403

    try:
        ocr_text, total_pages, is_pageless = get_book_page_ocr(book_name, page)
        
        q = request.args.get('q', '').strip()
        sanskrit_normalize = request.args.get('sanskrit_normalize', 'false').lower() == 'true'
        search_mode = request.args.get('search_mode', 'contains').strip().lower()
        
        # Parse custom rules if provided
        custom_rules = None
        if sanskrit_normalize:
            custom_rules_str = request.args.get('custom_rules', '').strip()
            if custom_rules_str:
                try:
                    custom_rules = json.loads(custom_rules_str)
                except:
                    pass

        highlighted_ocr = ocr_text
        if q and ocr_text:
            # Re-use highlighting logic from search
            import html
            highlighted_ocr = html.escape(ocr_text)
            terms = [t.strip() for t in q.split(',') if t.strip()]
            highlighted_ocr = highlight_text(highlighted_ocr, terms, custom_rules=custom_rules, search_mode=search_mode)

        folder_meta_api = get_metadata_from_folder(folder_path) if os.path.exists(folder_path) else {}
        levels_map_api = folder_meta_api.get('levels', {})
        formatted_ocr_text_api = render_structured_ocr_html(highlighted_ocr, levels_map_api) if highlighted_ocr else ""

        # Check if the requesting client has a pending notepad edit on this page
        ignore_pending = request.args.get('ignore_pending') in ('1', 'true', 'True')
        client_token = (request.headers.get('X-Client-Token') or request.args.get('client_token', '') or request.cookies.get('sdl_client_token', '') or (f"user_{session['user_id']}" if session.get('user_id') else '')).strip()
        has_pending_edit = False
        edit_id = None
        contributor_name = ''
        if client_token and not ignore_pending:
            try:
                from db.common_db import get_user_pending_edit
                pending = get_user_pending_edit(book_name, page, client_token)
                if pending:
                    has_pending_edit = True
                    edit_id = pending.get('edit_id')
                    contributor_name = pending.get('contributor_name', '')
                    ocr_text = pending.get('edited_text', '')
                    highlighted_ocr = ocr_text
                    if q and ocr_text:
                        import html
                        highlighted_ocr = html.escape(ocr_text)
                        terms = [t.strip() for t in q.split(',') if t.strip()]
                        highlighted_ocr = highlight_text(highlighted_ocr, terms, custom_rules=custom_rules, search_mode=search_mode)
                    formatted_ocr_text_api = render_structured_ocr_html(highlighted_ocr, levels_map_api) if highlighted_ocr else ""
            except Exception as e_pending:
                app.logger.warning(f"Error checking pending edit for {book_name} p{page}: {e_pending}")

        return jsonify({
            'success': True,
            'ocr_text': highlighted_ocr,
            'formatted_ocr_text': formatted_ocr_text_api,
            'raw_ocr_text': ocr_text,
            'total_pages': total_pages,
            'is_pageless': is_pageless,
            'page': page,
            'book_name': book_name,
            'has_user_pending_edit': has_pending_edit,
            'pending_edit_id': edit_id,
            'contributor_name': contributor_name
        })
    except Exception as e:
        app.logger.error(f"OCR API Error: {e}")
        return jsonify({'error': str(e), 'ocr_text': '', 'total_pages': 0, 'is_pageless': False}), 500


def get_all_book_pages_ocr(book_name):
    """Helper to extract all pages OCR dict map {page_num: ocr_text} and metadata for a book"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    pages_map = {}
    total_pages = 0
    is_pageless = False
    if os.path.exists(folder_path):
        txt_files = [f for f in sorted(os.listdir(folder_path)) 
                    if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
        
        full_text = ""
        for txt_file in txt_files:
            try:
                full_text += get_cached_file_content(os.path.join(folder_path, txt_file)) + "\n"
            except:
                pass
        
        if full_text:
            all_pages_matches = list(re.finditer(r'\{\[\((\d+)\)\]\}', full_text))
            if all_pages_matches:
                for idx, match in enumerate(all_pages_matches):
                    try:
                        p_num = int(match.group(1))
                        start_pos = match.end()
                        if idx + 1 < len(all_pages_matches):
                            end_pos = all_pages_matches[idx + 1].start()
                            pages_map[p_num] = full_text[start_pos:end_pos].strip()
                        else:
                            pages_map[p_num] = full_text[start_pos:].strip()
                    except ValueError:
                        pass
                total_pages = max(pages_map.keys()) if pages_map else 0
            else:
                is_pageless = True
                chunks = split_text_into_smart_chunks(full_text.strip(), target_chars=8000)
                total_pages = len(chunks)
                for idx, chunk in enumerate(chunks):
                    pages_map[idx + 1] = chunk
    return pages_map, total_pages, is_pageless


@app.route('/api/ocr/<book_name>/all')
def api_get_all_ocr(book_name):
    """API to get all OCR pages text for a book for continuous background preloading"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    if os.path.exists(folder_path):
        is_admin_user = is_admin_user_session()
        metadata = get_metadata_from_folder(folder_path)
        if not is_admin_user and not metadata.get('published', True):
            return jsonify({'error': 'Permission denied: This book is currently in draft status'}), 403

    try:
        pages_map, total_pages, is_pageless = get_all_book_pages_ocr(book_name)
        pages_json = {str(k): v for k, v in pages_map.items()}

        client_token = (request.headers.get('X-Client-Token') or request.args.get('client_token', '') or request.cookies.get('sdl_client_token', '') or (f"user_{session['user_id']}" if session.get('user_id') else '')).strip()
        user_pending_pages = []
        if client_token:
            try:
                from db.common_db import get_db
                conn = get_db()
                edits = conn.execute(
                    "SELECT page_number, edited_text FROM community_book_edits WHERE book_name = ? AND client_token = ? AND status = 'pending'",
                    (book_name, client_token)
                ).fetchall()
                conn.close()
                for edit in edits:
                    p_num = edit['page_number']
                    pages_json[str(p_num)] = edit['edited_text']
                    user_pending_pages.append(p_num)
            except Exception as e_edits:
                app.logger.warning(f"Error merging pending edits in all OCR: {e_edits}")
        
        return jsonify({
            'success': True,
            'pages': pages_json,
            'total_pages': total_pages,
            'is_pageless': is_pageless,
            'book_name': book_name,
            'user_pending_pages': user_pending_pages
        })
    except Exception as e:
        app.logger.error(f"OCR All API Error: {e}")
        return jsonify({'error': str(e), 'pages': {}, 'total_pages': 0, 'is_pageless': False}), 500

@app.route('/reader/<book_name>')
@app.route('/reader/<book_name>/<int:page>')
def reader(book_name, page=1):
    """Embedded archive.org BookReader for a local book or archive.org item"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    identifier = ''
    filename = ''
    subbooks = []
    
    if os.path.exists(folder_path):
        metadata = get_metadata_from_folder(folder_path, bypass_cache=True)
        is_admin_user = is_admin_user_session()
        if not is_admin_user and not metadata.get('published', True):
            return render_template('admin/forbidden.html', permission='PUBLISHED_BOOK_ONLY'), 403
            
        archive_url = metadata.get('source', '')
        subbooks = metadata.get('subbooks', [])
        
        if archive_url:
            parsed_url = urllib.parse.urlparse(archive_url)
            
            # Case 1: Filename in query parameter (?file=...)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            if 'file' in query_params:
                filename = query_params['file'][0]
                
            # Case 2: Extract identifier from path
            # URLs usually look like: https://archive.org/details/IDENTIFIER/...
            path_parts = parsed_url.path.rstrip('/').split('/')
            for i, part in enumerate(path_parts):
                if part == 'details' and i + 1 < len(path_parts):
                    identifier = path_parts[i + 1]
                    # Check if there's a filename after the identifier in the path
                    if not filename and i + 2 < len(path_parts):
                        filename = path_parts[i + 2]
                    break
            
            # Fallback for identifier if /details/ is missing
            if not identifier and path_parts:
                identifier = path_parts[-1]
        else:
            # Explicitly set empty if no source URL
            identifier = ''
    else:
        # Not a local folder — treat book_name as the archive.org identifier directly
        identifier = book_name

    # Load OCR text using helper
    ocr_text, total_pages, is_pageless = get_book_page_ocr(book_name, page)
    
    is_search_mode = request.args.get('source') == 'search'
    q = request.args.get('q', '').strip()
    
    if is_search_mode and q and ocr_text:
        # Escape HTML characters to prevent XSS before highlighting
        import html
        ocr_text = html.escape(ocr_text)
        
        # Highlight searched terms (split by comma if multiple)
        terms = [t.strip() for t in q.split(',') if t.strip()]
        ocr_text = highlight_text(ocr_text, terms)

    # Compute both defined subbooks and non-mentioned ranges
    sections = get_book_sections(subbooks, total_pages)

    pct = 0
    if os.path.exists(folder_path):
        metadata = get_metadata_from_folder(folder_path)
        notes_str = metadata.get('notes', '')
        pct = extract_proofreading_percentage(notes_str)
        
    from ai_search import get_embedded_book_names
    from db import common_db
    has_vector = book_name in set(get_embedded_book_names() or [])
    
    user_id = session.get('user_id')
    vector_status = 'none'
    if user_id and has_vector:
        try:
            req = common_db.get_vector_request(user_id, book_name)
            if req:
                vector_status = req['status']
        except Exception:
            pass

    raw_rt_settings = common_db.get_system_setting('universal_rich_text_settings')
    rich_text_settings = {}
    if raw_rt_settings:
        try:
            rich_text_settings = json.loads(raw_rt_settings)
        except:
            pass
            
    folder_meta = get_metadata_from_folder(folder_path) if os.path.exists(folder_path) else {}
    levels_map = folder_meta.get('levels', {})

    # Check if client has a pending edit on this page for instant SSR display
    client_token = (request.cookies.get('sdl_client_token') or request.args.get('client_token', '') or (f"user_{session['user_id']}" if session.get('user_id') else '')).strip()
    has_user_pending_edit = False
    if client_token:
        try:
            from db.common_db import get_user_pending_edit
            pending = get_user_pending_edit(book_name, page, client_token)
            if pending and pending.get('edited_text'):
                has_user_pending_edit = True
                ocr_text = pending['edited_text']
        except Exception:
            pass

    formatted_ocr_text = render_structured_ocr_html(ocr_text, levels_map) if ocr_text else ""

    return render_template('public/reader.html',
                         book_name=book_name,
                         page=page,
                         total_pages=total_pages,
                         is_pageless=is_pageless,
                         identifier=identifier,
                         filename=filename,
                         ocr_text=ocr_text,
                         formatted_ocr_text=formatted_ocr_text,
                         is_search_mode=is_search_mode,
                         sections=sections,
                         proofread_pct=pct,
                         has_vector=has_vector,
                         vector_status=vector_status,
                         levels=levels_map,
                         levels_raw=folder_meta.get('levels_raw', ''),
                         rich_text_settings=rich_text_settings,
                         is_community=folder_meta.get('is_community', False),
                         has_user_pending_edit=has_user_pending_edit)


def split_text_into_smart_chunks(full_text, target_chars=8000):
    """Splits full text into adaptive page chunks preferably at $level$ boundaries to preserve collapsible cards."""
    if not full_text:
        return []
    
    level_split_pos = [m.start() for m in re.finditer(r'(?:\$|&#36;|&dollar;)\s*\d+(?:\.[^\$\r\n]+)*\s*(?:\$|&#36;|&dollar;)', full_text)]
    if level_split_pos and len(level_split_pos) > 1:
        chunks = []
        curr_start = 0
        for i in range(1, len(level_split_pos)):
            pos = level_split_pos[i]
            if pos - curr_start >= target_chars:
                chunks.append(full_text[curr_start:pos].strip())
                curr_start = pos
        if curr_start < len(full_text):
            chunks.append(full_text[curr_start:].strip())
        if chunks:
            return [c for c in chunks if c]
            
    return split_text_into_pages(full_text.strip(), target_chars=target_chars)


def split_text_into_pages(text, target_chars=2000):
    """
    Divide text into approximate pages, preferring newlines or spaces.
    Splits at the nearest character BEFORE the target_chars limit to avoid oversized pages.
    """
    pages = []
    start = 0
    total = len(text)
    
    while start < total:
        # If remaining text is small enough, just take it as one page
        if total - start <= target_chars * 1.1:
            pages.append(text[start:].strip())
            break
            
        target_end = start + target_chars
        # Look back for best break point (limit lookback to 50% of target)
        lookback_limit = int(target_chars * 0.5)
        search_start = max(start, target_end - lookback_limit)
        
        # 1. Try Paragraph break (double newline) - best for keeping verses together
        para_pos = text.rfind('\n\n', search_start, target_end)
        if para_pos != -1:
            end = para_pos + 2
        else:
            # 2. Try Newline
            newline_pos = text.rfind('\n', search_start, target_end)
            if newline_pos != -1:
                end = newline_pos + 1
            else:
                # 3. Try Space
                space_pos = text.rfind(' ', search_start, target_end)
                if space_pos != -1:
                    end = space_pos + 1
                else:
                    # 4. Hard cut
                    end = target_end
                
        pages.append(text[start:end].strip())
        start = end
        
    return pages


# =============================================================================
# ADMIN ROUTES
# =============================================================================

# =============================================================================
# UNIFIED AUTH & USER ROUTES
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def unified_login():
    """Unified login page for users and admins"""
    if request.method == 'GET':
        return render_template('public/login.html')

    if request.method == 'POST':
        username_or_email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # 1. Check admins.json first (includes 'SUPERADMIN' and low-level admins)
        stored_username, admin_data = common_db.get_admin_by_username(username_or_email)
        
        if stored_username and common_db.verify_password(password, admin_data['password_hash']):
            session['logged_in'] = True
            session['admin_username'] = stored_username.upper()
            
            if stored_username.upper() == 'SUPERADMIN':
                session['admin_role'] = 'super'
                session['admin_permissions'] = common_db.ALL_PERMISSIONS
            else:
                session['admin_role'] = 'low-level'
                session['admin_permissions'] = admin_data.get('permissions', [])
            
            common_db.update_last_login(stored_username)
            flash(f'Admin login successful! Welcome, {stored_username.upper()}', 'success')
            return redirect(url_for('admin_dashboard'))
            
        # 2. Check SQLite users table
        user = common_db.verify_user(username_or_email, password)
        if user:
            session['user_logged_in'] = True
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_display_name'] = user['display_name'] or user['email'].split('@')[0]
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
            
        # 3. Fail
        flash('Invalid email/username or password', 'error')
        
    return render_template('public/login.html')


@app.route('/api/auth/google/config', methods=['GET'])
def google_auth_config():
    """Endpoint to return the configured Google Client ID"""
    client_id = getattr(config, 'GOOGLE_CLIENT_ID', '')
    is_enabled = bool(client_id and 'placeholder' not in client_id and 'YOUR_GOOGLE_CLIENT_ID' not in client_id)
    return jsonify({
        'google_client_id': client_id,
        'enabled': is_enabled
    })


@app.route('/api/auth/google', methods=['POST'])
def google_auth_signin():
    """Endpoint to verify Google ID token and log user in"""
    data = request.get_json() or {}
    token = data.get('credential')
    if not token:
        return jsonify({'success': False, 'error': 'No Google credential token received'}), 400

    client_id = getattr(config, 'GOOGLE_CLIENT_ID', '')
    if not client_id:
        return jsonify({'success': False, 'error': 'Google Sign-in is not configured on this server'}), 500

    idinfo = None
    
    # 1. Try local verification using google-auth library
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except Exception as e:
        # 2. Try verifying via Google's tokeninfo API as a fallback (robust against clock skew or local dep issues)
        try:
            import urllib.request
            import json
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
            with urllib.request.urlopen(url, timeout=10) as response:
                idinfo = json.loads(response.read().decode('utf-8'))
            if idinfo.get('aud') != client_id:
                raise ValueError("Audience mismatch")
        except Exception as e2:
            return jsonify({'success': False, 'error': f'Failed to verify Google token: {str(e2)}'}), 400

    if not idinfo:
        return jsonify({'success': False, 'error': 'Invalid Google token'}), 400

    email = idinfo.get('email')
    display_name = idinfo.get('name')
    if not email:
        return jsonify({'success': False, 'error': 'Email not provided by Google'}), 400

    # Retrieve or create user in SQLite database
    user = common_db.get_or_create_google_user(email, display_name)
    if not user:
        return jsonify({'success': False, 'error': 'Failed to create or retrieve user account'}), 500

    # Generate user token for client-side API calls/syncing
    user_token = common_db.create_user_token(user['id'])

    # Set up session
    session['user_logged_in'] = True
    session['user_id'] = user['id']
    session['user_email'] = user['email']
    session['user_display_name'] = user['display_name'] or user['email'].split('@')[0]

    # Flash message
    flash(f"Welcome back, {session['user_display_name']}! Logged in with Google.", 'success')

    # Return redirect and token
    ref = request.args.get('redirect') or request.args.get('next') or url_for('index')
    return jsonify({
        'success': True,
        'redirect': ref,
        'token': user_token,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'display_name': user['display_name']
        }
    })






@app.route('/register', methods=['GET', 'POST'])
def user_register():
    """Register page for public users"""
    if request.method == 'GET':
        import urllib.parse
        ref = request.args.get('redirect') or request.args.get('next')
        if ref:
            return redirect(f'/register?redirect={urllib.parse.quote(ref)}')
        return redirect('/register')

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        mobile = request.form.get('mobile', '').strip()
        display_name = request.form.get('display_name', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not email or not mobile or not password:
            flash('All mandatory fields are required (Email, Mobile, Password)', 'error')
            return render_template('public/register.html', email=email, mobile=mobile, display_name=display_name)
            
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('public/register.html', email=email, mobile=mobile, display_name=display_name)
            
        success, message, user_id = common_db.create_user(email, password, mobile, display_name)
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('unified_login'))
        else:
            flash(message, 'error')
            return render_template('public/register.html', email=email, mobile=mobile, display_name=display_name)
            
    return render_template('public/register.html')


@app.route('/logout', methods=['GET', 'POST'])
def user_logout():
    """Clears all session data (admin + user) and redirects to homepage."""
    import urllib.parse
    ref = request.args.get('redirect') or request.args.get('next')
    
    # Purge active API tokens from database
    user_id = None
    if session.get('user_id'):
        user_id = session.get('user_id')
    elif session.get('admin_username'):
        admin_username = session.get('admin_username').upper()
        admin_email = f"{admin_username.lower()}@system.local"
        conn = common_db.get_db()
        row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
        conn.close()
        if row:
            user_id = row['id']
            
    if user_id:
        try:
            conn = common_db.get_db()
            conn.execute('DELETE FROM user_tokens WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error purging tokens during main site logout: {e}")

    # 2. Clear Flask session
    session.clear()
    
    import json
    from flask import make_response
    redir_target = ref or '/'

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Logging out...</title>
    <script>
        (function() {{
            try {{
                localStorage.removeItem('user_token');
                localStorage.removeItem('user_profile');
                sessionStorage.clear();
            }} catch(e) {{}}
            window.location.href = {json.dumps(redir_target)};
        }})();
    </script>
</head>
<body>
    <p style="font-family: sans-serif; text-align: center; margin-top: 50px; color: #666;">Logging out...</p>
</body>
</html>"""

    resp = make_response(html_content)
    resp.set_cookie('session', '', expires=0, max_age=0, path='/', httponly=True, samesite='Lax')
    return resp


@app.route('/admin/login')
def admin_login():
    """Redirect old admin login to the unified login page"""
    return redirect(url_for('unified_login'))
@app.route('/admin/logout')
def admin_logout():
    """Redirect old admin logout to the unified logout"""
    return user_logout()


@app.route('/user/sdl-profile')
@app.route('/user/profile')
@user_login_required
def user_sdl_profile():
    """User profile and dashboard — Library focused"""
    user = common_db.get_user_by_id(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('unified_login'))
    return render_template('public/sdl_profile.html', user=user)




@app.route('/user/quiz-profile')
@user_login_required
def user_quiz_profile():
    """User profile — Quiz focused dashboard with stats and history"""
    user = common_db.get_user_by_id(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('unified_login'))
    return render_template('public/quiz_profile.html', user=user)


@app.route('/api/auth/profile', methods=['GET'])
@app.route('/api/auth/profile/', methods=['GET'])
def api_auth_profile():
    """Retrieve logged-in user profile details (JSON)"""
    if 'user_logged_in' not in session or not session.get('user_id'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    user = common_db.get_user_by_id(session['user_id'])
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
        
    return jsonify({
        'success': True,
        'id': user['id'],
        'email': user['email'],
        'mobile': user['mobile'],
        'display_name': user['display_name'],
        'user': {
            'id': user['id'],
            'email': user['email'],
            'mobile': user['mobile'],
            'display_name': user['display_name']
        }
    })


@app.route('/api/user/profile/update', methods=['POST'])
@user_login_required
def update_profile_avatar():
    data = request.get_json() or {}
    avatar_idx = data.get('avatar_idx')
    
    if avatar_idx is None:
        return jsonify({'success': False, 'message': 'Avatar index is required'}), 400
        
    try:
        avatar_idx = int(avatar_idx)
        if not (0 <= avatar_idx < len(AVATARS)):
            return jsonify({'success': False, 'message': 'Invalid avatar index'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid avatar index'}), 400
        
    # Update db: avatar index
    common_db.update_user_avatar(session['user_id'], avatar_idx)
    # Clear profile pic since we chose an avatar
    common_db.update_user_profile_pic(session['user_id'], None)
    
    # Update session variables
    session['user_avatar_idx'] = avatar_idx
    session['user_profile_pic'] = None
    
    return jsonify({'success': True, 'message': 'Avatar updated successfully'})


@app.route('/api/user/profile/upload-pic', methods=['POST'])
@user_login_required
def upload_profile_pic():
    if 'profile_pic' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'}), 400
        
    file = request.files['profile_pic']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'}), 400
        
    if file:
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        filename = file.filename
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in allowed_extensions:
            return jsonify({'success': False, 'message': 'Allowed image formats: PNG, JPG, JPEG, GIF, WEBP'}), 400
            
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'profile_pics')
        os.makedirs(upload_dir, exist_ok=True)
        
        new_filename = f"user_{session['user_id']}.{ext}"
        file_path = os.path.join(upload_dir, new_filename)
        file.save(file_path)
        
        # Update db and session
        common_db.update_user_profile_pic(session['user_id'], new_filename)
        session['user_profile_pic'] = new_filename
        
        return jsonify({'success': True, 'message': 'Profile picture uploaded successfully', 'url': url_for('static', filename='uploads/profile_pics/' + new_filename)})
        
    return jsonify({'success': False, 'message': 'Failed to save file'}), 500


@app.route('/api/user/profile/save-gemini-key', methods=['POST'])
@user_login_required
def save_user_gemini_key():
    return jsonify({'success': False, 'message': 'AI API keys are managed centrally by system administrators.'}), 400


@app.route('/api/user/profile/clear-gemini-key', methods=['POST'])
@user_login_required
def clear_user_gemini_key():
    return jsonify({'success': True, 'message': 'Settings updated.'})


@app.route('/api/user/profile/test-gemini-key', methods=['POST'])
@user_login_required
def test_user_gemini_key():
    return jsonify({'success': False, 'message': 'AI API keys are managed centrally by system administrators.'}), 400


@app.route('/api/user/profile/list-gemini-models', methods=['POST'])
@user_login_required
def list_user_gemini_models():
    return jsonify({'success': False, 'message': 'AI models are managed centrally by system administrators.'}), 400


# =============================================================================
# ADMIN GEMINI KEY CONFIGURATION (separate from chunk-tool system key)
# =============================================================================

@app.route('/api/admin/save-gemini-key', methods=['POST'])
@login_required
def admin_save_gemini_key():
    """Save admin's personal Gemini API key and model for व्याख्या AI & संभाषण AI (not the chunk-tool system key)."""
    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    gemini_model = data.get('gemini_model', '').strip()
    username = session.get('admin_username', '')
    if not username:
        return jsonify({'success': False, 'message': 'Admin session not found.'}), 401
    if not api_key:
        return jsonify({'success': False, 'message': 'API key cannot be empty.'}), 400

    if gemini_model:
        gemini_model = gemini_model.strip('/').strip()
        gemini_model = gemini_model.replace('\\', '/')
        while '//' in gemini_model:
            gemini_model = gemini_model.replace('//', '/')
        lower = gemini_model.lower()
        if lower.startswith('models/'):
            gemini_model = f"models/{gemini_model[7:]}"
        elif lower.startswith('tunedmodels/'):
            gemini_model = f"tunedmodels/{gemini_model[12:]}"
        else:
            gemini_model = f"models/{gemini_model}"
    else:
        gemini_model = None

    import ai_search
    success, err = ai_search.test_api_key(api_key)
    if not success:
        if not config.is_gemini_quota_error(err):
            return jsonify({'success': False, 'message': f'Invalid AI API Key: {err}'}), 400

    if common_db.update_admin_gemini_key(username, api_key, gemini_model):
        return jsonify({'success': True, 'message': 'AI API Key saved successfully!'})
    return jsonify({'success': False, 'message': 'Failed to save key to database.'}), 500


@app.route('/api/admin/clear-gemini-key', methods=['POST'])
@login_required
def admin_clear_gemini_key():
    """Clear the admin's personal Gemini API key and model."""
    username = session.get('admin_username', '')
    if not username:
        return jsonify({'success': False, 'message': 'Admin session not found.'}), 401
    if common_db.update_admin_gemini_key(username, None, None):
        return jsonify({'success': True, 'message': 'AI API Key cleared successfully!'})
    return jsonify({'success': False, 'message': 'Failed to clear API key.'}), 500


@app.route('/api/admin/test-gemini-key', methods=['POST'])
@login_required
def admin_test_gemini_key():
    """Test the admin's personal Gemini API key."""
    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    username = session.get('admin_username', '')
    if not api_key and username:
        api_key, _ = common_db.get_admin_gemini_key(username)
    if not api_key:
        return jsonify({'success': False, 'message': 'No API key provided or configured.'}), 400
    import ai_search
    success, err = ai_search.test_api_key(api_key)
    if success:
        return jsonify({'success': True, 'message': 'AI API connection successful!'})
    if config.is_gemini_quota_error(err):
        return jsonify({'success': True, 'message': 'AI API key is valid, but it has exceeded its daily/rate quota limit. It will work when the quota resets tomorrow.'})
    return jsonify({'success': False, 'message': f'Connection failed: {err}'}), 400


@app.route('/api/admin/list-gemini-models', methods=['POST'])
@login_required
def admin_list_gemini_models():
    """List working Gemini models for the admin's personal key."""
    data = request.get_json() or {}
    api_key = data.get('api_key', '').strip()
    username = session.get('admin_username', '')
    if not api_key and username:
        api_key, _ = common_db.get_admin_gemini_key(username)
    if not api_key:
        return jsonify({'success': False, 'message': 'API key is required to fetch models. Please configure your personal AI API Key in the Admin Dashboard settings first.'}), 400

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        from google.api_core import retry
        no_retry = retry.Retry(predicate=lambda e: False)

        raw_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                name_lower = m.name.lower()
                if 'gemini' not in name_lower and 'gemma' not in name_lower and not m.name.startswith('tunedModels/'):
                    continue
                if any(x in name_lower for x in ('embedding', 'tts', 'image', 'robotics', 'computer-use', 'customtools', 'vision')):
                    continue
                raw_models.append(m.name)

        import concurrent.futures
        def _test_admin_model(name):
            try:
                import google.generativeai as tg
                tg.configure(api_key=api_key)
                mdl = tg.GenerativeModel(name)
                mdl.generate_content('hi', generation_config={'max_output_tokens': 1},
                                     request_options={'retry': no_retry, 'timeout': 5.0})
                return name, True
            except Exception as e:
                err_str = str(e)
                # 1. Check for permanent quota limit 0
                if 'limit: 0' in err_str:
                    return name, False
                
                # 2. Check for permanent API errors (model does not exist, bad args, or no permission)
                from google.api_core.exceptions import NotFound, InvalidArgument, PermissionDenied
                if isinstance(e, (NotFound, InvalidArgument, PermissionDenied)):
                    return name, False
                
                # 3. For any other error (ResourceExhausted/429, DeadlineExceeded/timeout, connection errors, etc.),
                # assume the model is valid but throttled/delayed, so we still show it.
                return name, True

        working = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            for name, ok in executor.map(_test_admin_model, raw_models):
                if ok:
                    display = name[7:] if name.startswith('models/') else name
                    working.append(display)
        working.sort()
        return jsonify({'success': True, 'models': working})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to fetch models: {str(e)}'}), 400




@app.route('/api/user/quiz-feedback', methods=['POST'])
def api_quiz_feedback():
    """Save feedback (thumbs up/down and optional comment) for a quiz question."""
    data = request.get_json() or {}
    question_id = data.get('question_id')
    vote = data.get('vote', '').strip().lower()
    comments = data.get('comments', '').strip()

    if not question_id or vote not in ('up', 'down'):
        return jsonify({'success': False, 'message': 'Invalid parameters. question_id and vote (up/down) are required.'}), 400

    try:
        question_id = int(question_id)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Invalid question ID format.'}), 400

    # Resolve user_id if logged in (check session first, then bearer token)
    user_id = session.get('user_id')
    if not user_id:
        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
        else:
            token = request.headers.get('X-User-Token')
        if not token:
            token = request.args.get('token')
        if token:
            user_id = common_db.verify_user_token(token)

    success = quiz_db.save_quiz_feedback(question_id, user_id, vote, comments)
    if success:
        return jsonify({'success': True, 'message': 'Feedback submitted successfully.'})
    
    return jsonify({'success': False, 'message': 'Failed to save feedback to database.'}), 500




def load_task_status(task_id):
    import json
    tasks_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf_tasks')
    json_path = os.path.join(tasks_dir, f"{task_id}.json")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None

def save_task_status(task_id, data):
    import json
    tasks_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf_tasks')
    os.makedirs(tasks_dir, exist_ok=True)
    json_path = os.path.join(tasks_dir, f"{task_id}.json")
    tmp_path = json_path + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp_path, json_path)
    except:
        pass

def cleanup_old_pdf_tasks():
    """Clean up task files older than 2 hours from pdf_tasks directory"""
    try:
        tasks_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf_tasks')
        if not os.path.exists(tasks_dir):
            return
        import time
        now = time.time()
        max_age = 2 * 3600  # 2 hours
        for filename in os.listdir(tasks_dir):
            filepath = os.path.join(tasks_dir, filename)
            if os.path.isfile(filepath):
                if now - os.path.getmtime(filepath) > max_age:
                    try:
                        os.remove(filepath)
                    except:
                        pass
    except Exception as e:
        print(f"Error cleaning up old PDF tasks: {e}")

def bg_generate_pdf(task_id, book_name, font_choice='sanskrit_text', align_choice='center', script_choice='sa'):
    try:
        def update_progress(current, total):
            task = load_task_status(task_id)
            if task:
                task['current_page'] = current
                task['total_pages'] = total
                save_task_status(task_id, task)
        
        pdf_bytes = convert_text_book_to_image_pdf(book_name, progress_callback=update_progress, font_choice=font_choice, align_choice=align_choice, script_choice=script_choice)
        if not pdf_bytes:
            save_task_status(task_id, {
                'status': 'error',
                'error': 'Failed to compile PDF',
                'book_name': book_name,
                'current_page': 0,
                'total_pages': 0
            })
            return
        
        tasks_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf_tasks')
        os.makedirs(tasks_dir, exist_ok=True)
        pdf_path = os.path.join(tasks_dir, f"{task_id}.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(pdf_bytes)
            
        task = load_task_status(task_id) or {
            'book_name': book_name,
            'current_page': 0,
            'total_pages': 0
        }
        task.update({
            'status': 'completed'
        })
        save_task_status(task_id, task)
    except Exception as e:
        save_task_status(task_id, {
            'status': 'error',
            'error': str(e),
            'book_name': book_name,
            'current_page': 0,
            'total_pages': 0
        })


def split_text_runs(text):
    """Splits a line of text into runs of Devanagari vs non-Devanagari characters to avoid font box issues"""
    runs = []
    current_run = ""
    current_is_deva = None
    
    for char in text:
        cp = ord(char)
        # Devanagari characters: standard block (0x0900-0x097F) + Vedic Extensions (0x1CD0-0x1CFF) + Dandas
        is_deva = (0x0900 <= cp <= 0x097F) or (0x1CD0 <= cp <= 0x1CFF) or char in ['।', '॥']
        
        if char == ' ':
            if current_is_deva is not None:
                current_run += char
                continue
            else:
                is_deva = False
                
        if current_is_deva is None:
            current_is_deva = is_deva
            current_run += char
        elif current_is_deva == is_deva:
            current_run += char
        else:
            runs.append((current_run, current_is_deva))
            current_run = char
            current_is_deva = is_deva
            
    if current_run:
        runs.append((current_run, current_is_deva))
        
    return runs


def get_line_width(text, deva_font, latin_font, draw):
    """Calculate width of a line by summing the width of its Devanagari and Latin components"""
    runs = split_text_runs(text)
    total_w = 0
    for run_text, is_deva in runs:
        font_to_use = deva_font if is_deva else latin_font
        try:
            bbox = draw.textbbox((0, 0), run_text, font=font_to_use)
            run_w = bbox[2] - bbox[0]
        except AttributeError:
            run_w = draw.textsize(run_text, font=font_to_use)[0]
        total_w += run_w
    return total_w


def draw_line_with_fallback(draw, text, x_start, y, deva_font, latin_font, text_color):
    """Draw a line segment-by-segment using Devanagari and Latin fonts to prevent box rendering"""
    runs = split_text_runs(text)
    x = x_start
    for run_text, is_deva in runs:
        font_to_use = deva_font if is_deva else latin_font
        # Shift non-Devanagari runs down by 1px to align visually with hanging Devanagari characters
        y_offset = 0 if is_deva else 1
        draw.text((x, y + y_offset), run_text, fill=text_color, font=font_to_use)
        try:
            bbox = draw.textbbox((0, 0), run_text, font=font_to_use)
            run_w = bbox[2] - bbox[0]
        except AttributeError:
            run_w = draw.textsize(run_text, font=font_to_use)[0]
        x += run_w


def find_deva_font(font_choice=None):
    """Locates a suitable Devanagari TrueType font.
    Prefers bundled repository fonts in static/fonts/, then system fonts.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    this_dir = os.path.dirname(os.path.abspath(__file__))
    
    font_dirs = []
    if 'app' in globals() and hasattr(app, 'static_folder') and app.static_folder:
        font_dirs.append(os.path.join(app.static_folder, 'fonts'))
    font_dirs.extend([
        os.path.join(repo_root, 'static', 'fonts'),
        os.path.join(this_dir, 'static', 'fonts'),
        os.path.join(this_dir, '..', 'static', 'fonts'),
        os.path.join(os.getcwd(), 'static', 'fonts'),
    ])

    choice_map = {
        'siddhanta': ['siddhanta.ttf'],
        'noto_serif': ['NotoSerifDevanagari-Regular.ttf', 'NotoSerifDevanagari-Medium.ttf'],
        'noto_sans': ['NotoSansDevanagari-Regular.ttf', 'NotoSansDevanagari-Medium.ttf'],
        'sanskrit_text': ['NotoSerifDevanagari-Regular.ttf', 'siddhanta.ttf', 'NotoSansDevanagari-Regular.ttf'],
        'skttext': ['NotoSerifDevanagari-Regular.ttf', 'siddhanta.ttf', 'NotoSansDevanagari-Regular.ttf'],
        'mangal': ['NotoSerifDevanagari-Regular.ttf', 'siddhanta.ttf'],
        'aparajita': ['NotoSerifDevanagari-Regular.ttf', 'siddhanta.ttf'],
        'nirmula_ui': ['NotoSansDevanagari-Regular.ttf', 'NotoSerifDevanagari-Regular.ttf'],
    }

    # 1. Check requested font in bundled font folders
    if font_choice and str(font_choice).lower() in choice_map:
        for fname in choice_map[str(font_choice).lower()]:
            for fdir in font_dirs:
                p = os.path.normpath(os.path.join(fdir, fname))
                if os.path.isfile(p):
                    return p

    # 2. Check all bundled Devanagari fonts
    bundled_names = [
        'NotoSerifDevanagari-Regular.ttf',
        'NotoSansDevanagari-Regular.ttf',
        'siddhanta.ttf',
        'NotoSerifDevanagari-Medium.ttf',
        'NotoSansDevanagari-Medium.ttf',
    ]
    for fdir in font_dirs:
        for fname in bundled_names:
            p = os.path.normpath(os.path.join(fdir, fname))
            if os.path.isfile(p):
                return p

    # 3. Check system font locations
    system_candidates = [
        '/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Medium.ttf',
        '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Medium.ttf',
        '/usr/share/fonts/truetype/noto/NotoSerifDevanagari-Regular.ttf',
        '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf',
        os.path.expanduser('~/.local/share/fonts/keyman/itrans_devanagari_sanskrit_vedic/siddhanta.ttf'),
        'C:/Windows/Fonts/skttext.ttf',
        'C:/Windows/Fonts/SktText.ttf',
        'C:/Windows/Fonts/mangal.ttf',
        'C:/Windows/Fonts/aparaj.ttf',
        'C:/Windows/Fonts/Nirmala.ttf',
        'C:/Windows/Fonts/NirmalaUI.ttf',
    ]
    for p in system_candidates:
        if os.path.isfile(p):
            return p

    return None


def find_script_font(script_choice='sa', font_choice=None):
    """Locates a suitable TrueType font for the requested script (sa, ta, ka, te, en).
    Prefers bundled fonts in static/fonts/, then system font locations.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    this_dir = os.path.dirname(os.path.abspath(__file__))
    
    font_dirs = []
    if 'app' in globals() and hasattr(app, 'static_folder') and app.static_folder:
        font_dirs.append(os.path.join(app.static_folder, 'fonts'))
    font_dirs.extend([
        os.path.join(repo_root, 'static', 'fonts'),
        os.path.join(this_dir, 'static', 'fonts'),
        os.path.join(this_dir, '..', 'static', 'fonts'),
        os.path.join(os.getcwd(), 'static', 'fonts'),
        '/usr/share/fonts/truetype/noto',
        '/usr/share/fonts/opentype/noto',
        '/usr/local/share/fonts',
        '/usr/share/fonts',
    ])

    script = str(script_choice).lower().strip() if script_choice else 'sa'

    script_font_preferences = {
        'ta': [
            'NotoSerifTamil-Regular.ttf',
            'NotoSansTamil-Regular.ttf',
            'NotoSerifTamil-Medium.ttf',
            'NotoSansTamil-Medium.ttf'
        ],
        'ka': [
            'NotoSerifKannada-Regular.ttf',
            'NotoSansKannada-Regular.ttf',
            'NotoSerifKannada-Medium.ttf',
            'NotoSansKannada-Medium.ttf'
        ],
        'te': [
            'NotoSerifTelugu-Regular.ttf',
            'NotoSansTelugu-Regular.ttf',
            'NotoSerifTelugu-Medium.ttf',
            'NotoSansTelugu-Medium.ttf'
        ],
        'en': [
            'NotoSerif-Regular.ttf',
            'NotoSans-Regular.ttf'
        ]
    }

    if script in script_font_preferences:
        for fname in script_font_preferences[script]:
            for fdir in font_dirs:
                p = os.path.normpath(os.path.join(fdir, fname))
                if os.path.isfile(p):
                    return p

    # Default to Devanagari font locator
    return find_deva_font(font_choice)


def transliterate_content(text, target_script):
    """Safely transliterates Sanskrit (Devanagari) text into target_script (ta, ka, te, en)."""
    if not text or not target_script or target_script == 'sa':
        return text
    try:
        import sys
        sys_apps = os.path.join(APP_DIR, '..', 'apps', 'transliterator', 'backend')
        if sys_apps not in sys.path:
            sys.path.insert(0, sys_apps)
        from translit_engine import convert_script
        return convert_script(text, 'sa', target_script)
    except Exception as e:
        app.logger.warning(f"Transliteration error to {target_script}: {e}")
        return text


def convert_text_book_to_image_pdf(book_name, progress_callback=None, font_choice='sanskrit_text', align_choice='center', script_choice='sa'):
    """Helper to convert a text-only book to a high-quality copy-protected vector PDF.
    
    Uses FPDF2 with integrated HarfBuzz (uharfbuzz) complex script text-shaping
    for proper Devanagari, Tamil, Telugu, and Kannada conjunct alignment, then applies standard AES-256
    copy-protection permissions via PyMuPDF (fitz) so text is razor-sharp at any zoom,
    downloads rapidly, and maintains copy-protection without 35MB+ JPEG file bloat.
    """
    import fitz
    from fpdf import FPDF
    import uuid
    
    align_map = {'left': 'L', 'center': 'C', 'middle': 'C', 'justify': 'J'}
    pdf_align = align_map.get(str(align_choice).lower(), 'C')

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    if not os.path.exists(folder_path):
        return None
        
    txt_files = [f for f in sorted(os.listdir(folder_path)) 
                if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
    
    full_text = ""
    for txt_file in txt_files:
        try:
            full_text += get_cached_file_content(os.path.join(folder_path, txt_file)) + "\n"
        except:
            pass
            
    if not full_text:
        return None
        
    # Clean text (non-breaking spaces, control characters, bom)
    full_text = full_text.replace('\xa0', ' ').replace('\t', '    ')
    full_text = full_text.replace('\r\n', '\n').replace('\r', '\n')
    full_text = full_text.replace('\u00ad', '').replace('\u200b', '').replace('\ufeff', '')
    
    # Strip out original page markers so we wrap continuously
    full_text = re.sub(r'\{\[\((\d+)\)\]\}', '', full_text)
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
    total_paragraphs = max(len(paragraphs), 1)
    
    # Transliterate paragraphs if a target script was selected
    if script_choice and script_choice != 'sa':
        paragraphs = [transliterate_content(p, script_choice) for p in paragraphs]
        display_title = transliterate_content(book_name, script_choice)
    else:
        display_title = book_name

    font_path = find_script_font(script_choice=script_choice, font_choice=font_choice)
    active_font = "BookFont" if (font_path and os.path.isfile(font_path)) else "Helvetica"

    watermark_title = transliterate_content('संशोधनमन्दिरम्', script_choice) if script_choice != 'en' else 'Samshodhana Mandiram'

    class BookFPDF(FPDF):
        def __init__(self, title, watermark_text="संशोधनमन्दिरम्", font_name="BookFont"):
            super().__init__()
            self.book_title = title
            self.watermark_text = watermark_text
            self.font_name = font_name
            self.set_margin(18)
            self.set_auto_page_break(True, margin=18)
            
        def header(self):
            with self.local_context():
                # 1. Background Watermark (multiple times across page)
                # Low visibility for humans (faint light gray, not disturbing),
                # but clearly detectable by OCR engines and embedded in the text stream.
                if self.watermark_text and self.font_name != "Helvetica":
                    self.set_font(self.font_name, size=18)
                    self.set_text_color(230, 232, 236)
                    wm_w = self.get_string_width(self.watermark_text) + 4
                    wm_h = 8
                    wm_angles = [
                        [25, -30, 35],
                        [-22, 40, -35],
                        [32, -25, 28],
                        [-38, 20, -42],
                        [30, -32, 24]
                    ]
                    for r_idx, cy in enumerate(range(40, 280, 48)):
                        x_shift = 35 if (r_idx % 2 == 1) else 0
                        row_angles = wm_angles[r_idx % len(wm_angles)]
                        for c_idx, cx in enumerate(range(20 + x_shift, 210, 70)):
                            ang = row_angles[c_idx % len(row_angles)]
                            with self.rotation(ang, cx, cy):
                                self.set_xy(cx - wm_w / 2, cy - wm_h / 2)
                                self.cell(wm_w, wm_h, text=self.watermark_text, align="C")

                # 2. Running Header: Book title only (no site name)
                self.set_y(9)
                self.set_font(self.font_name, size=9.5)
                self.set_text_color(100, 110, 120)
                hdr_text = self.book_title
                max_w = self.w - 36
                if self.get_string_width(hdr_text) > max_w:
                    while len(hdr_text) > 3 and self.get_string_width(f"{hdr_text}…") > max_w:
                        hdr_text = hdr_text[:-1]
                    hdr_text = f"{hdr_text}…"
                self.cell(0, 5, text=hdr_text, align="C")
                self.set_draw_color(210, 210, 210)
                self.set_line_width(0.35)
                self.line(18, 16, self.w - 18, 16)
            self.set_xy(18, 21)
            
        def footer(self):
            with self.local_context():
                self.set_y(-14)
                self.set_draw_color(220, 220, 220)
                self.set_line_width(0.3)
                self.line(18, self.h - 16, self.w - 18, self.h - 16)
                self.set_font(self.font_name, size=9.5)
                self.set_text_color(120, 120, 120)
                self.cell(0, 6, text=f"{self.page_no()}", align="C")

    pdf = BookFPDF(display_title, watermark_text=watermark_title, font_name=active_font)
    
    # Register TrueType font with HarfBuzz shaping engine
    if font_path and os.path.isfile(font_path):
        try:
            pdf.add_font("BookFont", style="", fname=font_path)
            pdf.set_text_shaping(use_shaping_engine=True)
        except Exception as e:
            app.logger.warning(f"Could not load custom font or enable text shaping: {e}")
            active_font = "Helvetica"
            pdf.font_name = "Helvetica"
    else:
        active_font = "Helvetica"
        pdf.font_name = "Helvetica"

    pdf.add_page()
    pdf.set_font(active_font, size=13)
    pdf.set_text_color(30, 30, 30)
    
    # Write paragraphs with shaping, throttling progress updates to avoid excessive disk I/O
    step = max(1, total_paragraphs // 50)
    for idx, para in enumerate(paragraphs):
        if progress_callback and (idx % step == 0 or idx == total_paragraphs - 1):
            try:
                progress_callback(idx + 1, total_paragraphs)
            except:
                pass
        pdf.multi_cell(0, 7.8, text=para, new_x="LMARGIN", new_y="NEXT", align=pdf_align)
        pdf.ln(3.2)
        
    raw_pdf_bytes = bytes(pdf.output())
    
    # Apply standard AES-256 print-only permissions (copy-protection)
    try:
        doc = fitz.open("pdf", raw_pdf_bytes)
        doc.set_metadata({
            "title": display_title,
            "author": "Samshodhana Mandiram",
            "subject": display_title,
            "creator": "Samshodhana Mandiram Digital Library",
            "producer": "PyMuPDF"
        })
        enc_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            permissions=fitz.PDF_PERM_PRINT,
            owner_pw=uuid.uuid4().hex
        )
        doc.close()
        return enc_bytes
    except Exception as e:
        print(f"Warning: could not apply PDF encryption: {e}")
        return raw_pdf_bytes


@app.route('/api/user/download-pdf/start/<path:book_name>', methods=['POST'])
def api_user_download_pdf_start(book_name):
    """Start asynchronous PDF generation"""
    req_data = request.get_json(silent=True) or {}
    font_choice = req_data.get('font_choice', 'sanskrit_text')
    align_choice = req_data.get('align_choice', 'center')
    script_choice = req_data.get('script_choice') or req_data.get('script') or 'sa'

    # Clean up old tasks in background
    cleanup_thread = threading.Thread(target=cleanup_old_pdf_tasks)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    task_id = str(uuid.uuid4())
    save_task_status(task_id, {
        'status': 'processing',
        'current_page': 0,
        'total_pages': 0,
        'book_name': book_name,
        'font_choice': font_choice,
        'align_choice': align_choice,
        'script_choice': script_choice,
        'error': None
    })
    t = threading.Thread(target=bg_generate_pdf, args=(task_id, book_name, font_choice, align_choice, script_choice))
    t.daemon = True
    t.start()
    return jsonify({'success': True, 'task_id': task_id})


@app.route('/api/user/download-pdf/status/<task_id>')
def api_user_download_pdf_status(task_id):
    """Get status of asynchronous PDF generation"""
    task = load_task_status(task_id)
    if not task:
        return jsonify({'status': 'not_found'}), 404
    return jsonify({
        'status': task['status'],
        'current_page': task.get('current_page', 0),
        'total_pages': task.get('total_pages', 0),
        'error': task.get('error')
    })


@app.route('/api/user/download-pdf/file/<task_id>')
def api_user_download_pdf_file(task_id):
    """Download the completed PDF file"""
    task = load_task_status(task_id)
    tasks_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'pdf_tasks')
    pdf_path = os.path.join(tasks_dir, f"{task_id}.pdf")
    
    if not task or task['status'] != 'completed' or not os.path.exists(pdf_path):
        return jsonify({'error': 'File not ready or not found'}), 404
        
    book_name = task.get('book_name', 'book')
    script_choice = task.get('script_choice', 'sa')
    suffix = f"_{script_choice}" if script_choice and script_choice != 'sa' else ""
    
    # Safely stream file directly from disk without premature deletion;
    # background cleanup_old_pdf_tasks purges tasks older than 2 hours.
    return send_file(
        pdf_path,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"{book_name}{suffix}.pdf"
    )



# =============================================================================
# USER FAVORITES API
# =============================================================================


@app.route('/api/user/favourite', methods=['POST'])
@user_login_required
def api_toggle_favourite():
    data = request.get_json() or {}
    book_name = data.get('book_name') or request.form.get('book_name')
    if not book_name:
        return jsonify({'success': False, 'message': 'Book name is required'}), 400
        
    result = common_db.toggle_favourite(session['user_id'], book_name)
    return jsonify({
        'success': True,
        'is_favourite': result['is_favourite'],
        'message': 'Added to favourites' if result['is_favourite'] else 'Removed from favourites'
    })


@app.route('/api/user/favourites', methods=['GET'])
@user_login_required
def api_get_favourites():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': True, 'favourites': []})
    favs = common_db.get_favourites(user_id)
    return jsonify({'success': True, 'favourites': favs})


@app.route('/api/user/quiz/history', methods=['GET'])
@user_login_required
def api_user_quiz_history():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': True, 'quiz_history': []})
    history = quiz_db.get_user_quiz_results(user_id)
    return jsonify({
        'success': True,
        'quiz_history': history
    })



# =============================================================================
# USER BOOKLISTS API
# =============================================================================

@app.route('/api/user/booklists', methods=['GET'])
@user_login_required
def api_get_booklists():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': True, 'booklists': []})
    book_name = request.args.get('book_name')
    lists = common_db.get_booklists(user_id)
    if book_name:
        for lst in lists:
            lst['contains_book'] = common_db.is_book_in_booklist(lst['id'], book_name)
    return jsonify({'success': True, 'booklists': lists})


@app.route('/api/user/booklist/create', methods=['POST'])
@user_login_required
def api_create_booklist():
    data = request.get_json() or {}
    name = data.get('name') or request.form.get('name')
    description = data.get('description', '') or request.form.get('description', '')
    if not name or not name.strip():
        return jsonify({'success': False, 'message': 'Booklist name is required'}), 400
        
    bl_id = common_db.create_booklist(session['user_id'], name, description)
    if bl_id:
        return jsonify({'success': True, 'booklist_id': bl_id, 'message': 'Booklist created successfully'})
    return jsonify({'success': False, 'message': 'Failed to create booklist'}), 500


@app.route('/api/user/booklist/<int:booklist_id>/add', methods=['POST'])
@user_login_required
def api_add_to_booklist(booklist_id):
    data = request.get_json() or {}
    book_name = data.get('book_name') or request.form.get('book_name')
    if not book_name:
        return jsonify({'success': False, 'message': 'Book name is required'}), 400
        
    success, message = common_db.add_to_booklist(booklist_id, book_name, session['user_id'])
    return jsonify({'success': success, 'message': message})


@app.route('/api/user/booklist/<int:booklist_id>/remove', methods=['POST'])
@user_login_required
def api_remove_from_booklist(booklist_id):
    data = request.get_json() or {}
    book_name = data.get('book_name') or request.form.get('book_name')
    if not book_name:
        return jsonify({'success': False, 'message': 'Book name is required'}), 400
        
    success, message = common_db.remove_from_booklist(booklist_id, book_name, session['user_id'])
    return jsonify({'success': success, 'message': message})


@app.route('/api/user/booklist/<int:booklist_id>/delete', methods=['POST'])
@user_login_required
def api_delete_booklist(booklist_id):
    success, message = common_db.delete_booklist(booklist_id, session['user_id'])
    return jsonify({'success': success, 'message': message})


@app.route('/api/user/booklist/<int:booklist_id>/rename', methods=['POST'])
@user_login_required
def api_rename_booklist(booklist_id):
    data = request.get_json() or {}
    name = data.get('name') or request.form.get('name')
    description = data.get('description') or request.form.get('description')
    if not name or not name.strip():
        return jsonify({'success': False, 'message': 'Booklist name is required'}), 400
        
    success, message = common_db.rename_booklist(booklist_id, session['user_id'], name, description)
    return jsonify({'success': success, 'message': message})


@app.route('/user/booklist/<int:booklist_id>', methods=['GET'])
@user_login_required
def user_view_booklist(booklist_id):
    detail = common_db.get_booklist_detail(booklist_id, session['user_id'])
    if not detail:
        flash('Booklist not found or access denied', 'error')
        return redirect('/user/sdl-profile')
    return render_template('public/booklist_detail.html', booklist=detail)





# =============================================================================
# SDL ADMIN DASHBOARD (Books, Tags, Stats — SDL-specific)
# =============================================================================
# NOTE: Shared admin routes (Hub, Users, Manage Admins, Audit Logs)
# are served by the standalone admin_app in server.py via admin_shared.py.
# =============================================================================
@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin stats dashboard with high-level library insights and tag distributions"""
    if session.get('admin_role') != 'super':
        if 'user_logged_in' in session:
            return redirect('/user/sdl-profile')
        return render_template('admin/forbidden.html', permission='SUPERADMIN'), 403
        
    try:
        all_books = get_all_books(bypass_cache=True, include_unpublished=True)
        
        status_filter = request.args.get('status', 'all').strip().lower()
        if status_filter == 'published':
            filtered_books = [b for b in all_books if b.get('published', True)]
        elif status_filter == 'draft':
            filtered_books = [b for b in all_books if not b.get('published', True)]
        else:
            status_filter = 'all'
            filtered_books = all_books

        book_count = len(filtered_books)
        published_book_count = sum(1 for book in filtered_books if book.get('published', True))
        unpublished_book_count = sum(1 for book in filtered_books if not book.get('published', True))
        
        all_books = filtered_books  # Reassign so subsequent loops automatically use the filtered set
    except Exception as e:
        print(f"Error getting book count: {e}")
        all_books = []
        book_count = 0
        published_book_count = 0
        unpublished_book_count = 0
        status_filter = 'all'

    try:
        user_count = len(common_db.get_all_users())
    except Exception as e:
        print(f"Error getting user count: {e}")
        user_count = 0

    try:
        quiz_count = quiz_db.get_quiz_question_count()
    except Exception as e:
        print(f"Error getting quiz count: {e}")
        quiz_count = 0

    try:
        katha_count = katha_db.get_katha_count()
    except Exception as e:
        print(f"Error getting katha count: {e}")
        katha_count = 0

    try:
        article_count = articles_db.get_article_count()
    except Exception as e:
        print(f"Error getting article count: {e}")
        article_count = 0

    unread_count = 0

    # Calculate Tag distribution
    tag_counts = {}
    for book in all_books:
        tags_str = book.get('tags', '')
        if tags_str:
            for t in tags_str.split(','):
                t_clean = t.strip()
                if t_clean:
                    tag_counts[t_clean] = tag_counts.get(t_clean, 0) + 1

    # Sort tags by occurrence descending
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    
    # Keep top 8 tags and group others
    top_n = 8
    tags_data = {}
    if len(sorted_tags) <= top_n:
        tags_data = dict(sorted_tags)
    else:
        for i in range(top_n):
            t_name, t_cnt = sorted_tags[i]
            tags_data[t_name] = t_cnt
        
        others_cnt = sum(cnt for _, cnt in sorted_tags[top_n:])
        if others_cnt > 0:
            tags_data['Others'] = others_cnt

    if not tags_data:
        tags_data = {"No Tags Set": 0}

    # Top 10 tags for bar chart (books per tag)
    bar_tags = dict(list(sorted_tags[:10])) if sorted_tags else {"No Tags": 0}

    total_content = book_count + katha_count + quiz_count + article_count

    # ── 1. AI & Chunking Status ──
    ai_embedded_cnt = 0
    ai_draft_cnt = 0
    ai_unprocessed_cnt = 0
    db_stats = {"total_chunks": 0, "storage_size": "0 B", "last_updated": "Never"}
    
    try:
        from ai_search import get_embedded_book_names, get_db_stats
        embedded_names = set(get_embedded_book_names())
        db_stats = get_db_stats()
    except Exception as e:
        print(f"Error fetching ChromaDB details: {e}")
        embedded_names = set()

    for book in all_books:
        b_name = book['name']
        if b_name in embedded_names:
            ai_embedded_cnt += 1
        else:
            ai_unprocessed_cnt += 1

    # ── 2. Top Favourites ──
    top_favourites = {}
    try:
        favs_list = common_db.get_top_favourites(10)
        top_favourites = {item['book_name']: item['fav_count'] for item in favs_list}
    except Exception as e:
        print(f"Error fetching top favourites: {e}")

    if not top_favourites:
        top_favourites = {"No Favorites Yet": 0}

    # ── 3. Recent Activity Trends (last 7 days) ──
    from datetime import datetime, timedelta
    today = get_ist_now()
    last_7_days = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
    recent_activity = {day: 0 for day in last_7_days}

    # ── 4. Feedback Sentiment ──
    total_feedback_up = 0
    total_feedback_down = 0
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
            for b_id, data in feedback_data.items():
                total_feedback_up += data.get('up', 0)
                total_feedback_down += data.get('down', 0)
        except Exception as e:
            print(f"Error reading feedback JSON: {e}")

    # ── 5. Digitized Books and Total Pages Count ──
    text_only_books_count = 0
    total_pages_ocrd = 0
    total_chars_ocrd = 0
    total_proofread_pages = 0
    completed_proofreading_books = 0
    in_progress_proofreading_books = 0
    ocrd_books_count = 0

    for book in all_books:
        b_name = book['name']
        folder_path = book['path']
        if book.get('has_txt', False):
            ocrd_books_count += 1
            if not book.get('archive_url'):
                text_only_books_count += 1
            
            p_count = 0
            char_count = 0
            cached = CATALOG_METADATA_CACHE.get(b_name)
            if cached and 'pages' in cached and 'chars' in cached:
                p_count = cached['pages']
                char_count = cached['chars']
            else:
                sdl_files = [f for f in sorted(os.listdir(folder_path)) if f.endswith('.sdl')]
                if sdl_files:
                    sdl_path = os.path.join(folder_path, sdl_files[0])
                    try:
                        content = get_cached_file_content(sdl_path)
                        p_count = len(re.findall(r'\{\[\(\d+\)\]\}', content))
                        char_count = len(content)
                    except:
                        pass
                else:
                    for root, dirs, files in os.walk(folder_path):
                        for fname in sorted(files):
                            if fname.endswith('.txt') and fname.lower() != 'metadata.txt':
                                fpath = os.path.join(root, fname)
                                try:
                                    content = get_cached_file_content(fpath)
                                    p_count += len(re.findall(r'\{\[\(\d+\)\]\}', content))
                                    char_count += len(content)
                                except:
                                    continue
                if p_count == 0 and char_count > 0:
                    p_count = max(1, math.ceil(char_count / 1500))
                if b_name not in CATALOG_METADATA_CACHE:
                    CATALOG_METADATA_CACHE[b_name] = {}
                CATALOG_METADATA_CACHE[b_name]['pages'] = p_count
                CATALOG_METADATA_CACHE[b_name]['chars'] = char_count
                save_catalog_cache()
            total_pages_ocrd += p_count
            total_chars_ocrd += char_count
            
            # Proofreading calculations
            pct = book.get('proofread_pct', 0)
            if pct > 0:
                if pct >= 100:
                    completed_proofreading_books += 1
                    total_proofread_pages += p_count
                else:
                    in_progress_proofreading_books += 1
                    total_proofread_pages += int(round(p_count * (pct / 100.0)))

    proofread_percentage = round(total_proofread_pages / total_pages_ocrd * 100.0, 2) if total_pages_ocrd > 0 else 0
    avg_pages_per_book = round(total_pages_ocrd / ocrd_books_count) if ocrd_books_count > 0 else 0

    username = session.get('admin_username', '')
    admin_gemini_key, admin_gemini_model = common_db.get_admin_gemini_key(username) if username else (None, None)
    vyakhya_model = common_db.get_system_setting('sdl_vyakhya_model')
    if not vyakhya_model:
        vyakhya_model = common_db.get_system_setting('vyakhya_model')
    vyakhya_prompt = common_db.get_system_setting('sdl_vyakhya_prompt')
    if not vyakhya_prompt:
        vyakhya_prompt = common_db.get_system_setting('vyakhya_prompt')

    return render_template(
        'admin/dashboard.html',
        book_count=book_count,
        published_book_count=published_book_count,
        unpublished_book_count=unpublished_book_count,
        user_count=user_count,
        quiz_count=quiz_count,
        katha_count=katha_count,
        article_count=article_count,
        unread_count=unread_count,
        tags_data=tags_data,
        bar_tags=bar_tags,
        total_content=total_content,
        ai_embedded_cnt=ai_embedded_cnt,
        ai_draft_cnt=ai_draft_cnt,
        ai_unprocessed_cnt=ai_unprocessed_cnt,
        db_stats=db_stats,
        top_favourites=top_favourites,
        recent_activity=recent_activity,
        total_feedback_up=total_feedback_up,
        total_feedback_down=total_feedback_down,
        text_only_books_count=text_only_books_count,
        total_pages_ocrd=total_pages_ocrd,
        avg_pages_per_book=avg_pages_per_book,
        total_chars_ocrd=total_chars_ocrd,
        total_proofread_pages=total_proofread_pages,
        completed_proofreading_books=completed_proofreading_books,
        in_progress_proofreading_books=in_progress_proofreading_books,
        proofread_percentage=proofread_percentage,
        admin_gemini_key=admin_gemini_key,
        admin_gemini_model=admin_gemini_model,
        vyakhya_model=vyakhya_model,
        vyakhya_prompt=vyakhya_prompt,
        status_filter=status_filter,
        pending_edits_count=common_db.get_pending_edits_count('pending'),
        community_books_count=len([b for b in all_books if b.get('is_community')])
    )


@app.route('/admin/manage-books')
@login_required
def admin_manage_books():
    """Admin book management view with filtering, sorting, and pagination"""
    if session.get('admin_role') != 'super':
        if 'user_logged_in' in session:
            return redirect('/user/sdl-profile')
        return render_template('admin/forbidden.html', permission='SUPERADMIN'), 403
        
    all_books = get_all_books(bypass_cache=True, include_unpublished=True)
    
    # Load feedback data early so we can filter by feedback and attach stats
    feedback_data = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass

    for book in all_books:
        book_feedback = feedback_data.get(book['name'], {'up': 0, 'down': 0, 'comments': []})
        book['feedback_up'] = book_feedback.get('up', 0)
        book['feedback_down'] = book_feedback.get('down', 0)
        book['feedback_comments_count'] = len(book_feedback.get('comments', []))

    # Get filters
    q_name = request.args.get('name', '').strip().lower()
    q_tag = request.args.get('tag', '').strip().lower()
    q_neg_tag = request.args.get('neg_tag', '').strip().lower()
    q_subbook = request.args.get('subbook', '').strip().lower()
    q_ocr = request.args.get('ocr', '').strip().lower()
    q_status = request.args.get('status', '').strip().lower()
    q_proofread = request.args.get('proofread', '').strip().lower()
    q_feedback = request.args.get('feedback', '').strip().lower()
    
    neg_terms = [t.strip() for t in q_neg_tag.split(',') if t.strip()]

    # Apply filters to ALL books before pagination
    if q_name or q_tag or q_neg_tag or q_subbook or q_ocr or q_status or q_proofread or q_feedback:
        filtered_books = []
        for book in all_books:
            name_match = not q_name or q_name in book['name'].lower()
            tag_match = not q_tag or q_tag in (book.get('tags') or '').lower()
            
            neg_tag_match = True
            if neg_terms:
                book_tags = (book.get('tags') or '').lower()
                book_name = book['name'].lower()
                if any(term in book_tags or term in book_name for term in neg_terms):
                    neg_tag_match = False

            subbook_match = not q_subbook or q_subbook in (book.get('subbooks') or '').lower()
            
            ocr_match = True
            if q_ocr == 'digitized':
                ocr_match = book.get('has_txt', False)
            elif q_ocr == 'text_only':
                ocr_match = book.get('has_txt', False) and not book.get('archive_url')
            elif q_ocr == 'pdf_only':
                ocr_match = bool(book.get('archive_url')) and not book.get('has_txt', False)
                
            status_match = True
            if q_status == 'published':
                status_match = book.get('published', True)
            elif q_status == 'draft':
                status_match = not book.get('published', True)
            elif q_status == 'community':
                status_match = book.get('is_community', False)

            pct = book.get('proofread_pct')
            proofread_match = True
            if q_proofread == 'not_started':
                proofread_match = not pct or pct == 0
            elif q_proofread == 'in_progress':
                proofread_match = bool(pct and 0 < pct < 100)
            elif q_proofread == 'completed':
                proofread_match = bool(pct and pct >= 100)

            up_cnt = book.get('feedback_up', 0)
            down_cnt = book.get('feedback_down', 0)
            comments_cnt = book.get('feedback_comments_count', 0)

            feedback_match = True
            if q_feedback == 'has_up':
                feedback_match = up_cnt > 0
            elif q_feedback == 'has_down':
                feedback_match = down_cnt > 0
            elif q_feedback == 'has_comments':
                feedback_match = comments_cnt > 0
            elif q_feedback == 'any':
                feedback_match = (up_cnt > 0 or down_cnt > 0 or comments_cnt > 0)
                
            if name_match and tag_match and neg_tag_match and subbook_match and ocr_match and status_match and proofread_match and feedback_match:
                filtered_books.append(book)
        all_books = filtered_books

    # Assign Serial Number (s_no) based on Alphabetical Order of the filtered set
    all_books.sort(key=lambda x: x['name'].lower())
    for i, book in enumerate(all_books):
        book['s_no'] = i + 1

    # Get sorting params
    sort_col = request.args.get('sort', 'name')
    sort_order = request.args.get('order', 'asc')
    
    # Sort books based on user request (secondary sort)
    reverse = (sort_order == 'desc')
    if sort_col == 'name':
        if reverse:
            all_books.sort(key=lambda x: x['name'].lower(), reverse=True)
    elif sort_col == 'tags':
        all_books.sort(key=lambda x: (x.get('tags') or '').lower(), reverse=reverse)
    elif sort_col == 'subbooks':
        all_books.sort(key=lambda x: (x.get('subbooks') or '').lower(), reverse=reverse)
    elif sort_col == 'notes':
        all_books.sort(key=lambda x: (x.get('notes') or '').lower(), reverse=reverse)
    elif sort_col == 's_no':
        all_books.sort(key=lambda x: x['s_no'], reverse=reverse)
    else:
        if reverse:
            all_books.sort(key=lambda x: x['name'].lower(), reverse=True)
    
    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 20
    total_books = len(all_books)
    total_pages = math.ceil(total_books / per_page)
    
    # Limit page range
    page = max(1, min(page, total_pages or 1))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_books = all_books[start_idx:end_idx]

    if request.args.get('ajax'):
        return jsonify({
            'books': paginated_books,
            'total_books': total_books,
            'page': page,
            'total_pages': total_pages,
            'sort_col': sort_col,
            'sort_order': sort_order,
            'q_name': q_name,
            'q_tag': q_tag,
            'q_neg_tag': q_neg_tag,
            'q_subbook': q_subbook,
            'q_ocr': q_ocr,
            'q_status': q_status,
            'q_proofread': q_proofread,
            'q_feedback': q_feedback
        })

    return render_template('admin/manage_books.html', 
                         books=paginated_books, 
                         total_books=total_books,
                         page=page,
                         total_pages=total_pages,
                         q_name=q_name,
                         q_tag=q_tag,
                         q_neg_tag=q_neg_tag,
                         q_subbook=q_subbook,
                         q_ocr=q_ocr,
                         q_status=q_status,
                         q_proofread=q_proofread,
                         q_feedback=q_feedback,
                         sort_col=sort_col,
                         sort_order=sort_order)

@app.route('/api/feedback', methods=['POST'])
def save_feedback():
    """Save user feedback for a book"""
    data = request.json
    book_id = data.get('book_id')
    status = data.get('status') # 'up' or 'down'
    comment = data.get('comment', '').strip()
    page = data.get('page') # Optional page number
    
    if not book_id or status not in ['up', 'down']:
        return jsonify({'success': False, 'error': 'Invalid feedback data'})
        
    feedback_data = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass
            
    if book_id not in feedback_data:
        feedback_data[book_id] = {'up': 0, 'down': 0, 'comments': []}
        
    if status == 'up':
        feedback_data[book_id]['up'] += 1
    else:
        feedback_data[book_id]['down'] += 1
        
    # Record every interaction in the history if it has a page or a comment
    # This ensures "Page X was rated Up" is captured
    comment_entry = {
        'text': comment,
        'page': page,
        'status': status,
        'time': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    if session.get('user_logged_in') and session.get('user_id'):
        comment_entry['user_id'] = session.get('user_id')
        
    feedback_data[book_id]['comments'].append(comment_entry)
            
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(feedback_data, f, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/api/rich-text-settings', methods=['GET'])
def get_rich_text_settings():
    raw = common_db.get_system_setting('universal_rich_text_settings')
    if raw:
        try:
            return jsonify({'success': True, 'settings': json.loads(raw)})
        except:
            pass
    default_config = {
        'default_font': 'Noto Sans Devanagari',
        'level_font_sizes': {
            '1': '22px',
            '2': '18px',
            '3': '16px'
        }
    }
    return jsonify({'success': True, 'settings': default_config})


@app.route('/admin/api/rich-text-settings', methods=['POST'])
@login_required
def save_rich_text_settings():
    data = request.json or {}
    default_font = data.get('default_font', 'Noto Sans Devanagari').strip()
    level_font_sizes = data.get('level_font_sizes', {})
    
    if not isinstance(level_font_sizes, dict):
        level_font_sizes = {'1': '22px'}
        
    config_obj = {
        'default_font': default_font,
        'level_font_sizes': level_font_sizes
    }
    success = common_db.set_system_setting('universal_rich_text_settings', json.dumps(config_obj, ensure_ascii=False))
    return jsonify({'success': success, 'message': 'Settings saved successfully' if success else 'Failed to save settings'})


def get_level_display_name_py(code, levels_map):
    if not code:
        return ""
    code_str = str(code).strip()
    if not levels_map or not isinstance(levels_map, dict):
        return code_str
    
    if code_str in levels_map:
        val = str(levels_map[code_str]).strip()
        return re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', val).strip()
        
    prefix = code_str
    suffix_parts = []
    while '.' in prefix:
        last_dot = prefix.rfind('.')
        suffix_parts.insert(0, prefix[last_dot + 1:])
        prefix = prefix[:last_dot]
        if prefix in levels_map:
            base_name = str(levels_map[prefix]).strip()
            base_name = re.sub(r'^[\s"\'“”‘’【\[\(]+|[\s"\'“”‘’】\]\)]+$', '', base_name).strip()
            suffix_str = '.'.join(suffix_parts)
            return f"{base_name} - {suffix_str}" if suffix_str else base_name
            
    return code_str


def generate_custom_pdf_bytes(book_name, blocks, levels_map, font_choice=None, align_choice='center', script_choice='sa'):
    """Generates a high-quality PDF document for custom selected commentary layers
    using FPDF2 with HarfBuzz text-shaping engine for perfect Devanagari, Tamil, Telugu, and Kannada ligatures and conjuncts.
    Applies copy-protection permissions via PyMuPDF (fitz) so text renders crisply and securely.
    """
    import fitz
    from fpdf import FPDF

    align_map = {'left': 'L', 'center': 'C', 'middle': 'C', 'justify': 'J'}
    pdf_align = align_map.get(str(align_choice).lower(), 'C')

    if script_choice and script_choice != 'sa':
        display_title = transliterate_content(book_name, script_choice)
    else:
        display_title = book_name

    body_font_path = find_script_font(script_choice=script_choice, font_choice=font_choice)
    active_font = "BookFont" if (body_font_path and os.path.isfile(body_font_path)) else "Helvetica"

    watermark_title = transliterate_content('संशोधनमन्दिरम्', script_choice) if script_choice != 'en' else 'Samshodhana Mandiram'

    class CustomBookFPDF(FPDF):
        def __init__(self, title, watermark_text="संशोधनमन्दिरम्", font_name="BookFont"):
            super().__init__()
            self.book_title = title
            self.watermark_text = watermark_text
            self.font_name = font_name
            self.set_margin(18)
            self.set_auto_page_break(True, margin=18)

        def header(self):
            with self.local_context():
                # 1. Background Watermark (multiple times across page)
                # Low visibility for humans (faint light gray, not disturbing),
                # but clearly detectable by OCR engines and embedded in the text stream.
                if self.watermark_text and self.font_name != "Helvetica":
                    self.set_font(self.font_name, size=18)
                    self.set_text_color(230, 232, 236)
                    wm_w = self.get_string_width(self.watermark_text) + 4
                    wm_h = 8
                    wm_angles = [
                        [25, -30, 35],
                        [-22, 40, -35],
                        [32, -25, 28],
                        [-38, 20, -42],
                        [30, -32, 24]
                    ]
                    for r_idx, cy in enumerate(range(40, 280, 48)):
                        x_shift = 35 if (r_idx % 2 == 1) else 0
                        row_angles = wm_angles[r_idx % len(wm_angles)]
                        for c_idx, cx in enumerate(range(20 + x_shift, 210, 70)):
                            ang = row_angles[c_idx % len(row_angles)]
                            with self.rotation(ang, cx, cy):
                                self.set_xy(cx - wm_w / 2, cy - wm_h / 2)
                                self.cell(wm_w, wm_h, text=self.watermark_text, align="C")

                # 2. Running Header: Book title only (no site name)
                self.set_y(9)
                self.set_font(self.font_name, size=9.5)
                self.set_text_color(100, 110, 120)
                hdr_text = self.book_title
                max_w = self.w - 36
                if self.get_string_width(hdr_text) > max_w:
                    while len(hdr_text) > 3 and self.get_string_width(f"{hdr_text}…") > max_w:
                        hdr_text = hdr_text[:-1]
                    hdr_text = f"{hdr_text}…"
                self.cell(0, 5, text=hdr_text, align="C")
                self.set_draw_color(210, 210, 210)
                self.set_line_width(0.35)
                self.line(18, 16, self.w - 18, 16)
            self.set_xy(18, 21)

        def footer(self):
            with self.local_context():
                self.set_y(-14)
                self.set_draw_color(220, 220, 220)
                self.set_line_width(0.3)
                self.line(18, self.h - 16, self.w - 18, self.h - 16)
                self.set_font(self.font_name, size=9.5)
                self.set_text_color(120, 120, 120)
                self.cell(0, 6, text=f"{self.page_no()}", align="C")

    pdf = CustomBookFPDF(display_title, watermark_text=watermark_title, font_name=active_font)

    if body_font_path and os.path.isfile(body_font_path):
        try:
            pdf.add_font("BookFont", style="", fname=body_font_path)
            pdf.set_text_shaping(use_shaping_engine=True)
        except Exception as e:
            app.logger.warning(f"Could not load custom font or enable text shaping: {e}")
            active_font = "Helvetica"
            pdf.font_name = "Helvetica"
    else:
        active_font = "Helvetica"
        pdf.font_name = "Helvetica"

    pdf.add_page()

    for b in blocks:
        code = b['level']
        text = b['text']
        label_name = get_level_display_name_py(code, levels_map)
        if script_choice and script_choice != 'sa':
            label_name = transliterate_content(label_name, script_choice)
            text = transliterate_content(text, script_choice)
        is_moolam = code.startswith('1')

        if label_name:
            pdf.set_font(active_font, size=10.5)
            pdf.set_text_color(140, 80, 20)
            pdf.multi_cell(0, 6, text=f"[{label_name}]", new_x="LMARGIN", new_y="NEXT", align=pdf_align)
            pdf.ln(1)

        if is_moolam:
            pdf.set_font(active_font, size=13.5)
            pdf.set_text_color(160, 20, 30)
        else:
            pdf.set_font(active_font, size=12)
            pdf.set_text_color(20, 50, 120)

        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines:
            pdf.multi_cell(0, 7.5, text=line, new_x="LMARGIN", new_y="NEXT", align=pdf_align)
            pdf.ln(2)

        pdf.ln(4)

    raw_pdf_bytes = bytes(pdf.output())
    try:
        import uuid
        doc = fitz.open("pdf", raw_pdf_bytes)
        doc.set_metadata({
            "title": display_title,
            "author": "Samshodhana Mandiram",
            "subject": display_title,
            "creator": "Samshodhana Mandiram Digital Library",
            "producer": "PyMuPDF"
        })
        enc_bytes = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256,
            permissions=fitz.PDF_PERM_PRINT,
            owner_pw=uuid.uuid4().hex
        )
        doc.close()
        return enc_bytes
    except Exception as e:
        app.logger.warning(f"Failed to encrypt custom PDF permissions: {e}")
        return raw_pdf_bytes


@app.route('/api/v1/download_custom_pdf', methods=['POST'])
def download_custom_pdf():
    """Generates and streams a custom PDF document containing only the user-selected commentary levels."""
    from ai_search import load_book_full_text
    data = request.json or {}
    book_name = data.get('book_name', '').strip()
    selected_levels = data.get('selected_levels', [])
    font_choice = data.get('font_choice', 'sanskrit_text')
    align_choice = data.get('align_choice', 'center')
    script_choice = data.get('script_choice') or data.get('script') or 'sa'
    
    if not book_name:
        return jsonify({'error': 'Book name is required'}), 400
        
    upload_folder = app.config.get('UPLOAD_FOLDER', os.path.join(APP_DIR, 'uploads'))
    folder_path = os.path.join(upload_folder, book_name)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Book folder not found'}), 404
        
    full_text, err = load_book_full_text(book_name, upload_folder)
    if err or not full_text:
        return jsonify({'error': err or 'No text content available'}), 404
        
    metadata = get_metadata_from_folder(folder_path)
    levels_map = metadata.get('levels', {})
    blocks = parse_sdl_blocks(full_text)
    
    if selected_levels:
        selected_set = set(map(str, selected_levels))
        filtered_blocks = []
        for b in blocks:
            code = b['level']
            if any(code == sel or code.startswith(sel + '.') or sel.startswith(code + '.') for sel in selected_set):
                filtered_blocks.append(b)
        blocks = filtered_blocks

    try:
        pdf_bytes = generate_custom_pdf_bytes(book_name, blocks, levels_map, font_choice=font_choice, align_choice=align_choice, script_choice=script_choice)
        buf = io.BytesIO(pdf_bytes)
        buf.seek(0)
        suffix = f"_{script_choice}" if script_choice and script_choice != 'sa' else ""
        return send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{book_name}_custom{suffix}.pdf"
        )
    except Exception as e:
        app.logger.error(f"Custom PDF Generation Error: {e}")
        return jsonify({'error': f'Failed to generate custom PDF: {str(e)}'}), 500



@app.route('/admin/feedback')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_feedback_page():
    """Dedicated feedback report page"""
    can_manage = session.get('admin_role') == 'super' or 'PERM_MANAGE_FEEDBACK' in session.get('admin_permissions', [])
    return render_template('admin/feedback.html', 
                           can_manage_feedback=can_manage)

@app.route('/admin/feedback/<book_id>')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_view_feedback(book_id):
    """View paginated and searchable comments for a specific book"""
    page = int(request.args.get('page', 1))
    q_comment = request.args.get('q_comment', '').strip().lower()
    per_page = 20
    
    feedback_data = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass
            
    book_feedback = feedback_data.get(book_id, {'up': 0, 'down': 0, 'comments': []})
    all_comments = book_feedback.get('comments', [])
    
    # Filter by comment text or page number
    if q_comment:
        filtered = []
        for c in all_comments:
            text_match = q_comment in c.get('text', '').lower()
            page_match = q_comment in str(c.get('page', '')).lower()
            if text_match or page_match:
                filtered.append(c)
        all_comments = filtered

    # Reverse so newest are first
    all_comments = all_comments[::-1]
    
    total = len(all_comments)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages or 1))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_comments = all_comments[start_idx:end_idx]
    
    return jsonify({
        'book_id': book_id,
        'up': book_feedback.get('up', 0),
        'down': book_feedback.get('down', 0),
        'comments': paginated_comments,
        'total_comments': total,
        'page': page,
        'total_pages': total_pages
    })

@app.route('/admin/api/feedback_all')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_feedback_all():
    """Retrieve feedback for all books with search and pagination"""
    q = request.args.get('q', '').strip().lower()
    page = int(request.args.get('page', 1))
    per_page = 10
    
    feedback_data = {}
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass
            
    # Convert to list and filter
    report = []
    for book_id, data in feedback_data.items():
        if not q or q in book_id.lower():
            report.append({
                'book_id': book_id,
                'up': data.get('up', 0),
                'down': data.get('down', 0),
                'comments': data.get('comments', [])
            })
    
    # Sort by total interactions (up + down) descending
    report.sort(key=lambda x: (x['up'] + x['down']), reverse=True)
    
    # Pagination
    total = len(report)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages or 1))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_report = report[start_idx:end_idx]
    
    return jsonify({
        'data': paginated_report,
        'page': page,
        'total_pages': total_pages,
        'total_items': total
    })


@app.route('/admin/api/quiz-feedback/all')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_quiz_feedback_all():
    """Retrieve feedback for all quiz questions with search and pagination"""
    q = request.args.get('q', '').strip().lower()
    page = int(request.args.get('page', 1))
    per_page = 10

    raw_summary = quiz_db.get_quiz_feedback_summary()

    report = []
    for item in raw_summary:
        matches = False
        if not q:
            matches = True
        else:
            matches = (
                q in item['question_text'].lower() or
                q in item['subject'].lower() or
                q in item['level'].lower() or
                q in str(item['question_id'])
            )
        if matches:
            report.append(item)

    # Compute totals across the full filtered report before pagination
    total_up = sum(item['up'] for item in report)
    total_down = sum(item['down'] for item in report)

    total = len(report)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages or 1))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_report = report[start_idx:end_idx]

    return jsonify({
        'data': paginated_report,
        'page': page,
        'total_pages': total_pages,
        'total_items': total,
        'total_up': total_up,
        'total_down': total_down
    })


@app.route('/admin/api/quiz-feedback/<int:question_id>')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_quiz_feedback_details(question_id):
    """Retrieve paginated and searchable comments for a specific quiz question"""
    page = int(request.args.get('page', 1))
    q_comment = request.args.get('q_comment', '').strip().lower()
    per_page = 20

    details = quiz_db.get_quiz_feedback_details(question_id)
    all_comments = details.get('comments', [])

    if q_comment:
        all_comments = [
            c for c in all_comments
            if q_comment in c.get('text', '').lower() or q_comment in c.get('user', '').lower()
        ]

    total = len(all_comments)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages or 1))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_comments = all_comments[start_idx:end_idx]

    return jsonify({
        'question_id': question_id,
        'up': details.get('up', 0),
        'down': details.get('down', 0),
        'comments': paginated_comments,
        'total_comments': total,
        'page': page,
        'total_pages': total_pages
    })


@app.route('/admin/api/quiz-feedback/clear', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_FEEDBACK')
def admin_api_quiz_feedback_clear():
    """Clear feedback for a specific quiz question or all quiz questions"""
    data = request.get_json() or {}
    question_id = data.get('question_id')

    if question_id:
        try:
            question_id = int(question_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Invalid question ID format.'}), 400

    success = quiz_db.clear_quiz_feedback(question_id)
    if success:
        return jsonify({'success': True, 'message': 'Quiz feedback cleared successfully.'})
    
    return jsonify({'success': False, 'message': 'Failed to clear quiz feedback.'}), 500


@app.route('/admin/api/quiz-results/all')
@login_required
@permission_required('PERM_MANAGE_QUIZ')
def admin_api_quiz_results_all():
    """Retrieve all user and guest quiz attempt logs with search and pagination"""
    q = request.args.get('q', '').strip().lower()
    page = int(request.args.get('page', 1))
    per_page = 20

    raw_results = quiz_db.get_all_quiz_results()
    users_list = common_db.get_all_users()
    user_map = {u['id']: u['display_name'] for u in users_list}

    report = []
    unique_candidates = set()
    total_percentage_sum = 0

    for item in raw_results:
        user_id = item['user_id']
        display_name = ''
        if user_id > 0:
            display_name = user_map.get(user_id, f"User #{user_id}")
            unique_candidates.add(f"u_{user_id}")
        else:
            display_name = f"Guest: {item['guest_name'] or 'Candidate'}"
            unique_candidates.add(f"g_{display_name}")
        
        total_percentage_sum += item['percentage']

        matches = False
        if not q:
            matches = True
        else:
            matches = (
                q in display_name.lower() or
                q in item['subject'].lower() or
                q in item['level'].lower() or
                q in item['lang'].lower() or
                q in str(item['id'])
            )
        if matches:
            report.append({
                'id': item['id'],
                'user_id': user_id,
                'display_name': display_name,
                'subject': item['subject'],
                'level': item['level'],
                'score': item['score'],
                'total': item['total'],
                'percentage': item['percentage'],
                'lang': item['lang'],
                'taken_at': item['taken_at']
            })

    total = len(report)
    total_pages = math.ceil(total / per_page)
    page = max(1, min(page, total_pages or 1))

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_report = report[start_idx:end_idx]

    avg_pct = round(total_percentage_sum / len(raw_results)) if raw_results else 0

    return jsonify({
        'data': paginated_report,
        'page': page,
        'total_pages': total_pages,
        'total_items': total,
        'total_attempts': len(raw_results),
        'avg_percentage': avg_pct,
        'unique_candidates': len(unique_candidates)
    })


@app.route('/admin/api/quiz-results/delete/<int:result_id>', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_QUIZ')
def admin_api_quiz_result_delete(result_id):
    """Delete a single quiz result log"""
    success = quiz_db.delete_quiz_result(result_id)
    if success:
        return jsonify({'success': True, 'message': 'Quiz result deleted successfully.'})
    return jsonify({'success': False, 'message': 'Failed to delete quiz result.'}), 500


@app.route('/admin/api/quiz-results/clear', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_QUIZ')
def admin_api_quiz_results_clear():
    """Clear all quiz result logs from the database"""
    success = quiz_db.clear_all_quiz_results()
    if success:
        return jsonify({'success': True, 'message': 'All quiz results cleared successfully.'})
    return jsonify({'success': False, 'message': 'Failed to clear quiz results.'}), 500


@app.route('/admin/api/quiz-results/export/json')
@login_required
@permission_required('PERM_MANAGE_QUIZ')
def admin_api_quiz_results_export_json():
    """Export all quiz results as a JSON file download"""
    raw_results = quiz_db.get_all_quiz_results()
    users_list = common_db.get_all_users()
    user_map = {u['id']: u['display_name'] for u in users_list}

    data = []
    for item in raw_results:
        user_id = item['user_id']
        display_name = user_map.get(user_id, f"User #{user_id}") if user_id > 0 else f"Guest: {item['guest_name'] or 'Candidate'}"
        data.append({
            'id': item['id'],
            'user_id': user_id,
            'display_name': display_name,
            'subject': item['subject'],
            'level': item['level'],
            'score': item['score'],
            'total': item['total'],
            'percentage': item['percentage'],
            'lang': item['lang'],
            'taken_at': item['taken_at']
        })

    buf = io.BytesIO(json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='quiz_results_export.json',
        mimetype='application/json'
    )


@app.route('/admin/api/quiz-results/export/csv')
@login_required
@permission_required('PERM_MANAGE_QUIZ')
def admin_api_quiz_results_export_csv():
    """Export all quiz results as a CSV file download"""
    raw_results = quiz_db.get_all_quiz_results()
    users_list = common_db.get_all_users()
    user_map = {u['id']: u['display_name'] for u in users_list}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'User ID', 'Candidate Name', 'Subject', 'Level', 'Score', 'Total', 'Percentage', 'Language', 'Taken At'])

    for item in raw_results:
        user_id = item['user_id']
        display_name = user_map.get(user_id, f"User #{user_id}") if user_id > 0 else f"Guest: {item['guest_name'] or 'Candidate'}"
        writer.writerow([
            item['id'],
            user_id,
            display_name,
            item['subject'],
            item['level'],
            item['score'],
            item['total'],
            item['percentage'],
            item['lang'],
            item['taken_at']
        ])

    buf = io.BytesIO(output.getvalue().encode('utf-8-sig'))  # utf-8-sig for Excel compatibility
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='quiz_results_export.csv',
        mimetype='text/csv'
    )


@app.route('/admin/api/quiz-feedback/export/json')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_quiz_feedback_export_json():
    """Export all quiz feedback as a JSON file."""
    raw = quiz_db.get_quiz_feedback_summary()
    # Enrich each item with the full comment list
    export_rows = []
    for item in raw:
        details = quiz_db.get_quiz_feedback_details(item['question_id'])
        export_rows.append({
            'question_id': item['question_id'],
            'question_text': item['question_text'],
            'subject': item['subject'],
            'level': item['level'],
            'up_votes': item['up'],
            'down_votes': item['down'],
            'comments': details.get('comments', [])
        })
    buf = io.BytesIO(json.dumps(export_rows, indent=2, ensure_ascii=False).encode('utf-8'))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='quiz_feedback_export.json',
        mimetype='application/json'
    )


@app.route('/admin/api/quiz-feedback/export/csv')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_quiz_feedback_export_csv():
    """Export all quiz feedback as a CSV file (one row per vote/comment)."""
    raw = quiz_db.get_quiz_feedback_summary()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['question_id', 'question_text', 'subject', 'level', 'vote', 'comment', 'user', 'created_at'])
    for item in raw:
        details = quiz_db.get_quiz_feedback_details(item['question_id'])
        for c in details.get('comments', []):
            writer.writerow([
                item['question_id'],
                item['question_text'],
                item['subject'],
                item['level'],
                c.get('vote', ''),
                c.get('text', ''),
                c.get('user', ''),
                c.get('time', '')
            ])
    buf = io.BytesIO(output.getvalue().encode('utf-8-sig'))  # utf-8-sig for Excel compatibility
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name='quiz_feedback_export.csv',
        mimetype='text/csv'
    )


@app.route('/admin/api/quiz-feedback/import', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_FEEDBACK')
def admin_api_quiz_feedback_import():
    """Import quiz feedback from a previously exported JSON file.
    Accepts a JSON array of feedback objects, each with question_id, vote,
    and optional comments fields. Duplicate rows are simply appended.
    """
    data = request.get_json() or {}
    rows = data.get('rows', [])
    if not isinstance(rows, list) or len(rows) == 0:
        return jsonify({'success': False, 'message': 'No feedback rows provided.'}), 400

    imported = 0
    errors = []
    for i, row in enumerate(rows):
        try:
            q_id = int(row.get('question_id', 0))
            vote = str(row.get('vote', '')).strip().lower()
            comment = row.get('comment') or row.get('text') or row.get('comments') or None
            if isinstance(comment, list):
                comment = None  # skip summary-level imports; need flat rows
            if q_id <= 0 or vote not in ('up', 'down'):
                errors.append(f'Row {i + 1}: invalid question_id or vote value.')
                continue
            # user_id is unknown on import — store as NULL
            quiz_db.save_quiz_feedback(q_id, None, vote, comment if comment else None)
            imported += 1
        except Exception as e:
            errors.append(f'Row {i + 1}: {str(e)}')

    return jsonify({
        'success': True,
        'imported': imported,
        'errors': errors
    })


@app.route('/admin/api/feedback/export')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_feedback_export_all():
    """Export all feedback as JSON"""
    if os.path.exists(FEEDBACK_FILE):
        return send_file(FEEDBACK_FILE, as_attachment=True, download_name='all_feedback.json')
    return jsonify({'error': 'No feedback file found'}), 404

@app.route('/admin/api/feedback/export/<book_id>')
@login_required
@permission_required('PERM_VIEW_FEEDBACK')
def admin_api_feedback_export_book(book_id):
    """Export feedback for a specific book as JSON"""
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
            if book_id in all_data:
                # Create a temporary file for the specific book feedback
                temp_fd, temp_path = tempfile.mkstemp(suffix='.json')
                with os.fdopen(temp_fd, 'w', encoding='utf-8') as tf:
                    json.dump({book_id: all_data[book_id]}, tf, indent=2)
                
                return send_file(temp_path, as_attachment=True, download_name=f'feedback_{book_id}.json')
        except:
            pass
    return jsonify({'error': 'Feedback not found for this book'}), 404

@app.route('/admin/api/feedback/clear', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_FEEDBACK')
def admin_api_feedback_clear():
    """Clear feedback for one or all books"""
    # Bug #13 fix: use get_json() or {} to prevent AttributeError on malformed body
    data = request.get_json(silent=True) or {}
    book_id = data.get('book_id')  # If None, clear all
    
    if not book_id:
        # Clear all
        if os.path.exists(FEEDBACK_FILE):
            os.remove(FEEDBACK_FILE)
        return jsonify({'success': True, 'message': 'All feedback cleared'})
    else:
        # Clear specific book
        if os.path.exists(FEEDBACK_FILE):
            try:
                with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
                if book_id in all_data:
                    del all_data[book_id]
                    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
                        json.dump(all_data, f, indent=2)
                return jsonify({'success': True, 'message': f'Feedback for {book_id} cleared'})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)})
    return jsonify({'success': True})

@app.route('/admin/api/feedback/import', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_FEEDBACK')
def admin_api_feedback_import():
    """Import feedback from JSON file (Merge strategy)"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename.endswith('.json'):
        return jsonify({'error': 'Please upload a JSON file'}), 400
        
    try:
        new_data = json.load(file)
        if not isinstance(new_data, dict):
            return jsonify({'error': 'Invalid feedback JSON format'}), 400
            
        current_data = {}
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        
        # Merge logic
        for book_id, data in new_data.items():
            if book_id not in current_data:
                current_data[book_id] = data
            else:
                # Merge counts and comments
                current_data[book_id]['up'] += data.get('up', 0)
                current_data[book_id]['down'] += data.get('down', 0)
                current_data[book_id]['comments'].extend(data.get('comments', []))
                
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(current_data, f, indent=2)
            
        return jsonify({'success': True, 'message': 'Feedback imported and merged successfully'})
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


    
@app.route('/admin/refresh_cache', methods=['POST'])
@login_required
def admin_refresh_cache():
    """Clear and refresh various application caches"""
    if session.get('admin_role') != 'super':
        return render_template('admin/forbidden.html'), 403
    try:
        # 1. Clear Browse Cache
        if os.path.exists(BROWSE_CACHE_FILE):
            try:
                os.remove(BROWSE_CACHE_FILE)
            except:
                pass
            
        # 2. Clear File Content Cache
        global _file_content_cache
        _file_content_cache = {}
        
        # 3. Clear Catalog Cache
        global CATALOG_METADATA_CACHE
        CATALOG_METADATA_CACHE = {}
        if os.path.exists(CATALOG_CACHE_FILE):
            try:
                os.remove(CATALOG_CACHE_FILE)
            except:
                pass
        
        # 4. Trigger Background Warmup
        threading.Thread(target=warmup_catalog_cache, daemon=True).start()
        
        return jsonify({'success': True, 'message': 'Cache refresh started'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/cache_status')
@login_required
def admin_cache_status():
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Unauthorized'}), 403
    
    status = "IDLE"
    if os.path.exists(WARMUP_STATUS_FILE):
        try:
            with open(WARMUP_STATUS_FILE, 'r', encoding='utf-8') as f:
                status = f.read().strip()
        except:
            pass
            
    return jsonify({
        'status': status,
        'running': _warmup_running
    })


# =============================================================================
# COMMUNITY CONTRIBUTIONS & NOTEPAD-STYLE IN-READER EDITING
# =============================================================================

_CONTRIBUTE_IP_LIMITS = {}
_CONTRIBUTE_RATE_LIMIT_MAX = 20  # Max 20 uploads per hour per IP

def _check_contribute_rate_limit(ip):
    now = time.time()
    cutoff = now - 3600
    times = [t for t in _CONTRIBUTE_IP_LIMITS.get(ip, []) if t > cutoff]
    if len(times) >= _CONTRIBUTE_RATE_LIMIT_MAX:
        return False
    times.append(now)
    _CONTRIBUTE_IP_LIMITS[ip] = times
    return True

def create_community_book_from_text(book_name, content, tags='', author='', contributor='', source='', published=True, chars_per_page=2000):
    """
    Creates or safely disambiguates a community contributed book in UPLOAD_FOLDER.
    Formats pages if needed with {[ (N) ]}, compresses into .sdl, writes metadata.txt with 'Verification: unverified'.
    """
    import zstandard as zstd
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Strip dangerous filesystem characters while preserving Sanskrit/Unicode
    safe_name = re.sub(r'[\\/*?:"<>|]', '', book_name).strip()
    if not safe_name:
        safe_name = "Community_Book_" + str(int(time.time()))
        
    dest_path = os.path.join(upload_folder, safe_name)
    # Disambiguate if existing book folder exists so we never overwrite existing books!
    if os.path.exists(dest_path):
        counter = 2
        while os.path.exists(os.path.join(upload_folder, f"{safe_name} (Community {counter})")):
            counter += 1
        safe_name = f"{safe_name} (Community {counter})"
        dest_path = os.path.join(upload_folder, safe_name)
        
    os.makedirs(dest_path, exist_ok=True)
    
    # Format pages if not already formatted with {[ (N) ]}
    if '{[(' in content:
        formatted_text = content
    else:
        pages = split_text_into_pages(content, chars_per_page)
        if not pages:
            pages = [content]
        formatted_text = ""
        for i, page_content in enumerate(pages):
            formatted_text += f"{{[({i+1})]}}\n{page_content}\n\n"
            
    # Clean tags against taxonomy
    cleaned_tags = sanitize_tags_against_taxonomy(tags.strip(), published=published) if tags else ""
    
    # Save metadata.txt
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(os.path.join(dest_path, 'metadata.txt'), 'w', encoding='utf-8') as f:
        f.write(f"Source: {source.strip()}\n")
        f.write(f"Tags: {cleaned_tags}\n")
        if author:
            f.write(f"Author: {author.strip()}\n")
        f.write(f"Verification: unverified\n")
        if contributor:
            f.write(f"Contributor: {contributor.strip()}\n")
        f.write(f"Published: {'true' if published else 'false'}\n")
        f.write(f"Notes: Community contributed on {now_str}\n")
        
    # Compress into .sdl
    sdl_data = bytearray(b'SDL\x03')
    cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
    sdl_data.extend(cctx.compress(formatted_text.encode('utf-8')))
    with open(os.path.join(dest_path, f"{safe_name}.sdl"), 'wb') as f:
        f.write(sdl_data)
        
    # Update catalog cache
    CATALOG_METADATA_CACHE[safe_name] = {
        'source': source.strip(),
        'tags': cleaned_tags,
        'subbooks': [],
        'subbooks_raw': '',
        'levels': {},
        'levels_raw': '',
        'notes': f"Community contributed on {now_str}",
        'published': published,
        'verification': 'unverified',
        'is_community': True,
        'contributor': contributor.strip(),
        'author': author.strip()
    }
    save_catalog_cache()
    return safe_name

def apply_approved_page_edit(book_name, page_number, new_text):
    """
    Applies an approved page edit to the book's .sdl or .txt file in UPLOAD_FOLDER.
    Safely substitutes the targeted page text, updates caches, and recalculates notes if applicable.
    """
    import zstandard as zstd
    upload_folder = app.config['UPLOAD_FOLDER']
    folder_path = os.path.join(upload_folder, book_name)
    if not os.path.exists(folder_path):
        return False, "Book folder not found"
        
    txt_files = [f for f in sorted(os.listdir(folder_path)) 
                if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
    if not txt_files:
        return False, "No book text file found"
        
    target_file = txt_files[0]
    file_path = os.path.join(folder_path, target_file)
    
    try:
        full_text = get_cached_file_content(file_path)
    except Exception as e:
        return False, f"Failed to read file: {e}"
        
    page_marker = f"{{[({page_number})]}}"
    if page_marker in full_text:
        start_idx = full_text.find(page_marker)
        content_start = start_idx + len(page_marker)
        next_match = re.search(r'\{\[\(\d+\)\]\}', full_text[content_start:])
        if next_match:
            end_idx = content_start + next_match.start()
            new_full_text = full_text[:content_start] + "\n" + new_text.strip() + "\n\n" + full_text[end_idx:]
        else:
            new_full_text = full_text[:content_start] + "\n" + new_text.strip() + "\n"
    else:
        chunks = split_text_into_smart_chunks(full_text.strip(), target_chars=8000)
        if 1 <= page_number <= len(chunks):
            chunks[page_number - 1] = new_text.strip()
            new_full_text = "\n\n".join(chunks)
        else:
            new_full_text = new_text.strip()

    try:
        if file_path.endswith('.sdl'):
            sdl_data = bytearray(b'SDL\x03')
            cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
            sdl_data.extend(cctx.compress(new_full_text.encode('utf-8')))
            with open(file_path, 'wb') as f:
                f.write(sdl_data)
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_full_text)
                
        # Invalidate and refresh cache
        mtime = os.path.getmtime(file_path)
        for k in list(_file_content_cache.keys()):
            if k.startswith(file_path):
                del _file_content_cache[k]
        _file_content_cache[f"{file_path}:{mtime}"] = new_full_text
        return True, "Successfully applied edit"
    except Exception as e:
        return False, f"Failed to write file: {e}"


@app.route('/upload-book')
@app.route('/contribute')
def contribute_page():
    """Public page for contributing books without login"""
    import random
    n1 = random.randint(2, 9)
    n2 = random.randint(1, 9)
    session['math_challenge'] = n1 + n2
    return render_template('public/contribute.html', math_n1=n1, math_n2=n2)


@app.route('/api/contribute/challenge')
def api_contribute_challenge():
    """Refresh math challenge numbers"""
    import random
    n1 = random.randint(2, 9)
    n2 = random.randint(1, 9)
    session['math_challenge'] = n1 + n2
    return jsonify({'n1': n1, 'n2': n2})


@app.route('/api/contribute/upload', methods=['POST'])
def api_contribute_upload():
    """Handle public book upload without login (PDF or Text)"""
    client_ip = request.remote_addr or '127.0.0.1'
    if not _check_contribute_rate_limit(client_ip):
        return jsonify({'error': 'Rate limit exceeded. Please wait a few minutes before contributing again.'}), 429

    # 1. Anti-bot honeypot check
    honeypot = request.form.get('website_url', '').strip()
    if honeypot:
        return jsonify({'error': 'Submission rejected.'}), 400

    # 2. Math challenge check
    math_ans = request.form.get('math_answer', '').strip()
    expected = session.get('math_challenge')
    if expected is not None:
        try:
            if int(math_ans) != int(expected):
                return jsonify({'error': 'Incorrect anti-bot math verification answer. Please try again.'}), 400
        except:
            return jsonify({'error': 'Invalid math verification answer.'}), 400
    # Reset challenge after check
    session.pop('math_challenge', None)

    book_name = request.form.get('book_name', '').strip()
    author = request.form.get('author', '').strip()
    tags = request.form.get('tags', '').strip()
    contributor = request.form.get('contributor', '').strip()
    source = request.form.get('source', '').strip()
    upload_type = request.form.get('upload_type', 'text') # 'text' or 'pdf'

    if not book_name:
        return jsonify({'error': 'Book title is required.'}), 400

    if upload_type == 'text':
        content = request.form.get('content', '').strip()
        text_file = request.files.get('text_file')
        if text_file and text_file.filename:
            try:
                content = text_file.read().decode('utf-8', errors='ignore')
            except Exception as e:
                return jsonify({'error': f'Failed to read uploaded text file: {e}'}), 400

        if not content:
            return jsonify({'error': 'Please provide book content by typing/pasting text or uploading a .txt file.'}), 400

        created_name = create_community_book_from_text(
            book_name=book_name,
            content=content,
            tags=tags,
            author=author,
            contributor=contributor,
            source=source
        )
        return jsonify({
            'success': True,
            'book_name': created_name,
            'redirect_url': f"/reader/{urllib.parse.quote(created_name)}"
        })

    elif upload_type == 'pdf':
        pdf_file = request.files.get('pdf_file')
        if not pdf_file or not pdf_file.filename:
            return jsonify({'error': 'Please choose a PDF file to upload.'}), 400

        # Save to temp file for inspection
        import tempfile
        temp_dir = tempfile.mkdtemp()
        temp_pdf_path = os.path.join(temp_dir, secure_filename(pdf_file.filename) or 'upload.pdf')
        pdf_file.save(temp_pdf_path)

        try:
            import fitz
            doc = fitz.open(temp_pdf_path)
            num_pages = len(doc)
            extracted_pages = []
            total_chars = 0
            for p in doc:
                txt = p.get_text().strip()
                total_chars += len(txt)
                extracted_pages.append(txt)
            doc.close()

            # If the PDF contains searchable/embedded digital text:
            if total_chars > 50 * max(1, num_pages):
                formatted_text = ""
                for i, p_txt in enumerate(extracted_pages):
                    formatted_text += f"{{[({i+1})]}}\n{p_txt}\n\n"
                created_name = create_community_book_from_text(
                    book_name=book_name,
                    content=formatted_text,
                    tags=tags,
                    author=author,
                    contributor=contributor,
                    source=source
                )
                try: shutil.rmtree(temp_dir)
                except: pass
                return jsonify({
                    'success': True,
                    'book_name': created_name,
                    'redirect_url': f"/reader/{urllib.parse.quote(created_name)}"
                })
            else:
                # Scanned image PDF: queue for Google Drive OCR
                from ocr import TaskState, OCR_JOB_QUEUE, start_ocr_worker_if_needed, OCR_DIR, sanitize_upload_filename
                task_id = str(uuid.uuid4())
                ocr_task_dir = os.path.join(OCR_DIR, f"ocr_task_{task_id}")
                os.makedirs(ocr_task_dir, exist_ok=True)
                saved_pdf = os.path.join(ocr_task_dir, sanitize_upload_filename(pdf_file.filename))
                shutil.copy2(temp_pdf_path, saved_pdf)
                try: shutil.rmtree(temp_dir)
                except: pass

                state = TaskState(task_id)
                state.update(status='Queued', book_name=book_name)
                start_ocr_worker_if_needed()
                layout_options = {
                    'insert_page_breaks': True,
                    'page_marker_format': '{[({page})]}',
                    'ocr_lang': 'auto',
                    'auto_publish_book_metadata': {
                        'book_name': book_name,
                        'author': author,
                        'tags': tags,
                        'contributor': contributor,
                        'source': source
                    }
                }
                OCR_JOB_QUEUE.put((task_id, [saved_pdf], 'text', layout_options))
                return jsonify({
                    'success': True,
                    'needs_ocr': True,
                    'task_id': task_id,
                    'book_name': book_name,
                    'message': 'Scanned PDF detected. OCR is running in the background.'
                })
        except Exception as e:
            try: shutil.rmtree(temp_dir)
            except: pass
            return jsonify({'error': f'Failed to process PDF: {str(e)}'}), 500

    return jsonify({'error': 'Unsupported upload type.'}), 400


@app.route('/api/contribute/publish-ocr', methods=['POST'])
def api_contribute_publish_ocr():
    """Publish the completed result of an OCR task directly as a library book"""
    data = request.get_json() or {}
    task_id = data.get('task_id', '').strip()
    book_name = data.get('book_name', '').strip()
    author = data.get('author', '').strip()
    tags = data.get('tags', '').strip()
    contributor = data.get('contributor', '').strip()
    source = data.get('source', '').strip()

    if not task_id or not book_name:
        return jsonify({'error': 'Task ID and book title are required.'}), 400

    from ocr import TaskState
    state = TaskState(task_id)
    task = state.get()
    if not task or not task.get('done'):
        return jsonify({'error': 'OCR task is not yet complete.'}), 400

    result_text = task.get('result_text', '')
    if not result_text:
        # Try reading result file
        res_file = task.get('result_file')
        if res_file and os.path.exists(res_file) and res_file.endswith('.txt'):
            try:
                with open(res_file, 'r', encoding='utf-8') as f:
                    result_text = f.read()
            except:
                pass

    if not result_text:
        return jsonify({'error': 'No OCR text found to publish.'}), 400

    created_name = create_community_book_from_text(
        book_name=book_name,
        content=result_text,
        tags=tags,
        author=author,
        contributor=contributor,
        source=source
    )
    return jsonify({
        'success': True,
        'book_name': created_name,
        'reader_url': f"/reader/{urllib.parse.quote(created_name)}"
    })


@app.route('/api/book/edit-suggestion', methods=['POST'])
def api_submit_edit_suggestion():
    """Receive a user's edit suggestion for a book page"""
    data = request.get_json() or {}
    book_name = data.get('book_name', '').strip()
    page = int(data.get('page', 1))
    edited_text = data.get('edited_text', '').strip()
    client_token = (request.headers.get('X-Client-Token') or data.get('client_token', '') or request.cookies.get('sdl_client_token', '') or (f"user_{session['user_id']}" if session.get('user_id') else '')).strip()
    contributor_name = data.get('contributor_name', '').strip()
    if not contributor_name:
        contributor_name = session.get('user_display_name') or session.get('admin_username') or session.get('username') or 'Community Contributor'
    contributor_email = (data.get('contributor_email', '') or session.get('user_email', '') or session.get('email', '')).strip()
    edit_notes = data.get('edit_notes', '').strip()
    original_text = data.get('original_text', '').strip()

    # Clean HTML if pasted into contenteditable
    if edited_text and '<' in edited_text and '>' in edited_text:
        import re, html
        cleaned = re.sub(r'<\s*br\s*/?>', '\n', edited_text, flags=re.IGNORECASE)
        cleaned = re.sub(r'</div>\s*<div>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        edited_text = html.unescape(cleaned).strip()

    if not book_name or not edited_text or not client_token:
        return jsonify({'success': False, 'error': 'Book name, edited text, and client token are required'}), 400

    curr_ocr, _, _ = get_book_page_ocr(book_name, page)
    official_original = (curr_ocr or '').strip()
    if not original_text:
        original_text = official_original

    # If the user's text matches the original official book text, clear any pending edit draft
    if official_original and edited_text.strip() == official_original:
        from db.common_db import get_db
        conn = get_db()
        try:
            conn.execute(
                "DELETE FROM community_book_edits WHERE book_name = ? AND page_number = ? AND client_token = ? AND status = 'pending'",
                (book_name, page, client_token)
            )
            conn.commit()
        finally:
            conn.close()
        return jsonify({
            'success': True,
            'reverted_to_official': True,
            'message': 'Text matches official version. Pending edit cleared.'
        })

    from db.common_db import submit_community_edit
    result = submit_community_edit(
        book_name=book_name,
        page_number=page,
        client_token=client_token,
        edited_text=edited_text,
        original_text=official_original or original_text,
        contributor_name=contributor_name,
        contributor_email=contributor_email,
        edit_notes=edit_notes
    )

    if not result:
        return jsonify({'success': False, 'error': 'Failed to record edit suggestion'}), 500

    if result == 'reverted':
        return jsonify({
            'success': True,
            'reverted_to_official': True,
            'message': 'Text matches official version. Pending edit cleared.'
        })

    return jsonify({
        'success': True,
        'edit_id': result,
        'message': 'Changes saved successfully!'
    })


@app.route('/api/book/edit-suggestion/cancel', methods=['POST'])
def api_cancel_edit_suggestion():
    """Cancel / delete a guest user's pending edit so they revert to official text"""
    data = request.get_json() or {}
    book_name = data.get('book_name', '').strip()
    page = int(data.get('page', 1))
    client_token = (data.get('client_token', '') or request.cookies.get('sdl_client_token', '') or (f"user_{session['user_id']}" if session.get('user_id') else '')).strip()
    if not book_name or not client_token:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400

    from db.common_db import get_db
    conn = get_db()
    try:
        conn.execute(
            "DELETE FROM community_book_edits WHERE book_name = ? AND page_number = ? AND client_token = ? AND status = 'pending'",
            (book_name, page, client_token)
        )
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


# =============================================================================
# ADMIN REVIEW QUEUE (MODERATION FOR COMMUNITY BOOKS & EDITS)
# =============================================================================

@app.route('/admin/review-queue')
@login_required
def admin_review_queue():
    """Library Admin Review Queue for proposed page edits & community-uploaded books"""
    filter_status = request.args.get('status', 'pending').strip().lower()
    from db.common_db import get_pending_edits, get_pending_edits_count
    
    edits = get_pending_edits(status=filter_status, limit=150)
    pending_count = get_pending_edits_count(status='pending')

    # Fetch community uploaded books
    all_books = get_all_books(bypass_cache=True, include_unpublished=True)
    community_books = [b for b in all_books if b.get('is_community')]

    return render_template(
        'admin/review_queue.html',
        edits=edits,
        pending_count=pending_count,
        filter_status=filter_status,
        community_books=community_books
    )


@app.route('/admin/review-queue/edit/<edit_id>/action', methods=['POST'])
@login_required
def admin_review_edit_action(edit_id):
    """Approve or reject a community page edit"""
    data = request.get_json() or {}
    action = data.get('action', '').strip().lower() # 'approve' or 'reject'
    if action not in ('approve', 'reject'):
        return jsonify({'error': 'Invalid action'}), 400

    from db.common_db import get_community_edit_by_id, update_community_edit_status
    edit = get_community_edit_by_id(edit_id)
    if not edit:
        return jsonify({'error': 'Edit record not found'}), 404

    admin_user = session.get('admin_username', 'admin')
    if action == 'approve':
        success, msg = apply_approved_page_edit(edit['book_name'], edit['page_number'], edit['edited_text'])
        if not success:
            return jsonify({'error': f"Failed to apply edit to book file: {msg}"}), 500
        update_community_edit_status(edit_id, 'approved', reviewed_by=admin_user)
        log_change(admin_user, 'APPROVE', 'PAGE_EDIT', f"{edit['book_name']} p{edit['page_number']}")
        return jsonify({'success': True, 'message': 'Edit approved and applied to book successfully!'})
    else:
        update_community_edit_status(edit_id, 'rejected', reviewed_by=admin_user)
        log_change(admin_user, 'REJECT', 'PAGE_EDIT', f"{edit['book_name']} p{edit['page_number']}")
        return jsonify({'success': True, 'message': 'Edit rejected.'})


@app.route('/admin/verify-book/<path:book_name>', methods=['POST'])
@login_required
def admin_verify_book(book_name):
    """Verify a community book: change status from unverified to verified"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Book folder not found'}), 404

    metadata_path = os.path.join(folder_path, 'metadata.txt')
    if os.path.exists(metadata_path):
        lines = []
        found_verif = False
        with open(metadata_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('Verification:'):
                    lines.append('Verification: verified\n')
                    found_verif = True
                else:
                    lines.append(line)
        if not found_verif:
            lines.append('Verification: verified\n')
        with open(metadata_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    # Refresh catalog cache
    get_metadata_from_folder(folder_path, bypass_cache=True)
    save_catalog_cache()
    log_change(session.get('admin_username', 'admin'), 'VERIFY', 'BOOK', book_name)
    return jsonify({'success': True, 'message': f"'{book_name}' verified successfully!"})


@app.route('/admin/api/pending-edits-count')
@login_required
def admin_api_pending_edits_count():
    """API returning current pending count for admin header badges"""
    from db.common_db import get_pending_edits_count
    return jsonify({'count': get_pending_edits_count('pending')})




@app.route('/admin/upload-panel')
@login_required
@permission_required('PERM_ADD_BOOK')
def admin_upload_panel():
    """Render the upload panel page"""
    return render_template('admin/upload_panel.html')


@app.route('/admin/upload', methods=['POST'])
@login_required
@permission_required('PERM_ADD_BOOK')
def admin_upload():
    """Handle bulk folder upload (as ZIP)"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    published = request.form.get('status', 'published').strip().lower() == 'published'
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.zip'):
        return jsonify({'error': 'Please upload a ZIP file containing folders'}), 400
    
    try:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(zip_path)
        
        extract_dir = os.path.join(temp_dir, 'extracted')
        real_extract_dir = os.path.realpath(extract_dir)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                target_path = os.path.realpath(os.path.join(real_extract_dir, member.filename))
                if not target_path.startswith(real_extract_dir + os.sep) and target_path != real_extract_dir:
                    raise Exception(f"Unsafe ZIP entry detected: {member.filename}")
                zip_ref.extract(member, extract_dir)
        
        uploaded_count = 0
        skipped_duplicates = []
        upload_folder = app.config['UPLOAD_FOLDER']

        # --- Build a set of all archive Source links already on disk ---
        existing_source_links = set()
        if os.path.exists(upload_folder):
            for existing_folder in os.listdir(upload_folder):
                existing_folder_path = os.path.join(upload_folder, existing_folder)
                if not os.path.isdir(existing_folder_path):
                    continue
                existing_meta = get_metadata_from_folder(existing_folder_path)
                existing_source = existing_meta.get('source', '').strip().rstrip('/')
                if existing_source:
                    existing_source_links.add(existing_source.lower())

        # Recursively find all folders containing .txt files
        book_paths = []
        for root, dirs, files in os.walk(extract_dir):
            # Skip __MACOSX and hidden folders
            if '__MACOSX' in root or os.path.basename(root).startswith('.'):
                continue
                
            # Check for .txt or .sdl files (excluding system files)
            valid_files = [f for f in files if (f.endswith('.txt') or f.endswith('.sdl')) and not f.startswith('._')]
            
            if valid_files:
                book_paths.append(root)
                # If we found a book here, don't look inside it for more books
                # (Assume a folder with .txt files is a self-contained book)
                dirs[:] = []
        
        for book_path in book_paths:
            # Determine folder name
            if book_path == extract_dir:
                # If the root itself contains files, use zip filename
                folder_name = os.path.splitext(secure_filename(file.filename))[0]
            else:
                # Use the leaf directory name
                folder_name = os.path.basename(book_path)
            
            # Clean filename slightly but allow unicode
            folder_name = folder_name.strip()
            if not folder_name:
                continue

            # --- Duplicate check: read incoming book's metadata Source link ---
            incoming_meta_path = os.path.join(book_path, 'metadata.txt')
            incoming_source = ''
            if os.path.isfile(incoming_meta_path):
                try:
                    with open(incoming_meta_path, 'r', encoding='utf-8') as mf:
                        for line in mf:
                            if line.lower().startswith('source:'):
                                incoming_source = line.split(':', 1)[1].strip().rstrip('/')
                                break
                except Exception:
                    pass

            if incoming_source and incoming_source.lower() in existing_source_links:
                skipped_duplicates.append(folder_name)
                continue

            dest_path = os.path.join(upload_folder, folder_name)
            
            # If the folder exists with the same name, remove it first (update/overwrite behavior)
            is_update = False
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
                is_update = True
            
            shutil.copytree(book_path, dest_path)

            # Update or write metadata.txt with selection
            metadata = get_metadata_from_folder(dest_path, bypass_cache=True)
            metadata_path = os.path.join(dest_path, 'metadata.txt')
            try:
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    if metadata.get('source'):
                        f.write(f"Source: {metadata['source']}\n")
                    raw_tags = metadata.get('tags', '')
                    tags = sanitize_tags_against_taxonomy(raw_tags, published=published)
                    f.write(f"Tags: {tags}\n")

                    if metadata.get('levels_raw'):
                        f.write(f"Level: {metadata['levels_raw']}\n")
                    if metadata.get('notes'):
                        escaped_notes = metadata['notes'].replace('\r\n', '\n').replace('\n', '\\n')
                        f.write(f"Notes: {escaped_notes}\n")
                    f.write(f"Published: {'true' if published else 'false'}\n")
            except:
                pass

            # --- Auto-Convert to Zstd (.sdl) ---
            # If the book already has a .sdl file, we skip the conversion step
            has_native_sdl = any(f.endswith('.sdl') for f in os.listdir(dest_path))
            
            if not has_native_sdl:
                new_txt_files = [f for f in sorted(os.listdir(dest_path)) if f.endswith('.txt') and f.lower() != 'metadata.txt']
                if new_txt_files:
                    text_parts = []
                    for fname in new_txt_files:
                        try:
                            fpath = os.path.join(dest_path, fname)
                            with open(fpath, 'r', encoding='utf-8') as f:
                                text_parts.append(f.read())
                            os.remove(fpath)  # Delete the .txt file immediately to save space!
                        except Exception:
                            pass
                    
                    if text_parts:
                        text_content = '\n'.join(text_parts)
                        sdl_data = bytearray()
                        sdl_data.extend(b'SDL\x03')
                        cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
                        sdl_data.extend(cctx.compress(text_content.encode('utf-8')))
                        
                        sdl_path = os.path.join(dest_path, f"{folder_name}.sdl")
                        with open(sdl_path, 'wb') as sf:
                            sf.write(sdl_data)
            else:
                # If it already had .sdl, we still want to clean up any redundant .txt files
                for f in os.listdir(dest_path):
                    if f.endswith('.txt') and f.lower() != 'metadata.txt':
                        try:
                            os.remove(os.path.join(dest_path, f))
                        except:
                            pass
            # -----------------------------------

            uploaded_count += 1
            
            # Log the creation or update
            action = 'UPDATE' if is_update else 'CREATE'
            log_change(session.get('admin_username'), action, 'BOOK', folder_name)

            # Add newly uploaded source to the set so within-batch duplicates are also caught
            if incoming_source:
                existing_source_links.add(incoming_source.lower())
        
        shutil.rmtree(temp_dir)

        # Compose response message
        msg_parts = []
        if uploaded_count:
            msg_parts.append(f'Successfully uploaded {uploaded_count} folder(s)')
        if skipped_duplicates:
            msg_parts.append(
                f'Skipped {len(skipped_duplicates)} duplicate(s) (same archive link already exists)'
            )
        if not msg_parts:
            msg_parts.append('No new books were uploaded')

        return jsonify({
            'success': True,
            'message': '. '.join(msg_parts)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/upload-text', methods=['POST'])
@login_required
@permission_required('PERM_ADD_BOOK')
def admin_upload_text():
    """Handle raw text upload with automatic pagination"""
    data = request.json or {}
    book_name = data.get('book_name', '').strip()
    content = data.get('content', '').strip()
    chars_per_page = int(data.get('chars_per_page', 2000))
    published = data.get('status', 'published').strip().lower() == 'published'
    tags = sanitize_tags_against_taxonomy(data.get('tags', '').strip(), published=published)
    
    levels_raw = data.get('levels_raw', '').strip()
    
    if not book_name or not content:
        return jsonify({'error': 'Book name and content are required'}), 400
        
    # Split and format content into pages
    if chars_per_page == 0:
        formatted_text = content
        # Detect manual pages in the raw text by counting occurrences of '{[('
        num_pages = max(1, content.count('{[('))
    else:
        pages = split_text_into_pages(content, chars_per_page)
        if not pages:
            return jsonify({'error': 'Content resulted in 0 pages'}), 400
            
        # Format with page markers {[ (1) ]}
        formatted_text = ""
        for i, page_content in enumerate(pages):
            formatted_text += f"{{[({i+1})]}}\n{page_content}\n\n"
        num_pages = len(pages)
        
    # Create folder and save
    upload_folder = app.config['UPLOAD_FOLDER']
    
    # Sanitize name but allow Unicode (Sanskrit) - strip characters illegal in Windows paths
    safe_name = re.sub(r'[\\/*?:"<>|]', '', book_name).strip()
    if not safe_name:
        safe_name = "text_upload_" + str(int(time.time()))
        
    dest_path = os.path.join(upload_folder, safe_name)
    
    is_update = False
    if os.path.exists(dest_path):
        shutil.rmtree(dest_path)
        is_update = True
    os.makedirs(dest_path, exist_ok=True)
    
    # Save metadata (Source empty as requested)
    with open(os.path.join(dest_path, 'metadata.txt'), 'w', encoding='utf-8') as f:
        f.write(f"Source: \nTags: {tags}\n")
        if levels_raw:
            f.write(f"Level: {levels_raw}\n")
        f.write(f"Published: {'true' if published else 'false'}\n")
        
    # Compress to .sdl
    sdl_data = bytearray()
    sdl_data.extend(b'SDL\x03')
    cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
    sdl_data.extend(cctx.compress(formatted_text.encode('utf-8')))
    
    sdl_path = os.path.join(dest_path, f"{safe_name}.sdl")
    with open(sdl_path, 'wb') as sf:
        sf.write(sdl_data)
        
    action = 'UPDATE' if is_update else 'CREATE'
    log_change(session.get('admin_username'), action, 'BOOK', book_name)
    return jsonify({'success': True, 'message': f'Book "{book_name}" added successfully with {num_pages} pages.'})


@app.route('/admin/start_zip', methods=['POST'])
@login_required
@permission_required('PERM_DOWNLOAD_BOOKS')
def admin_start_zip():
    """Start background ZIP creation and return a task ID for progress polling"""
    export_format = request.form.get('format', 'txt')  # 'txt' or 'sdl'
    books_json = request.form.get('books')
    if not books_json:
        return jsonify({'error': 'No books selected'}), 400

    upload_folder = app.config['UPLOAD_FOLDER']
    if books_json == 'all':
        books = sorted(get_filtered_book_names(request.form))
    else:
        books = json.loads(books_json)
    task_id = str(uuid.uuid4())

    # Count total files first
    total_files = 0
    for book_name in books:
        folder_path = os.path.join(upload_folder, book_name)
        if os.path.isdir(folder_path):
            if export_format == 'sdl':
                total_files += 2  # 1 .sdl file + 1 metadata.txt
            else:
                for root, dirs, files in os.walk(folder_path):
                    total_files += len(files)

    # Dynamic download filename generation based on selected books
    if len(books) == 1:
        clean_name = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
        download_name = f"{clean_name}.zip" if clean_name else "book_export.zip"
    elif len(books) > 1 and books_json != 'all':
        clean_first = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
        download_name = f"{clean_first}_and_{len(books)-1}_others.zip" if clean_first else f"books_export_{len(books)}.zip"
    else:
        download_name = f"SDL_Library_Export_{datetime.now().strftime('%Y%m%d')}.zip"

    initial_task_state = {
        'status': 'preparing',
        'progress': 0,
        'total_files': total_files,
        'processed_files': 0,
        'error': None,
        'zip_path': None,
        'cancelled': False,
        'download_name': download_name
    }
    save_zip_task(task_id, initial_task_state)

    def build_zip():
        temp_zip_path = None
        try:
            fd, temp_zip_path = tempfile.mkstemp(suffix='.zip')
            os.close(fd)

            processed = 0
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_STORED) as zf:
                # Add the Converter GUI tool to the root of the ZIP
                # Robust path identification: Look for it in the same folder as sdl.py
                base_dir = os.path.dirname(os.path.abspath(__file__))
                tool_path = os.path.join(base_dir, 'sdl_converter_gui.pyw')
                
                if os.path.exists(tool_path):
                    zf.write(tool_path, "sdl_converter_gui.pyw")
                
                for book_name in books:
                    folder_path = os.path.join(upload_folder, book_name)
                    if not os.path.isdir(folder_path):
                        continue
                        
                    task_state = get_zip_task(task_id) or {}
                    if task_state.get('cancelled'):
                        raise InterruptedError('Cancelled by user')

                    if export_format == 'sdl':
                        # If exporting as SDL, see if we already have it natively!
                        native_sdl = [f for f in sorted(os.listdir(folder_path)) if f.endswith('.sdl')]
                        if native_sdl:
                            # It's already SDL natively! Just write it in a structured way.
                            zf.write(os.path.join(folder_path, native_sdl[0]), f"{book_name}/{native_sdl[0]}")
                            processed += 1
                        else:
                            # Combine old .txt into .sdl
                            text_parts = []
                            txt_files = [os.path.join(r, f) for r, d, fs in os.walk(folder_path) for f in sorted(fs) if f.endswith('.txt') and f.lower() != 'metadata.txt']
                            for txt_path in txt_files:
                                try:
                                    with open(txt_path, 'r', encoding='utf-8') as f:
                                        text_parts.append(f.read())
                                except Exception:
                                    pass
                            
                            if text_parts:
                                text_content = '\n'.join(text_parts)
                                sdl_data = bytearray()
                                sdl_data.extend(b'SDL\x03')
                                cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
                                sdl_data.extend(cctx.compress(text_content.encode('utf-8')))
                                zf.writestr(f"{book_name}/{book_name}.sdl", sdl_data)
                            processed += 1

                        # Add metadata in the same folder
                        meta_path = os.path.join(folder_path, 'metadata.txt')
                        if os.path.exists(meta_path):
                            folder_meta = get_metadata_from_folder(folder_path)
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta_content = f.read()
                            
                            levels_raw_val = folder_meta.get('levels_raw', '')
                            if 'Level:' not in meta_content and levels_raw_val:
                                meta_content = meta_content.strip() + f"\nLevel: {levels_raw_val}\n"
                            zf.writestr(f"{book_name}/metadata.txt", meta_content)
                        processed += 1
                        
                        if total_files > 0:
                            task_state['progress'] = int((processed / total_files) * 100)
                        task_state['processed_files'] = processed
                        save_zip_task(task_id, task_state)

                    else:
                        # Export as TXT
                        native_sdl = [f for f in sorted(os.listdir(folder_path)) if f.endswith('.sdl')]
                        if native_sdl:
                            # It's native SDL, we must decompress to TXT!
                            text_content = get_cached_file_content(os.path.join(folder_path, native_sdl[0]))
                            zf.writestr(f"{book_name}/{book_name}.txt", text_content.encode('utf-8'))
                            processed += 1
                            
                            meta_path = os.path.join(folder_path, 'metadata.txt')
                            if os.path.exists(meta_path):
                                folder_meta = get_metadata_from_folder(folder_path)
                                with open(meta_path, 'r', encoding='utf-8') as f:
                                    meta_content = f.read()
                                levels_raw_val = folder_meta.get('levels_raw', '')
                                if 'Level:' not in meta_content and levels_raw_val:
                                    meta_content = meta_content.strip() + f"\nLevel: {levels_raw_val}\n"
                                zf.writestr(f"{book_name}/metadata.txt", meta_content)
                            processed += 1
                        else:
                            # It's native TXT, just zip it!
                            for root, dirs, files in os.walk(folder_path):
                                for fname in files:
                                    file_path = os.path.join(root, fname)
                                    arcname = os.path.join(book_name, os.path.relpath(file_path, folder_path))
                                    task_state = get_zip_task(task_id) or {}
                                    if task_state.get('cancelled'):
                                        raise InterruptedError('Cancelled by user')
                                    if fname.lower() == 'metadata.txt':
                                        folder_meta = get_metadata_from_folder(folder_path)
                                        with open(file_path, 'r', encoding='utf-8') as f:
                                            meta_content = f.read()
                                        levels_raw_val = folder_meta.get('levels_raw', '')
                                        if 'Level:' not in meta_content and levels_raw_val:
                                            meta_content = meta_content.strip() + f"\nLevel: {levels_raw_val}\n"
                                        zf.writestr(arcname, meta_content)
                                    else:
                                        zf.write(file_path, arcname)
                                    processed += 1
                                    if processed % 10 == 0 or processed == total_files:
                                        if total_files > 0:
                                            task_state['progress'] = int((processed / total_files) * 100)
                                        task_state['processed_files'] = processed
                                        save_zip_task(task_id, task_state)
                        
                        if total_files > 0:
                            task_state['progress'] = int((processed / total_files) * 100)
                        task_state['processed_files'] = processed
                        save_zip_task(task_id, task_state)

            task_state = get_zip_task(task_id) or {}
            task_state['status'] = 'done'
            task_state['progress'] = 100
            task_state['zip_path'] = temp_zip_path
            save_zip_task(task_id, task_state)

            # Safety: auto-cleanup if not downloaded within 10 minutes
            def auto_cleanup():
                task_state = get_zip_task(task_id) or {}
                if task_state.get('zip_path') and os.path.exists(task_state['zip_path']):
                    try:
                        os.remove(task_state['zip_path'])
                    except Exception:
                        pass
                delete_zip_task(task_id)
            threading.Timer(600.0, auto_cleanup).start()

        except InterruptedError:
            # Cancelled — clean up and mark as cancelled
            task_state = get_zip_task(task_id) or {}
            task_state['status'] = 'cancelled'
            save_zip_task(task_id, task_state)
            if temp_zip_path and os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            # Remove task after a short delay
            threading.Timer(10.0, lambda: delete_zip_task(task_id)).start()
        except Exception as e:
            task_state = get_zip_task(task_id) or {}
            task_state['status'] = 'error'
            task_state['error'] = str(e)
            save_zip_task(task_id, task_state)
            if temp_zip_path and os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)

    thread = threading.Thread(target=build_zip, daemon=True)
    thread.start()

    return jsonify({'task_id': task_id, 'total_files': total_files})


@app.route('/admin/zip_progress/<task_id>')
@login_required
def admin_zip_progress(task_id):
    """Poll for ZIP creation progress"""
    task = get_zip_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    return jsonify({
        'status': task.get('status'),
        'progress': task.get('progress'),
        'total_files': task.get('total_files'),
        'processed_files': task.get('processed_files'),
        'error': task.get('error'),
        'download_name': task.get('download_name', 'books_export.zip')
    })


@app.route('/admin/cancel_zip/<task_id>', methods=['POST'])
@login_required
def admin_cancel_zip(task_id):
    """Cancel a running ZIP creation task"""
    task = get_zip_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404

    # Bug #11 fix: set cancelled flag for any non-terminal status (not just 'preparing')
    # The build_zip thread checks task_state.get('cancelled') during the book loop, so
    # setting it here will stop the thread on the next book iteration.
    if task.get('status') == 'done':
        # Already done — clean up the file
        zip_path = task.get('zip_path')
        if zip_path and os.path.exists(zip_path):
            try:
                os.remove(zip_path)
            except:
                pass
        delete_zip_task(task_id)
        return jsonify({'success': True, 'message': 'Task cleaned up'})
    elif task.get('status') == 'cancelled':
        delete_zip_task(task_id)
        return jsonify({'success': True, 'message': 'Task was already cancelled'})
    else:
        # Still running (preparing or in-progress) — signal cancellation
        task['cancelled'] = True
        save_zip_task(task_id, task)
        return jsonify({'success': True, 'message': 'Cancellation requested'})


@app.route('/admin/download_zip/<task_id>')
@login_required
@permission_required('PERM_DOWNLOAD_BOOKS')
def admin_download_zip(task_id):
    """Download the completed ZIP file"""
    task = get_zip_task(task_id)
    if not task:
        return "Task not found", 404
    if task.get('status') != 'done' or not task.get('zip_path'):
        return "ZIP not ready", 400

    zip_path = task['zip_path']
    download_name = task.get('download_name', 'books_export.zip')

    response = send_file(
        zip_path,
        mimetype='application/zip',
        as_attachment=True,
        download_name=download_name
    )

    # Cleanup after response is sent
    @response.call_on_close
    def cleanup():
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        except Exception as e:
            print(f"Error cleaning up temp zip: {e}")
        delete_zip_task(task_id)

    return response


@app.route('/admin/delete/<folder_name>', methods=['POST'])
@login_required
@permission_required('PERM_DELETE_BOOK')
def admin_delete(folder_name):
    """Delete a folder"""
    upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
    folder_path = os.path.realpath(os.path.join(upload_root, folder_name))
    
    if not folder_path.startswith(upload_root + os.sep) or folder_path == upload_root:
        return jsonify({'error': 'Invalid folder path'}), 400

    if os.path.exists(folder_path):
        try:
            shutil.rmtree(folder_path)
            log_change(session.get('admin_username'), 'DELETE', 'BOOK', folder_name)
            # Sync deletion to ChromaDB
            try:
                import ai_search
                ai_search.delete_book_embeddings(folder_name)
            except Exception as e:
                print(f"Error deleting embeddings during book deletion: {e}")
            if folder_name in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[folder_name]
            save_catalog_cache()
            return jsonify({'success': True, 'message': f'Deleted {folder_name}'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        return jsonify({'error': 'Folder not found'}), 404


@app.route('/admin/edit/<folder_name>', methods=['GET', 'POST'])
@login_required
def admin_edit_book(folder_name):
    """Edit a book's metadata and folder name"""
    # Check if user has ANY edit permission (including OCR)
    edit_perms = ['PERM_EDIT_BOOK_NAME', 'PERM_EDIT_TAGS', 'PERM_EDIT_SUB_BOOK', 'PERM_EDIT_LINK', 'PERM_EDIT_OCR']
    user_perms = session.get('admin_permissions', [])
    is_super = session.get('admin_role') == 'super'
    
    if not is_super and not any(p in user_perms for p in edit_perms):
        return render_template('admin/forbidden.html', permission="ANY_EDIT_PERMISSION"), 403

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    if not os.path.exists(folder_path):
        flash('Folder not found', 'error')
        return redirect(url_for('admin_manage_books'))

    if request.method == 'GET':
        metadata = get_metadata_from_folder(folder_path, bypass_cache=True)
        
        # Get list of .txt files
        txt_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if (file.endswith('.txt') and file.lower() != 'metadata.txt') or file.endswith('.sdl'):
                    # Get relative path for display
                    rel_path = os.path.relpath(os.path.join(root, file), folder_path)
                    # Normalize slashes
                    rel_path = rel_path.replace('\\', '/')
                    txt_files.append(rel_path)
        
        return render_template('admin/edit_book.html', 
                               book_name=folder_name, 
                               tags=metadata.get('tags', ''),
                               archive_url=metadata.get('source', ''),
                               subbooks_raw=metadata.get('subbooks_raw', ''),
                               levels_raw=metadata.get('levels_raw', ''),
                               notes=metadata.get('notes', ''),
                               published=metadata.get('published', True),
                               txt_files=sorted(txt_files),
                               permissions=user_perms,
                               is_super=is_super)

    if request.method == 'POST':
        data = request.get_json()
        new_name = data.get('new_name', '').strip()
        published = data.get('published', True)
        if isinstance(published, str):
            published = published.lower() == 'true'
        raw_tags = data.get('tags', '').strip()
        tags = sanitize_tags_against_taxonomy(raw_tags, published=published)
        archive_url = data.get('archive_url', '').strip()
        subbooks_raw = data.get('subbooks_raw', '').strip()
        levels_raw = data.get('levels_raw', '').strip()
        notes = data.get('notes', '').strip()
        published = data.get('published', True)
        if isinstance(published, str):
            published = published.lower() == 'true'
        
        if not new_name:
            return jsonify({'error': 'Folder name cannot be empty'})

        # Load current metadata to compare
        current_metadata = get_metadata_from_folder(folder_path)

        new_folder_path = folder_path
        if new_name != folder_name:
            if not is_super and 'PERM_EDIT_BOOK_NAME' not in user_perms:
                return jsonify({'error': 'Permission denied: PERM_EDIT_BOOK_NAME required to rename book'}), 403
            
            # Sanitize new_name slightly
            new_name = re.sub(r'[<>:"/\\|?*]', '-', new_name)
            new_folder_path = os.path.join(app.config['UPLOAD_FOLDER'], new_name)
            if os.path.exists(new_folder_path):
                return jsonify({'error': 'A folder with that name already exists'})
            
            try:
                os.rename(folder_path, new_folder_path)
                log_change(session.get('admin_username'), 'RENAME', 'BOOK', folder_name, previous_data={'name': folder_name}, after_data={'name': new_name})
            except Exception as e:
                return jsonify({'error': f'Failed to rename folder: {str(e)}'})

        # Check permissions for other fields if they changed
        if archive_url != current_metadata.get('source', '') and not is_super and 'PERM_EDIT_LINK' not in user_perms:
             archive_url = current_metadata.get('source', '')
        
        if tags != current_metadata.get('tags', '') and not is_super and 'PERM_EDIT_TAGS' not in user_perms:
             tags = current_metadata.get('tags', '')
             
        if subbooks_raw != current_metadata.get('subbooks_raw', '') and not is_super and 'PERM_EDIT_SUB_BOOK' not in user_perms:
             subbooks_raw = current_metadata.get('subbooks_raw', '')

        # Handle metadata
        old_metadata_path = os.path.join(folder_path, 'metadata.txt') if folder_name == new_name else os.path.join(new_folder_path, 'metadata.txt')
        old_meta_text = ''
        if os.path.exists(old_metadata_path):
            with open(old_metadata_path, 'r', encoding='utf-8') as f:
                old_meta_text = f.read()
                
        metadata_path = os.path.join(new_folder_path, 'metadata.txt')
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                if archive_url:
                    f.write(f"Source: {archive_url}\n")
                f.write(f"Tags: {tags}\n")

                if levels_raw:
                    f.write(f"Level: {levels_raw}\n")
                if notes:
                    escaped_notes = notes.replace('\r\n', '\n').replace('\n', '\\n')
                    f.write(f"Notes: {escaped_notes}\n")
                f.write(f"Published: {'true' if published else 'false'}\n")
            
            # Clear cache for this book
            if folder_name in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[folder_name]
            if new_name in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[new_name]
            save_catalog_cache()
            
            if (archive_url != current_metadata.get('source', '') or 
                tags != current_metadata.get('tags', '') or 
                subbooks_raw != current_metadata.get('subbooks_raw', '') or 
                notes != current_metadata.get('notes', '') or
                published != current_metadata.get('published', True)):
                new_meta_text = ''
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    new_meta_text = f.read()
                diff = generate_text_diff(old_meta_text, new_meta_text)
                if diff:
                    log_change(session.get('admin_username'), 'UPDATE', 'METADATA_FILE', f"{new_name}/metadata.txt", after_data={'diff': diff})
            
            return jsonify({'success': True, 'message': 'Metadata and folder updated', 'new_folder_name': new_name})
        except Exception as e:
            return jsonify({'error': f'Failed to update metadata: {str(e)}'})


@app.route('/admin/edit/<folder_name>/file/<path:filename>', methods=['GET', 'POST'])
@login_required
@permission_required('PERM_EDIT_OCR')
def admin_edit_file(folder_name, filename):
    """Read or update a specific text file within a book folder"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404

    # Prevent directory traversal
    file_path = os.path.abspath(os.path.join(folder_path, filename))
    if not file_path.startswith(os.path.abspath(folder_path)):
        return jsonify({'error': 'Invalid file path'}), 403
        
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    if request.method == 'GET':
        try:
            content = get_cached_file_content(file_path)
            return jsonify({'success': True, 'content': content})
        except Exception as e:
            return jsonify({'error': f'Failed to read file: {str(e)}'})

    if request.method == 'POST':
        data = request.get_json()
        content = data.get('content', '')
        try:
            old_content = get_cached_file_content(file_path)
            if file_path.endswith('.sdl') or (filename.lower() != 'metadata.txt' and not filename.endswith('.json')):
                target_sdl_path = file_path if file_path.endswith('.sdl') else os.path.splitext(file_path)[0] + '.sdl'
                import zstandard as zstd
                sdl_data = bytearray(b'SDL\x03')
                cctx = zstd.ZstdCompressor(level=CURRENT_ZSTD_LEVEL)
                sdl_data.extend(cctx.compress(content.encode('utf-8')))
                with open(target_sdl_path, 'wb') as f:
                    f.write(sdl_data)
                
                # If old file was .txt, remove it so only .sdl exists on server
                if target_sdl_path != file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass

                # Invalidate cache manually since we just overwrote it directly with bytes
                import time
                mtime = os.path.getmtime(target_sdl_path)
                cache_key = f"{target_sdl_path}:{mtime}"
                _file_content_cache[cache_key] = content
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
            # Log the change
            diff = generate_text_diff(old_content, content)
            if diff:
                log_change(session.get('admin_username'), 'UPDATE', 'OCR_FILE', f"{folder_name}/{filename}", after_data={'diff': diff})
            
            # Auto-reembed in background if the book has existing embeddings
            try:
                import ai_search
                status = ai_search.get_book_embedding_status([folder_name])
                if status.get(folder_name):
                    def run_reembed():
                        try:
                            # Pass None as the API key to use configured platform key in ai_search
                            ai_search.embed_book(folder_name, app.config['UPLOAD_FOLDER'], None)
                        except Exception as e:
                            print(f"Error in background auto-reembedding: {e}")
                    threading.Thread(target=run_reembed, daemon=True).start()
            except Exception as e:
                print(f"Error checking/starting background re-embedding: {e}")

            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': f'Failed to write file: {str(e)}'})


@app.route('/admin/download_txt/<folder_name>', defaults={'filename': None}, methods=['GET'])
@app.route('/admin/download_txt/<folder_name>/<path:filename>', methods=['GET'])
@login_required
def admin_download_book_txt(folder_name, filename=None):
    """Download decompressed text content of a book or specific file as a .txt attachment"""
    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder_name)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404

    if not filename:
        for root, dirs, files in os.walk(folder_path):
            for file in sorted(files):
                if (file.endswith('.txt') and file.lower() != 'metadata.txt') or file.endswith('.sdl'):
                    rel_path = os.path.relpath(os.path.join(root, file), folder_path).replace('\\', '/')
                    filename = rel_path
                    break
            if filename:
                break

    if not filename:
        return jsonify({'error': 'No readable text or SDL file found in folder'}), 404

    file_path = os.path.abspath(os.path.join(folder_path, filename))
    if not file_path.startswith(os.path.abspath(folder_path)) or not os.path.exists(file_path):
        return jsonify({'error': 'Invalid file path'}), 403

    try:
        content = get_cached_file_content(file_path)
        base_name = os.path.splitext(os.path.basename(filename))[0]
        if base_name.lower() in ('data', 'content', folder_name.lower()):
            out_filename = f"{folder_name}.txt"
        else:
            out_filename = f"{folder_name}_{base_name}.txt"

        out_filename = re.sub(r'[^\w\-\.]', '_', out_filename)
        response = Response(content, mimetype='text/plain; charset=utf-8')
        response.headers['Content-Disposition'] = f'attachment; filename="{out_filename}"'
        return response
    except Exception as e:
        return jsonify({'error': f'Failed to generate text download: {str(e)}'}), 500


@app.route('/api/admin/book-text/<book_name>')
@login_required
def admin_get_book_text(book_name):
    """API for admin to fetch full text of a book (preserving page markers)"""
    try:
        from ai_search import load_book_full_text
        full_text, err = load_book_full_text(book_name, app.config['UPLOAD_FOLDER'])
        if err:
            return jsonify({'success': False, 'error': err}), 400
        return jsonify({'success': True, 'text': full_text})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/admin/delete_bulk', methods=['POST'])
@login_required
@permission_required('PERM_DELETE_BOOK')
def admin_delete_bulk():
    """Delete multiple books"""
    data = request.get_json()
    books_raw = data.get('books', [])
    
    if books_raw == 'all':
        books = get_filtered_book_names(data)
    else:
        books = books_raw
        
    if not books:
        return jsonify({'error': 'No books selected'}), 400
        
    deleted_count = 0
    errors = []
    
    for book_name in books:
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path)
                log_change(session.get('admin_username'), 'DELETE', 'BOOK', book_name)
                # Sync deletion to ChromaDB
                try:
                    import ai_search
                    ai_search.delete_book_embeddings(book_name)
                except Exception as e:
                    print(f"Error deleting embeddings during bulk deletion of {book_name}: {e}")
                if book_name in CATALOG_METADATA_CACHE:
                    del CATALOG_METADATA_CACHE[book_name]
                deleted_count += 1
            except Exception as e:
                errors.append(f"Failed to delete {book_name}: {str(e)}")
    
    if deleted_count > 0:
        save_catalog_cache()
        
    if errors:
        return jsonify({
            'success': False, 
            'error': f'Deleted {deleted_count} books but encountered errors: {"; ".join(errors)}'
        })
    
    return jsonify({
        'success': True,
        'message': f'Successfully deleted {deleted_count} books'
    })


@app.route('/admin/bulk_change_status', methods=['POST'])
@login_required
def admin_bulk_change_status():
    """Change published/draft status for multiple books"""
    edit_perms = ['PERM_EDIT_BOOK_NAME', 'PERM_EDIT_TAGS', 'PERM_EDIT_SUB_BOOK', 'PERM_EDIT_LINK', 'PERM_EDIT_OCR']
    user_perms = session.get('admin_permissions', [])
    is_super = session.get('admin_role') == 'super'
    
    if not is_super and not any(p in user_perms for p in edit_perms):
        return jsonify({'error': 'Permission denied: edit permissions required'}), 403

    data = request.get_json()
    books_raw = data.get('books', [])
    target_status_raw = data.get('target_status') or data.get('new_status') or data.get('status', 'published')
    target_status = str(target_status_raw).strip().lower()
    published = (target_status == 'published')
    
    if books_raw == 'all':
        books = get_filtered_book_names(data)
    else:
        books = books_raw
        
    if not books:
        return jsonify({'error': 'No books selected'}), 400
        
    updated_count = 0
    errors = []
    
    for book_name in books:
        folder_path = os.path.join(app.config['UPLOAD_FOLDER'], book_name)
        if os.path.exists(folder_path):
            try:
                metadata = get_metadata_from_folder(folder_path, bypass_cache=True)
                metadata_path = os.path.join(folder_path, 'metadata.txt')
                old_meta_text = ''
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        old_meta_text = f.read()
                
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    if metadata.get('source'):
                        f.write(f"Source: {metadata['source']}\n")
                    f.write(f"Tags: {metadata.get('tags', '')}\n")

                    if metadata.get('levels_raw'):
                        f.write(f"Level: {metadata['levels_raw']}\n")
                    if metadata.get('notes'):
                        escaped_notes = metadata['notes'].replace('\r\n', '\n').replace('\n', '\\n')
                        f.write(f"Notes: {escaped_notes}\n")
                    f.write(f"Published: {'true' if published else 'false'}\n")
                
                if book_name in CATALOG_METADATA_CACHE:
                    del CATALOG_METADATA_CACHE[book_name]
                
                new_meta_text = ''
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        new_meta_text = f.read()
                diff = generate_text_diff(old_meta_text, new_meta_text)
                if diff:
                    log_change(session.get('admin_username'), 'UPDATE', 'METADATA_FILE', f"{book_name}/metadata.txt", after_data={'diff': diff})
                    
                updated_count += 1
            except Exception as e:
                errors.append(f"Failed to update {book_name}: {str(e)}")
                
    if updated_count > 0:
        save_catalog_cache()
        
    if errors:
        return jsonify({
            'success': False,
            'error': f'Updated {updated_count} books but encountered errors: {"; ".join(errors)}'
        })
        
    return jsonify({
        'success': True,
        'message': f'Successfully updated status for {updated_count} books'
    })


@app.route('/admin/download_excel', methods=['POST'])
@login_required
@permission_required('PERM_UPLOAD_EXCEL')
def admin_download_excel():
    """Download Excel (XLSX) of selected books with protected columns using temporary files"""
    temp_excel_path = None
    try:
        books_json = request.form.get('books')
        if not books_json:
            return "No books selected", 400
            
        if books_json == 'all':
            books = sorted(get_filtered_book_names(request.form))
        else:
            books = json.loads(books_json)
        
        # Create Excel workbook and sheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Books"
        
        # Define headers
        headers = ['ID (Do Not Edit)', 'Name', 'Link', 'Tags', 'Pages', 'Size (KB)', 'Subbook', 'Notes']
        ws.append(headers)
        
        upload_folder = app.config['UPLOAD_FOLDER']
        
        for book_name in books:
            folder_path = os.path.join(upload_folder, book_name)
            if not os.path.exists(folder_path):
                continue
                
            metadata = get_metadata_from_folder(folder_path)
            
            cached = CATALOG_METADATA_CACHE.get(book_name, {})
            pages = cached.get('pages', 0)
            size_bytes = cached.get('size', 0)
            
            # Convert size to KB
            size_kb = round(size_bytes / 1024, 2)
 
            ws.append([
                book_name,        # ID (used to locate the folder during upload)
                book_name,        # Editable Name
                metadata.get('source', ''),
                metadata.get('tags', ''),
                pages,
                size_kb,
                metadata.get('subbooks_raw', ''),
                metadata.get('notes', '')
            ])
            
        # Protect the worksheet
        ws.protection.enable()
        
        # Unlock specific columns
        # Loop through all rows (skipping header row 1)
        for row in range(2, ws.max_row + 1):
            ws.cell(row=row, column=2).protection = Protection(locked=False)  # Unlock Name
            ws.cell(row=row, column=4).protection = Protection(locked=False)  # Unlock Tags
            ws.cell(row=row, column=7).protection = Protection(locked=False)  # Unlock Subbook
            ws.cell(row=row, column=8).protection = Protection(locked=False)  # Unlock Notes

        # Create temporary file and save workbook
        fd, temp_excel_path = tempfile.mkstemp(suffix='.xlsx')
        os.close(fd)
        wb.save(temp_excel_path)

        if len(books) == 1:
            clean_name = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
            download_name = f"{clean_name}.xlsx" if clean_name else "books_export.xlsx"
        elif len(books) > 1 and books_json != 'all':
            clean_first = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
            download_name = f"{clean_first}_and_{len(books)-1}_others.xlsx" if clean_first else f"books_export_{len(books)}.xlsx"
        else:
            download_name = f"SDL_Library_Export_{datetime.now().strftime('%Y%m%d')}.xlsx"

        response = send_file(
            temp_excel_path,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=download_name
        )
        
        # Schedule cleanup after response is sent
        cleanup_path = temp_excel_path
        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(cleanup_path):
                    os.remove(cleanup_path)
            except Exception as e:
                print(f"Error cleaning up temp excel: {e}")

        return response
        
    except Exception as e:
        if temp_excel_path and os.path.exists(temp_excel_path):
            os.remove(temp_excel_path)
        return f"Error generating Excel: {str(e)}", 500


@app.route('/admin/upload_excel', methods=['POST'])
@login_required
@permission_required('PERM_UPLOAD_EXCEL')
def admin_upload_excel():
    """Handle Excel file upload to update book metadata and names"""
    if 'excel_file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['excel_file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'error': 'Please upload an Excel (.xlsx) file'}), 400
    
    try:
        # Read the Excel file
        wb = openpyxl.load_workbook(file)
        ws = wb.active
        
        # Get headers from first row
        headers = [str(cell.value).strip() if cell.value is not None else '' for cell in ws[1]]
        
        # Verify required columns exist
        required_cols = ['ID (Do Not Edit)', 'Name', 'Tags']
        if not all(col in headers for col in required_cols):
            return jsonify({'error': 'Excel is missing required columns (ID (Do Not Edit), Name, Tags).'}), 400
            
        # Get column indices
        id_idx = headers.index('ID (Do Not Edit)')
        name_idx = headers.index('Name')
        tags_idx = headers.index('Tags')
        books_idx = headers.index('Subbook') if 'Subbook' in headers else None
        notes_idx = headers.index('Notes') if 'Notes' in headers else None

        upload_folder = app.config['UPLOAD_FOLDER']
        updated_count = 0
        errors = []
        
        # Iterate through rows starting from row 2
        for row in ws.iter_rows(min_row=2, values_only=True):
            # Check if row is empty
            if row[id_idx] is None:
                continue
                
            book_id = str(row[id_idx]).strip()
            new_name = str(row[name_idx]).strip() if row[name_idx] is not None else ""
            if new_name:
                # Sanitize the given name, e.g. replacing illegal Windows folder chars like '|' with '-'
                new_name = re.sub(r'[<>:"/\\|?*]', '-', new_name)
            raw_tags = str(row[tags_idx]).strip() if row[tags_idx] is not None else ""
            new_books_raw = ''
            if books_idx is not None and books_idx < len(row) and row[books_idx] is not None:
                new_books_raw = str(row[books_idx]).strip()
            new_notes = str(row[notes_idx]).strip() if (notes_idx is not None and notes_idx < len(row) and row[notes_idx] is not None) else ""
            
            if not book_id:
                continue

            folder_path = os.path.join(upload_folder, book_id)
            if not os.path.exists(folder_path):
                # It's possible the folder was already renamed in a previous run of this same Excel file.
                # Let's check if the target target_path exists.
                if new_name:
                    already_renamed_path = os.path.join(upload_folder, new_name)
                    if os.path.exists(already_renamed_path):
                        folder_path = already_renamed_path
                    else:
                        errors.append(f"Folder '{book_id}' not found.")
                        continue
                else:
                    errors.append(f"Folder '{book_id}' not found.")
                    continue

            # 1. Update rename folder if Name changed
            new_folder_path = folder_path
            # Need to check if folder_path is not already the target_path (which happens if we caught it above)
            if new_name and os.path.normcase(os.path.basename(folder_path)) != os.path.normcase(new_name):
                target_path = os.path.join(upload_folder, new_name)
                # Check if target already exists and it's a different folder to avoid overwrite
                if os.path.exists(target_path) and os.path.normcase(folder_path) != os.path.normcase(target_path):
                    errors.append(f"Cannot rename '{book_id}' to '{new_name}' because a folder with that name already exists.")
                else:
                    try:
                        os.rename(folder_path, target_path)
                        log_change(session.get('admin_username'), 'RENAME', 'BOOK', book_id, previous_data={'name': book_id}, after_data={'name': new_name})
                        new_folder_path = target_path
                    except Exception as e:
                        errors.append(f"Error renaming '{book_id}': {str(e)}")
                        continue
            
            # 2. Update metadata.txt for Tags
            # Maintain the existing Source/Link since it shouldn't be edited.
            metadata = get_metadata_from_folder(new_folder_path)
            source_link = metadata.get('source', '')
            
            metadata_path = os.path.join(new_folder_path, 'metadata.txt')
            
            old_meta_text = ''
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    old_meta_text = f.read()
                    
            try:
                is_pub = metadata.get('published', True)
                tags_to_write = sanitize_tags_against_taxonomy(raw_tags, published=is_pub)
                with open(metadata_path, 'w', encoding='utf-8') as f:
                    if source_link:
                        f.write(f"Source: {source_link}\n")
                    f.write(f"Tags: {tags_to_write}\n")

                    if metadata.get('levels_raw'):
                        f.write(f"Level: {metadata['levels_raw']}\n")
                    if new_notes:
                        escaped_notes = new_notes.replace('\r\n', '\n').replace('\n', '\\n')
                        f.write(f"Notes: {escaped_notes}\n")
                    f.write(f"Published: {'true' if is_pub else 'false'}\n")
                
                if new_tags != metadata.get('tags', '') or new_books_raw != metadata.get('subbooks_raw', '') or new_notes != metadata.get('notes', ''):
                    new_meta_text = ''
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        new_meta_text = f.read()
                    diff = generate_text_diff(old_meta_text, new_meta_text)
                    if diff:
                        log_change(session.get('admin_username'), 'UPDATE', 'METADATA_FILE', f"{new_name or book_id}/metadata.txt", after_data={'diff': diff})
                
                # Clear cache for this book
                if book_id in CATALOG_METADATA_CACHE:
                    del CATALOG_METADATA_CACHE[book_id]
                if new_name and new_name in CATALOG_METADATA_CACHE:
                    del CATALOG_METADATA_CACHE[new_name]
                
                updated_count += 1
            except Exception as e:
                errors.append(f"Error saving metadata for '{book_id}': {str(e)}")
                
        if updated_count > 0:
            save_catalog_cache()
            
        if errors:
            from collections import Counter
            c = Counter(errors)
            error_details = []
            for err, count in c.items():
                if count > 1:
                    error_details.append(f"{count}x {err}")
                else:
                    error_details.append(err)
            
            error_msg = f'Updated {updated_count} books. Encountered {len(errors)} errors:\n' + '\n'.join(error_details)
            return jsonify({
                'success': True,
                'has_errors': True,
                'message': error_msg
            })
            
        return jsonify({
            'success': True,
            'has_errors': False,
            'message': f'Successfully updated {updated_count} books from Excel.'
        })
        
    except Exception as e:
        app.logger.error(f"Mobile Catalog Error: {e}")
        return jsonify({'error': str(e), 'granthas': [], 'total': 0}), 500


@app.route('/admin/download_json', methods=['POST'])
@login_required
@permission_required('PERM_UPLOAD_EXCEL')
def admin_download_json():
    """Download JSON of selected books with metadata for AI and data processing"""
    try:
        books_json = request.form.get('books')
        if not books_json:
            return jsonify({'error': 'No books selected'}), 400
            
        if books_json == 'all':
            books = sorted(get_filtered_book_names(request.form))
        else:
            books = json.loads(books_json)
        
        upload_folder = app.config['UPLOAD_FOLDER']
        books_data = []
        
        for book_name in books:
            folder_path = os.path.join(upload_folder, book_name)
            if not os.path.exists(folder_path):
                continue
                
            metadata = get_metadata_from_folder(folder_path)
            cached = CATALOG_METADATA_CACHE.get(book_name, {})
            pages = cached.get('pages', 0)
            size_bytes = cached.get('size', 0)
            size_kb = round(size_bytes / 1024, 2)
            
            books_data.append({
                'id': book_name,
                'name': book_name,
                'link': metadata.get('source', ''),
                'tags': metadata.get('tags', ''),
                'pages': pages,
                'size_kb': size_kb,
                'subbooks': metadata.get('subbooks_raw', ''),
                'notes': metadata.get('notes', '')
            })
            
        export_payload = {
            'version': '1.0',
            'exported_at': datetime.now().isoformat(),
            'total_books': len(books_data),
            'books': books_data
        }
        
        json_bytes = json.dumps(export_payload, ensure_ascii=False, indent=2).encode('utf-8')
        buf = io.BytesIO(json_bytes)
        
        if len(books) == 1:
            clean_name = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
            download_name = f"{clean_name}.json" if clean_name else "books_export.json"
        elif len(books) > 1 and books_json != 'all':
            clean_first = re.sub(r'[^\w\s-]', '', books[0], flags=re.UNICODE).strip()
            download_name = f"{clean_first}_and_{len(books)-1}_others.json" if clean_first else f"books_export_{len(books)}.json"
        else:
            download_name = f"SDL_Library_Export_{datetime.now().strftime('%Y%m%d')}.json"

        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=download_name
        )
        
    except Exception as e:
        return jsonify({'error': f'Error generating JSON: {str(e)}'}), 500


@app.route('/admin/upload_json', methods=['POST'])
@login_required
@permission_required('PERM_UPLOAD_EXCEL')
def admin_upload_json():
    """Handle JSON file upload to update book metadata and names"""
    if 'json_file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['json_file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.lower().endswith('.json'):
        return jsonify({'error': 'Please upload a JSON (.json) file'}), 400
    
    try:
        content = file.read().decode('utf-8')
        raw_data = json.loads(content)
    except Exception as e:
        return jsonify({'error': f'Invalid JSON content: {str(e)}'}), 400

    if isinstance(raw_data, list):
        items = raw_data
    elif isinstance(raw_data, dict):
        if 'books' in raw_data and isinstance(raw_data['books'], list):
            items = raw_data['books']
        elif 'data' in raw_data and isinstance(raw_data['data'], list):
            items = raw_data['data']
        else:
            items = [raw_data]
    else:
        return jsonify({'error': 'Invalid JSON format. Expected an array of books or an object containing a books array.'}), 400

    def extract_val(item_dict, keys):
        if not isinstance(item_dict, dict):
            return ""
        for k in keys:
            if k in item_dict and item_dict[k] is not None:
                val = item_dict[k]
                if isinstance(val, list):
                    if all(isinstance(x, (str, int, float)) for x in val):
                        return ", ".join(str(x) for x in val)
                    else:
                        lines = []
                        for sub in val:
                            if isinstance(sub, dict):
                                parts = [f"{pk}: {pv}" for pk, pv in sub.items()]
                                lines.append(" | ".join(parts))
                            else:
                                lines.append(str(sub))
                        return "\n".join(lines)
                return str(val)
        return ""

    upload_folder = app.config['UPLOAD_FOLDER']
    updated_count = 0
    errors = []

    for item in items:
        if not isinstance(item, dict):
            continue

        book_id = extract_val(item, ['id', 'ID', 'ID (Do Not Edit)', 'book_id', 'folder_name']).strip()
        new_name = extract_val(item, ['name', 'Name', 'title']).strip()
        if new_name:
            new_name = re.sub(r'[<>:"/\\|?*]', '-', new_name)
        raw_tags = extract_val(item, ['tags', 'Tags']).strip()
        new_books_raw = extract_val(item, ['subbooks', 'Subbook', 'subbook', 'subbooks_raw']).strip()
        new_notes = extract_val(item, ['notes', 'Notes']).strip()

        if not book_id:
            continue

        folder_path = os.path.join(upload_folder, book_id)
        if not os.path.exists(folder_path):
            if new_name:
                already_renamed_path = os.path.join(upload_folder, new_name)
                if os.path.exists(already_renamed_path):
                    folder_path = already_renamed_path
                else:
                    errors.append(f"Folder '{book_id}' not found.")
                    continue
            else:
                errors.append(f"Folder '{book_id}' not found.")
                continue

        # 1. Rename folder if Name changed
        new_folder_path = folder_path
        if new_name and os.path.normcase(os.path.basename(folder_path)) != os.path.normcase(new_name):
            target_path = os.path.join(upload_folder, new_name)
            if os.path.exists(target_path) and os.path.normcase(folder_path) != os.path.normcase(target_path):
                errors.append(f"Cannot rename '{book_id}' to '{new_name}' because a folder with that name already exists.")
            else:
                try:
                    os.rename(folder_path, target_path)
                    log_change(session.get('admin_username'), 'RENAME', 'BOOK', book_id, previous_data={'name': book_id}, after_data={'name': new_name})
                    new_folder_path = target_path
                except Exception as e:
                    errors.append(f"Error renaming '{book_id}': {str(e)}")
                    continue

        # 2. Update metadata.txt
        metadata = get_metadata_from_folder(new_folder_path)
        source_link = metadata.get('source', '')
        provided_source = extract_val(item, ['link', 'Link', 'source', 'Source']).strip()
        if provided_source:
            source_link = provided_source

        metadata_path = os.path.join(new_folder_path, 'metadata.txt')

        old_meta_text = ''
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                old_meta_text = f.read()

        try:
            is_pub = metadata.get('published', True)
            tags_to_write = sanitize_tags_against_taxonomy(raw_tags, published=is_pub)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                if source_link:
                    f.write(f"Source: {source_link}\n")
                f.write(f"Tags: {tags_to_write}\n")

                if metadata.get('levels_raw'):
                    f.write(f"Level: {metadata['levels_raw']}\n")
                if new_notes:
                    escaped_notes = new_notes.replace('\r\n', '\n').replace('\n', '\\n')
                    f.write(f"Notes: {escaped_notes}\n")
                f.write(f"Published: {'true' if is_pub else 'false'}\n")

            if new_tags != metadata.get('tags', '') or new_books_raw != metadata.get('subbooks_raw', '') or new_notes != metadata.get('notes', '') or source_link != metadata.get('source', ''):
                new_meta_text = ''
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    new_meta_text = f.read()
                diff = generate_text_diff(old_meta_text, new_meta_text)
                if diff:
                    log_change(session.get('admin_username'), 'UPDATE', 'METADATA_FILE', f"{new_name or book_id}/metadata.txt", after_data={'diff': diff})

            if book_id in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[book_id]
            if new_name and new_name in CATALOG_METADATA_CACHE:
                del CATALOG_METADATA_CACHE[new_name]

            updated_count += 1
        except Exception as e:
            errors.append(f"Error saving metadata for '{book_id}': {str(e)}")

    if updated_count > 0:
        save_catalog_cache()

    if errors:
        from collections import Counter
        c = Counter(errors)
        error_details = []
        for err, count in c.items():
            if count > 1:
                error_details.append(f"{count}x {err}")
            else:
                error_details.append(err)

        error_msg = f'Updated {updated_count} books. Encountered {len(errors)} errors:\n' + '\n'.join(error_details)
        return jsonify({
            'success': True,
            'has_errors': True,
            'message': error_msg
        })

    return jsonify({
        'success': True,
        'has_errors': False,
        'message': f'Successfully updated {updated_count} books from JSON.'
    })




def warmup_catalog_cache():
    """Populate the catalog cache in the background on startup."""
    global _warmup_running
    
    # Use a lock to ensure only one warmup runs at a time
    if not _warmup_lock.acquire(blocking=False):
        return
        
    try:
        _warmup_running = True
        load_catalog_cache()
        print("Warming up catalog cache (checking for changes)...")
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            return
        
        all_items = sorted(os.listdir(upload_folder))
        folders = [d for d in all_items if os.path.isdir(os.path.join(upload_folder, d))]
        total_books = len(folders)
        
        cache_updated = False
        for i, folder_name in enumerate(folders):
            folder_path = os.path.join(upload_folder, folder_name)
            
            try:
                with open(WARMUP_STATUS_FILE, 'w', encoding='utf-8') as f:
                    f.write(f"[{i+1}/{total_books}] {folder_name}")
            except:
                pass

            try:
                latest_mtime = int(os.path.getmtime(folder_path))
                with os.scandir(folder_path) as it:
                    for entry in it:
                        if entry.is_file():
                            latest_mtime = max(latest_mtime, int(entry.stat().st_mtime))
                
                cached = CATALOG_METADATA_CACHE.get(folder_name)
                if cached and cached.get('mtime') == latest_mtime:
                    continue

                metadata = get_metadata_from_folder(folder_path, bypass_cache=True)
                
                page_count = 0
                char_count = 0
                sha256 = hashlib.sha256()
                compressed_size = 0
                
                sdl_files = [f for f in sorted(os.listdir(folder_path)) if f.endswith('.sdl')]
                if sdl_files:
                    sdl_path = os.path.join(folder_path, sdl_files[0])
                    compressed_size = os.path.getsize(sdl_path)
                    try:
                        content = get_cached_file_content(sdl_path)
                        page_count = len(re.findall(r'\{\[\(\d+\)\]\}', content))
                        char_count = len(content)
                        sha256.update(content.encode('utf-8'))
                    except:
                        pass
                else:
                    for root, dirs, files in os.walk(folder_path):
                        for fname in sorted(files):
                            if fname.endswith('.txt') and fname.lower() != 'metadata.txt':
                                fpath = os.path.join(root, fname)
                                try:
                                    content = get_cached_file_content(fpath)
                                    page_count += len(re.findall(r'\{\[\(\d+\)\]\}', content))
                                    char_count += len(content)
                                    sha256.update(content.encode('utf-8'))
                                except:
                                    pass
                
                checksum = f'sha256:{sha256.hexdigest()}'
                CATALOG_METADATA_CACHE[folder_name] = {
                    'mtime': latest_mtime,
                    'size': compressed_size,
                    'pages': page_count,
                    'chars': char_count,
                    'checksum': checksum,
                    'tags': metadata.get('tags', ''),
                    'source': metadata.get('source', ''),
                    'subbooks_raw': metadata.get('subbooks_raw', ''),
                    'subbooks': metadata.get('subbooks', []),
                    'notes': metadata.get('notes', '')
                }
                cache_updated = True
                if i > 0 and i % 50 == 0:
                    save_catalog_cache()
            except Exception as e:
                print(f"Error warming cache for book index: {e}")
                
        stale_keys = [k for k in CATALOG_METADATA_CACHE if k not in folders]
        for k in stale_keys:
            del CATALOG_METADATA_CACHE[k]
            cache_updated = True
            
        if cache_updated:
            save_catalog_cache()
            
    finally:
        # Mark as done and release lock
        try:
            with open(WARMUP_STATUS_FILE, 'w', encoding='utf-8') as f:
                f.write("IDLE")
        except:
            pass
        _warmup_running = False
        _warmup_lock.release()
        
    print(f"Catalog cache ready: {len(CATALOG_METADATA_CACHE)} books.")

# Start warmup thread on module load so it works under Gunicorn/Waitress
# Every worker process will have its own local memory cache.
threading.Thread(target=warmup_catalog_cache, daemon=True).start()

import glob
from time_utils import get_ist_now


# =============================================================================
# SAMSHODHANA MANDIRAM - EXTERNAL API ENDPOINTS
# =============================================================================

# Helper to render the reporting outcome page
def render_report_template(success, message):
    title = "Account Secured" if success else "Link Expired"
    icon = "🛡️" if success else "⚠️"
    status_text = "Secure" if success else "Info"
    badge_style = "background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.25);" if success else "background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.25);"
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Samshodhana Mandiram</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #311042 100%);
            min-height: 100vh;
            color: #cbd5e1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .card {{
            background: rgba(15, 23, 42, 0.45);
            backdrop-filter: blur(16px) saturate(180%);
            -webkit-backdrop-filter: blur(16px) saturate(180%);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            padding: 48px 32px;
            max-width: 500px;
            width: 100%;
            text-align: center;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }}
        .icon {{
            font-size: 64px;
            margin-bottom: 24px;
            display: block;
        }}
        h1 {{
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, #a5b4fc 0%, #e879f9 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 12px;
            letter-spacing: -0.5px;
        }}
        p {{
            color: #cbd5e1;
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 32px;
            text-align: center;
        }}
        .badge {{
            display: inline-block;
            padding: 8px 18px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 24px;
            {badge_style}
        }}
        .home-btn {{
            display: inline-block;
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            color: white;
            text-decoration: none;
            padding: 14px 28px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            transition: all 0.3s;
        }}
        .home-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.45);
            filter: brightness(1.1);
        }}
    </style>
</head>
<body>
    <div class="card">
        <span class="icon">{icon}</span>
        <br>
        <span class="badge">{status_text}</span>
        <h1>{title}</h1>
        <p>{message}</p>
        <a href="/" class="home-btn">Return to Home</a>
    </div>
</body>
</html>"""


def send_admin_report_email(user_email):
    """Notify the admin of an unauthorized password reset attempt."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from datetime import datetime

    admin_email = getattr(config, 'ADMIN_EMAIL', config.SMTP_USER)
    if not getattr(config, 'SMTP_USER', None) or not getattr(config, 'SMTP_PASSWORD', None) or not admin_email:
        print("SMTP or Admin credentials not configured. Skipping admin report email.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = config.SMTP_USER
        msg['To'] = admin_email
        msg['Subject'] = f"SECURITY ALERT: Unauthorized Password Reset Attempt Reported - {user_email}"
        
        body = f"""Hello Administrator,

A user has reported an unauthorized password reset request for their account.

Details:
User Email: {user_email}
Action Taken: The OTP code was deactivated and deleted immediately upon report.
Time of Report: {get_ist_now().strftime('%Y-%m-%d %H:%M:%S')}

Please review user account security logs if necessary.

Best regards,
Samshodhana Mandiram Security Team"""

        msg.attach(MIMEText(body, 'plain'))
        
        context = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending admin report email: {e}")
        return False


def send_otp_email(to_email, otp, host_url):
    """Send reset password OTP via email with beautiful styling and report link."""
    import smtplib
    import ssl
    import urllib.parse
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not getattr(config, 'SMTP_USER', None) or not getattr(config, 'SMTP_PASSWORD', None):
        print("SMTP credentials not configured. Skipping email.")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config.SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = "Reset Your Password - Samshodhana Mandiram OTP"
        
        # Construct secure one-click report link
        report_url = f"{host_url}api/external/forgot-password/report?email={urllib.parse.quote(to_email)}&otp={otp}"
        
        # 1. Plain text fallback
        body_text = f"""Hello,

You have requested to reset your password for your Samshodhana Mandiram account.

Your 6-digit One-Time Password (OTP) is:
{otp}

This OTP is valid for 10 minutes.

If you did not request this reset, please click the link below to deactivate the code and report the unauthorized attempt:
{report_url}

Best regards,
Samshodhana Mandiram Team"""

        # 2. Rich HTML email template matching the website branding
        body_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset Your Password</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f8fafc; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;">
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8fafc; padding: 40px 20px;">
        <tr>
            <td align="center">
                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 500px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05), 0 8px 10px -6px rgba(0, 0, 0, 0.05); border: 1px solid #e2e8f0;">
                    <!-- Top Gradient Header Bar -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 28px; text-align: center;">
                            <span style="font-size: 32px; display: block; margin-bottom: 8px;">📖</span>
                            <span style="color: #ffffff; font-size: 20px; font-weight: 700; letter-spacing: 0.5px; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;">Samshodhana Mandiram</span>
                        </td>
                    </tr>
                    <!-- Main Body -->
                    <tr>
                        <td style="padding: 40px 32px; text-align: center; background-color: #ffffff;">
                            <h2 style="margin: 0 0 16px 0; color: #0f172a; font-size: 22px; font-weight: 700; letter-spacing: -0.5px;">Reset Your Password</h2>
                            <p style="margin: 0 0 20px 0; color: #475569; font-size: 15px; line-height: 1.6; text-align: left;">
                                Hello,
                            </p>
                            <p style="margin: 0 0 28px 0; color: #475569; font-size: 15px; line-height: 1.6; text-align: left;">
                                We received a request to reset the password for your Samshodhana Mandiram account. Please use the following 6-digit One-Time Password (OTP) to complete your password reset:
                            </p>
                            
                            <!-- OTP Badge -->
                            <div style="background-color: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 12px; padding: 18px 24px; margin: 24px 0; display: inline-block;">
                                <span style="font-family: 'Courier New', Courier, monospace; font-size: 36px; font-weight: 800; color: #6d28d9; letter-spacing: 6px; display: block;">{otp}</span>
                            </div>
                            
                            <!-- Report Action -->
                            <div style="margin: 32px 0; text-align: center;">
                                <p style="margin: 0 0 12px 0; color: #64748b; font-size: 14px; line-height: 1.5; text-align: center;">
                                    Did not request this reset? Secure your account:
                                </p>
                                <a href="{report_url}" style="display: inline-block; background-color: #ef4444; border: 1px solid #dc2626; border-radius: 10px; padding: 12px 24px; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 600; box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2); transition: all 0.2s;">
                                    Report Unauthorized Request
                                </a>
                            </div>
                            
                            <p style="margin: 0 0 24px 0; color: #64748b; font-size: 13px; line-height: 1.5; text-align: left; background-color: #f8fafc; padding: 14px 18px; border-radius: 10px; border-left: 4px solid #818cf8;">
                                <strong>Note:</strong> This OTP is valid for <strong>10 minutes</strong>.
                            </p>
                            
                            <hr style="border: 0; border-top: 1px solid #f1f5f9; margin: 32px 0 24px 0;">
                            
                            <p style="margin: 0; color: #475569; font-size: 14px; line-height: 1.6; text-align: left;">
                                Best regards,<br>
                                <strong style="color: #0f172a;">Samshodhana Mandiram Team</strong>
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8fafc; padding: 24px; text-align: center; border-top: 1px solid #f1f5f9;">
                            <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 12px; line-height: 1.5;">
                                This is an automated email. Please do not reply directly.
                            </p>
                            <p style="margin: 0; color: #94a3b8; font-size: 12px; line-height: 1.5;">
                                &copy; 2026 Samshodhana Mandiram. All rights reserved.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""

        # Attach both formats - clients will choose the best one (usually HTML)
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        context = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending OTP email: {e}")
        return False


def send_vector_approval_email(to_email, book_name, unique_key):
    """Send vector DB download approval decryption key to user via email."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    if not getattr(config, 'SMTP_USER', None) or not getattr(config, 'SMTP_PASSWORD', None):
        print("SMTP credentials not configured. Skipping approval email.")
        return False
        
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = config.SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = f"Approved: Vector DB Access Key for {book_name}"
        
        # 1. Plain text version
        body_text = f"""Hello,
        
Your request to download the vector database (embeddings) for "{book_name}" has been APPROVED by the Super Administrator!

Here is your unique decryption key to open the downloaded file:
{unique_key}

This key is required to decrypt the vector data for non-commercial AI usage.
You can download the dataset directly from your profile tab under "Vector Downloads".
Refer to the "guidelines.html" file inside the downloaded ZIP archive for instructions and a Python code snippet to load the data.

Best regards,
Sanskrit Digital Library Team"""

        # 2. HTML version with beautiful styling matching the theme
        body_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }}
                .container {{ max-width: 600px; background: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); padding: 30px; margin: 0 auto; }}
                .header {{ border-bottom: 2px solid #3b82f6; padding-bottom: 15px; margin-bottom: 25px; }}
                .title {{ font-size: 20px; font-weight: bold; color: #1e3a8a; margin: 0; }}
                .greeting {{ font-size: 16px; margin-bottom: 15px; }}
                .content {{ font-size: 14px; line-height: 1.6; margin-bottom: 25px; }}
                .key-box {{ background-color: #eff6ff; border: 1px dashed #3b82f6; border-radius: 8px; padding: 15px; text-align: center; margin: 20px 0; }}
                .key {{ font-family: 'Courier New', Courier, monospace; font-size: 18px; font-weight: bold; color: #2563eb; letter-spacing: 1px; word-break: break-all; }}
                .footer {{ font-size: 12px; color: #6b7280; border-top: 1px solid #e5e7eb; padding-top: 15px; margin-top: 25px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 class="title">🔑 Vector DB Access Key Approved</h2>
                </div>
                <div class="greeting">Hello,</div>
                <div class="content">
                    <p>Your request to download the vector database (embeddings) for <strong>"{book_name}"</strong> has been approved by the Super Administrator.</p>
                    <p>Below is your unique decryption key. You will need this key to decrypt the downloaded ZIP data.</p>
                    
                    <div class="key-box">
                        <span class="key">{unique_key}</span>
                    </div>
                    
                    <p>You can download the dataset directly from your profile tab under <strong>Vector Downloads</strong>. Refer to the <code>guidelines.html</code> file inside the downloaded ZIP for instructions and a Python code snippet to decrypt and load the vector data.</p>
                </div>
                <div class="footer">
                    This email is auto-generated. Please do not reply directly to this message.<br>
                    &copy; Sanskrit Digital Library
                </div>
            </div>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body_text, 'plain'))
        msg.attach(MIMEText(body_html, 'html'))
        
        context = ssl.create_default_context()
        with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending vector approval email to {to_email}: {e}")
        return False


@app.route('/api/external/forgot-password/request', methods=['POST'])
def external_forgot_password_request():
    import secrets
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400
        
    # Check if user exists
    user = common_db.get_user_by_email(email)
    if not user:
        return jsonify({'success': False, 'error': 'No account found with this email address'}), 404
        
    # Generate 6-digit OTP
    otp = "".join(secrets.choice("0123456789") for _ in range(6))
    
    # Save OTP to database
    if not common_db.save_otp(email, otp):
        return jsonify({'success': False, 'error': 'Failed to generate OTP. Please try again.'}), 500
        
    # Send email
    if send_otp_email(email, otp, request.host_url):
        return jsonify({'success': True, 'message': 'OTP sent successfully to your email'})
    else:
        return jsonify({'success': False, 'error': 'Failed to send email OTP. Please check server SMTP configuration.'}), 500


@app.route('/api/external/forgot-password/report', methods=['GET'])
def external_forgot_password_report():
    email = request.args.get('email', '').strip().lower()
    otp = request.args.get('otp', '').strip()
    
    if not email or not otp:
        return "Invalid report request. Missing parameters.", 400
        
    conn = common_db.get_db()
    try:
        # Check if the OTP is currently active
        row = conn.execute('SELECT otp FROM user_otps WHERE email = ?', (email,)).fetchone()
        if not row or row['otp'] != otp:
            # Already consumed, expired, or invalid
            return render_report_template(
                success=False, 
                message="This link is invalid or has already expired. Your account is already secure."
            )
            
        # Invalidate OTP immediately
        conn.execute('DELETE FROM user_otps WHERE email = ?', (email,))
        conn.commit()
    except Exception as e:
        app.logger.error(f"Error invalidating OTP during report: {e}")
        return "An error occurred. Please try again later.", 500
    finally:
        conn.close()
        
    # Send email notification to Admin
    send_admin_report_email(email)
    
    return render_report_template(
        success=True, 
        message=f"Your account is secure. The temporary reset code has been deactivated, and the administrator has been notified."
    )


@app.route('/api/external/forgot-password/reset', methods=['POST'])
def external_forgot_password_reset():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    otp = data.get('otp', '').strip()
    new_password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not email or not otp or not new_password or not confirm_password:
        return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        
    if len(new_password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        
    # Check if user exists
    user = common_db.get_user_by_email(email)
    if not user:
        return jsonify({'success': False, 'error': 'No account found with this email address'}), 404
        
    # Verify OTP
    if not common_db.verify_otp(email, otp, max_age_seconds=600):
        return jsonify({'success': False, 'error': 'Invalid or expired OTP. Please try again.'}), 400
        
    # Reset Password
    success, message = common_db.reset_user_password(user['id'], new_password)
    if success:
        return jsonify({'success': True, 'message': 'Password has been reset successfully. You can now login.'})
    else:
        return jsonify({'success': False, 'error': message}), 500


@app.route('/api/external/register', methods=['POST'])
def external_register():
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    mobile = data.get('mobile', '').strip()
    display_name = data.get('display_name', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not email or not mobile or not password:
        return jsonify({'success': False, 'error': 'Email, Mobile, and Password are required'}), 400

    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400

    success, message, user_id = common_db.create_user(email, password, mobile, display_name)
    if success:
        return jsonify({
            'success': True,
            'message': 'Registration successful! Please login.',
            'user_id': user_id
        })
    else:
        return jsonify({'success': False, 'error': message}), 400


@app.route('/api/external/login', methods=['POST'])
def external_login():
    import secrets
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'success': False, 'error': 'Email and Password are required'}), 400


    # 1. Check admins.json first
    stored_username, admin_data = common_db.get_admin_by_username(email)
    if stored_username:
        if common_db.verify_password(password, admin_data['password_hash']):
            admin_email = f"{stored_username.lower()}@system.local"
            conn = common_db.get_db()
            row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
            conn.close()
            
            if row:
                admin_user_id = row['id']
            else:
                # Create a shadow sqlite user to support token mapping & database consistency
                success, msg, admin_user_id = common_db.create_user(
                    admin_email, 
                    secrets.token_hex(16), 
                    '0000000000', 
                    stored_username.upper()
                )
            
            if admin_user_id:
                token = common_db.create_user_token(admin_user_id)
                if token:
                    session['logged_in'] = True
                    session['admin_username'] = stored_username.upper()
                    if stored_username.upper() == 'SUPERADMIN':
                        session['admin_role'] = 'super'
                        session['admin_permissions'] = common_db.ALL_PERMISSIONS
                    else:
                        session['admin_role'] = 'low-level'
                        session['admin_permissions'] = admin_data.get('permissions', [])
                    
                    admin_user = common_db.get_user_by_id(admin_user_id)
                    admin_avatar = get_avatar_for_id(admin_user_id, admin_user.get('avatar_idx', 0) if admin_user else 0)
                    return jsonify({
                        'success': True,
                        'token': token,
                        'user': {
                            'id': admin_user_id,
                            'email': admin_email,
                            'mobile': '0000000000',
                            'display_name': stored_username.upper(),
                            'role': 'super' if stored_username.upper() == 'SUPERADMIN' else 'admin',
                            'avatar_emoji': admin_avatar['emoji'],
                            'avatar_gradient': admin_avatar['gradient'],
                            'profile_pic': admin_user.get('profile_pic') if admin_user else None
                        }
                    })
                else:
                    return jsonify({'success': False, 'error': 'Failed to generate session token'}), 500
        else:
            return jsonify({'success': False, 'error': 'Incorrect password for this account.', 'error_type': 'password'}), 401

    # 2. Check SQLite users table
    user_record = common_db.get_user_by_email(email)
    if user_record:
        user = common_db.verify_user(email, password)
        if user:
            token = common_db.create_user_token(user['id'])
            if token:
                session['user_logged_in'] = True
                session['user_id'] = user['id']
                session['user_email'] = user['email']
                session['user_display_name'] = user['display_name'] or user['email'].split('@')[0]
                
                user_avatar = get_avatar_for_id(user['id'], user.get('avatar_idx', 0))
                return jsonify({
                    'success': True,
                    'token': token,
                    'user': {
                        'id': user['id'],
                        'email': user['email'],
                        'mobile': user['mobile'],
                        'display_name': user['display_name'] or user['email'].split('@')[0],
                        'role': 'user',
                        'avatar_emoji': user_avatar['emoji'],
                        'avatar_gradient': user_avatar['gradient'],
                        'profile_pic': user.get('profile_pic')
                    }
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to generate session token'}), 500
        else:
            return jsonify({'success': False, 'error': 'Incorrect password for this account.', 'error_type': 'password'}), 401
    
    return jsonify({'success': False, 'error': 'Account not found with this email.', 'error_type': 'email'}), 401


def token_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        token = None
        if auth_header.lower().startswith('bearer '):
            token = auth_header[7:].strip()
        else:
            token = request.headers.get('X-User-Token')

        if not token:
            token = request.args.get('token')

        user_id = common_db.verify_user_token(token)
        if not user_id:
            return jsonify({'success': False, 'error': 'Unauthorized or invalid token'}), 401

        request.user_id = user_id
        request.user_token = token
        return f(*args, **kwargs)
    return decorated


@app.route('/api/external/logout', methods=['POST'])
@token_auth_required
def external_logout():
    common_db.delete_user_token(request.user_token)
    session.clear()
    resp = jsonify({'success': True, 'message': 'Logged out successfully'})
    resp.set_cookie('session', '', expires=0, max_age=0, path='/', httponly=True, samesite='Lax')
    return resp


@app.route('/api/external/session-sync', methods=['POST'])
def external_session_sync():
    import secrets
    
    # 1. Check if Flask session is logged in (either as user or admin)
    is_user = session.get('user_logged_in', False)
    is_admin = session.get('logged_in', False)
    
    if is_admin:
        admin_username = session.get('admin_username', '').upper()
        admin_email = f"{admin_username.lower()}@system.local"
        
        conn = common_db.get_db()
        row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
        conn.close()
        
        if row:
            admin_user_id = row['id']
        else:
            success, msg, admin_user_id = common_db.create_user(
                admin_email,
                secrets.token_hex(16),
                '0000000000',
                admin_username
            )
            
        if admin_user_id:
            conn = common_db.get_db()
            token_row = conn.execute('SELECT token FROM user_tokens WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (admin_user_id,)).fetchone()
            conn.close()
            
            token = token_row['token'] if token_row else common_db.create_user_token(admin_user_id)
            if token:
                admin_user = common_db.get_user_by_id(admin_user_id)
                admin_avatar = get_avatar_for_id(admin_user_id, admin_user.get('avatar_idx', 0) if admin_user else 0)
                return jsonify({
                    'logged_in': True,
                    'token': token,
                    'user': {
                        'id': admin_user_id,
                        'email': admin_email,
                        'mobile': '0000000000',
                        'display_name': admin_username,
                        'role': 'super' if admin_username == 'SUPERADMIN' else 'admin',
                        'avatar_emoji': admin_avatar['emoji'],
                        'avatar_gradient': admin_avatar['gradient'],
                        'profile_pic': admin_user.get('profile_pic') if admin_user else None
                    }
                })

    elif is_user and session.get('user_id'):
        user_id = session.get('user_id')
        user = common_db.get_user_by_id(user_id)
        if user:
            conn = common_db.get_db()
            token_row = conn.execute('SELECT token FROM user_tokens WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (user_id,)).fetchone()
            conn.close()
            
            token = token_row['token'] if token_row else common_db.create_user_token(user_id)
            if token:
                user_avatar = get_avatar_for_id(user_id, user.get('avatar_idx', 0))
                return jsonify({
                    'logged_in': True,
                    'token': token,
                    'user': {
                        'id': user['id'],
                        'email': user['email'],
                        'mobile': user['mobile'],
                        'display_name': user['display_name'] or user['email'].split('@')[0],
                        'role': 'user',
                        'avatar_emoji': user_avatar['emoji'],
                        'avatar_gradient': user_avatar['gradient'],
                        'profile_pic': user.get('profile_pic')
                    }
                })

    # 2. If not logged in in Flask session, but a valid token is provided in the request headers/args,
    # automatically log them in to Flask session!
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.lower().startswith('bearer '):
        token = auth_header[7:].strip()
    else:
        token = request.args.get('token')
        
    if token:
        user_id = common_db.verify_user_token(token)
        if user_id:
            user = common_db.get_user_by_id(user_id)
            if user:
                if user['email'].endswith('@system.local'):
                    # Admin
                    username = user['display_name'].upper()
                    session['logged_in'] = True
                    session['admin_username'] = username
                    if username == 'SUPERADMIN':
                        session['admin_role'] = 'super'
                        session['admin_permissions'] = common_db.ALL_PERMISSIONS
                    else:
                        session['admin_role'] = 'low-level'
                        stored_username, admin_data = common_db.get_admin_by_username(username)
                        session['admin_permissions'] = admin_data.get('permissions', []) if admin_data else []
                    
                    common_db.update_last_login(username)
                    admin_avatar = get_avatar_for_id(user['id'], user.get('avatar_idx', 0))
                    return jsonify({
                        'logged_in': True,
                        'token': token,
                        'user': {
                            'id': user['id'],
                            'email': user['email'],
                            'mobile': user['mobile'],
                            'display_name': username,
                            'role': 'super' if username == 'SUPERADMIN' else 'admin',
                            'avatar_emoji': admin_avatar['emoji'],
                            'avatar_gradient': admin_avatar['gradient'],
                            'profile_pic': user.get('profile_pic')
                        }
                    })
                else:
                    # Regular User
                    session['user_logged_in'] = True
                    session['user_id'] = user['id']
                    session['user_email'] = user['email']
                    session['user_display_name'] = user['display_name'] or user['email'].split('@')[0]
                    user_avatar = get_avatar_for_id(user['id'], user.get('avatar_idx', 0))
                    return jsonify({
                        'logged_in': True,
                        'token': token,
                        'user': {
                            'id': user['id'],
                            'email': user['email'],
                            'mobile': user['mobile'],
                            'display_name': user['display_name'],
                            'role': 'user',
                            'avatar_emoji': user_avatar['emoji'],
                            'avatar_gradient': user_avatar['gradient'],
                            'profile_pic': user.get('profile_pic')
                        }
                    })

    return jsonify({'logged_in': False})


@app.route('/api/external/profile', methods=['GET'])
@token_auth_required
def external_profile():
    user = common_db.get_user_by_id(request.user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    # Fetch quiz history
    history = quiz_db.get_user_quiz_results(request.user_id)

    # Determine role
    role = 'user'
    if user['email'].endswith('@system.local'):
        role = 'super' if user['display_name'].upper() == 'SUPERADMIN' else 'admin'

    user_avatar = get_avatar_for_id(user['id'], user.get('avatar_idx', 0))
    return jsonify({
        'success': True,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'mobile': user['mobile'],
            'display_name': user['display_name'],
            'role': role,
            'avatar_emoji': user_avatar['emoji'],
            'avatar_gradient': user_avatar['gradient'],
            'profile_pic': user.get('profile_pic')
        },
        'quiz_history': history
    })


@app.route('/api/external/quiz/submit', methods=['POST'])
def external_quiz_submit():
    # Retrieve user token optionally (fallback to guest submission)
    auth_header = request.headers.get('Authorization', '')
    token = None
    if auth_header.lower().startswith('bearer '):
        token = auth_header[7:].strip()
    else:
        token = request.headers.get('X-User-Token')

    if not token:
        token = request.args.get('token')

    user_id = common_db.verify_user_token(token) if token else None

    data = request.get_json() or {}
    subject = data.get('subject', '').strip()
    level = data.get('level', '').strip()
    score = data.get('score')
    total = data.get('total')
    lang = data.get('lang', 'sa').strip()
    guest_name = data.get('guest_name', '').strip() or None

    if not subject or not level or score is None or total is None:
        return jsonify({'success': False, 'error': 'Missing quiz result metrics'}), 400

    try:
        score = int(score)
        total = int(total)
        percentage = round((score / total) * 100) if total > 0 else 0
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Invalid score or total format'}), 400

    if not user_id:
        user_id = 0  # 0 denotes a guest user attempt
        if not guest_name:
            guest_name = 'Guest'

    result_id = quiz_db.save_quiz_result(user_id, subject, level, score, total, percentage, lang, guest_name=guest_name)
    if result_id:
        return jsonify({
            'success': True,
            'message': 'Quiz score saved successfully',
            'result_id': result_id
        })
    
    return jsonify({'success': False, 'error': 'Failed to save score to database'}), 500


@app.route('/api/external/quiz/history', methods=['GET'])
@token_auth_required
def external_quiz_history():
    history = quiz_db.get_user_quiz_results(request.user_id)
    return jsonify({
        'success': True,
        'quiz_history': history
    })


@app.route('/api/external/<path:path>', methods=['OPTIONS'])
def external_api_preflight(path):
    response = make_response()
    return response


# =============================================================================
# AI SEMANTIC SEARCH & EMBEDDINGS SYSTEM
# =============================================================================

AI_TASKS_DIR = os.path.join(tempfile.gettempdir(), 'sdl_ai_tasks')
os.makedirs(AI_TASKS_DIR, exist_ok=True)

def get_ai_task(task_id):
    path = os.path.join(AI_TASKS_DIR, f"{task_id}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_ai_task(task_id, data):
    path = os.path.join(AI_TASKS_DIR, f"{task_id}.json")
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except Exception:
        pass

def delete_ai_task(task_id):
    path = os.path.join(AI_TASKS_DIR, f"{task_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass


@app.route('/admin/ai/stats', methods=['GET'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_stats():
    import ai_search
    stats = ai_search.get_db_stats()
    return jsonify(stats)


@app.route('/admin/ai/book_status', methods=['GET'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_book_status():
    import ai_search
    upload_folder = app.config['UPLOAD_FOLDER']
    books = sorted([d for d in os.listdir(upload_folder) if os.path.isdir(os.path.join(upload_folder, d))])
    status = ai_search.get_book_embedding_status(books)
    return jsonify(status)


@app.route('/admin/ai/embed', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_embed():
    import ai_search
    api_key = ai_search.load_api_key()
    if not api_key:
        return jsonify({'error': 'AI API key is not configured. Please save it first.'}), 400
        
    books_json = request.form.get('books')
    if not books_json:
        return jsonify({'error': 'No books selected'}), 400
        
    upload_folder = app.config['UPLOAD_FOLDER']
    if books_json == 'all':
        books = sorted([d for d in os.listdir(upload_folder) if os.path.isdir(os.path.join(upload_folder, d))])
    else:
        try:
            books = json.loads(books_json)
        except Exception:
            return jsonify({'error': 'Invalid books list format'}), 400
            
    if not books:
        return jsonify({'error': 'No books selected'}), 400
        
    task_id = str(uuid.uuid4())
    initial_task_state = {
        'status': 'preparing',
        'progress': 0,
        'total_books': len(books),
        'current_book_index': 0,
        'current_book_name': '',
        'total_chunks': 0,
        'processed_chunks': 0,
        'error': None,
        'cancelled': False
    }
    save_ai_task(task_id, initial_task_state)
    
    admin_user = session.get('admin_username')
    
    def process_embeddings():
        try:
            for idx, book_name in enumerate(books):
                task = get_ai_task(task_id)
                if not task:
                    break
                if task.get('cancelled'):
                    raise InterruptedError('Cancelled by user')
                    
                task['status'] = 'processing'
                task['current_book_index'] = idx
                task['current_book_name'] = book_name
                task['progress'] = int((idx / len(books)) * 100)
                save_ai_task(task_id, task)
                
                def inner_progress_callback(processed, total):
                    t = get_ai_task(task_id)
                    if not t or t.get('cancelled'):
                        return False
                    t['total_chunks'] = total
                    t['processed_chunks'] = processed
                    local_progress = int((idx / len(books)) * 100 + (processed / total) * (100 / len(books)))
                    t['progress'] = min(99, local_progress)
                    save_ai_task(task_id, t)
                    return True
                    
                success, err = ai_search.embed_book(book_name, upload_folder, api_key, inner_progress_callback)
                if not success:
                    raise Exception(f"Failed to embed book '{book_name}': {err}")
                    
            task = get_ai_task(task_id)
            if task:
                task['status'] = 'done'
                task['progress'] = 100
                save_ai_task(task_id, task)
                log_change(admin_user, 'GENERATE', 'AI_EMBEDDINGS', f"Generated embeddings for {len(books)} books")
                threading.Timer(300.0, lambda: delete_ai_task(task_id)).start()
                
        except InterruptedError:
            task = get_ai_task(task_id)
            if task:
                task['status'] = 'cancelled'
                save_ai_task(task_id, task)
                threading.Timer(60.0, lambda: delete_ai_task(task_id)).start()
        except Exception as e:
            task = get_ai_task(task_id)
            if task:
                task['status'] = 'error'
                task['error'] = str(e)
                save_ai_task(task_id, task)
                threading.Timer(600.0, lambda: delete_ai_task(task_id)).start()
                
    thread = threading.Thread(target=process_embeddings, daemon=True)
    thread.start()
    
    return jsonify({'task_id': task_id, 'total_books': len(books)})


@app.route('/admin/ai/embed_progress/<task_id>', methods=['GET'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_embed_progress(task_id):
    task = get_ai_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/admin/ai/cancel_embed/<task_id>', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_cancel_embed(task_id):
    task = get_ai_task(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
        
    task['cancelled'] = True
    save_ai_task(task_id, task)
    return jsonify({'success': True, 'message': 'Cancellation requested.'})


@app.route('/admin/ai/delete_embeddings', methods=['POST'])
@login_required
@permission_required('PERM_MANAGE_AI')
def admin_ai_delete_embeddings():
    import ai_search
    books_json = request.form.get('books')
    if not books_json:
        return jsonify({'error': 'No books selected'}), 400
        
    try:
        books = json.loads(books_json)
    except Exception:
        return jsonify({'error': 'Invalid books list format'}), 400
        
    success_count = 0
    for book_name in books:
        if ai_search.delete_book_embeddings(book_name):
            success_count += 1
            
    log_change(session.get('admin_username'), 'DELETE', 'AI_EMBEDDINGS', f"Deleted embeddings for {success_count} books")
    return jsonify({'success': True, 'message': f'Deleted embeddings for {success_count} books.'})


@app.route('/search/semantic/stats', methods=['GET'])
def public_search_semantic_stats():
    """Public stats endpoint: returns total embedded chunks for users with semantic search access."""
    import ai_search
    if not check_semantic_search_access():
        return jsonify({'error': 'Access restricted'}), 403
    try:
        stats = ai_search.get_db_stats()
        return jsonify({
            'total_chunks': stats.get('total_chunks', 0),
            'storage_size': stats.get('storage_size', '0 B'),
            'last_updated': stats.get('last_updated', 'Never')
        })
    except Exception as e:
        return jsonify({'total_chunks': 0, 'storage_size': '0 B', 'last_updated': 'Never'})


@app.route('/search/semantic', methods=['GET'])
def public_search_semantic():
    import ai_search
    
    is_admin = session.get('logged_in', False)
    user_id = session.get('user_id')
    is_super = session.get('admin_role') == 'super'
    
    role = 'non_logged_in'
    if is_admin:
        role = 'admin'
    elif user_id:
        role = 'logged_in'

    # Access evaluation
    if not check_semantic_search_access():
        if role == 'non_logged_in':
            return jsonify({'error': 'AI Search is only available after login. Please log in first.'}), 401
        return jsonify({'error': 'Access to Semantic Search is restricted by the administrator.'}), 403

    api_key = ai_search.load_api_key() or common_db.get_any_admin_gemini_key()
    if not api_key:
        return jsonify({'error': 'AI service is currently unavailable. Please contact system administrator.'}), 400

    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})
        
    tags_param = request.args.get('tags', '').strip()
    tags_filter = [t.strip() for t in tags_param.split(',') if t.strip()] if tags_param else None
    
    books_param = request.args.get('books', '').strip()
    book_filter = [b.strip() for b in books_param.split(',') if b.strip()] if books_param else None
    
    top_k_str = request.args.get('top_k', '10')
    try:
        top_k = int(top_k_str)
        top_k = max(1, min(50, top_k))
    except ValueError:
        top_k = 10
        
    try:
        is_admin_user = is_admin_user_session()
        mode = request.args.get('mode', 'semantic').strip().lower()
        if mode == 'keyword':
            results, expanded_keywords = ai_search.keyword_search(query, api_key, tags_filter, book_filter, top_k, include_unpublished=is_admin_user)
            if user_id:
                common_db.log_user_ai_usage(user_id, 'semantic_search', success=True)
            return jsonify({'results': results, 'mode': 'keyword', 'expanded_keywords': expanded_keywords})
        else:
            skip_disambiguation = request.args.get('skip_disambiguation', '0') == '1'
            if not skip_disambiguation:
                try:
                    ambiguity_res = ai_search.check_query_ambiguity(query, api_key)
                    if ambiguity_res and ambiguity_res.get('status') == 'ambiguous':
                        return jsonify(ambiguity_res)
                except Exception as e:
                    print(f"Ambiguity check error: {e}")

            results = ai_search.semantic_search(query, api_key, tags_filter, book_filter, top_k, include_unpublished=is_admin_user)
            if user_id:
                common_db.log_user_ai_usage(user_id, 'semantic_search', success=True)
            return jsonify({'results': results, 'mode': 'semantic'})
    except Exception as e:
        if user_id:
            common_db.log_user_ai_usage(user_id, 'semantic_search', success=False)
        # Bug #10 fix: return structured JSON error instead of bare re-raise (which causes unformatted 500)
        err_msg = str(e)
        if config.is_gemini_quota_error(e):
            return jsonify({'error': 'The AI search quota has been exhausted. Please try again later or configure your own AI API Key.'}), 429
        return jsonify({'error': f'Semantic search error: {err_msg}'}), 500


@app.route('/search/semantic/summarize', methods=['POST'])
def public_search_semantic_summarize():
    import ai_search
    data = request.get_json() or {}
    query = data.get('q', '').strip()
    results = data.get('results', [])
    
    if not query:
        return jsonify({'error': 'Query is empty'}), 400
        
    is_admin = session.get('logged_in', False)
    user_id = session.get('user_id')
    is_super = session.get('admin_role') == 'super'
    
    role = 'non_logged_in'
    if is_admin:
        role = 'admin'
    elif user_id:
        role = 'logged_in'

    # Access evaluation
    if not check_semantic_search_access():
        if role == 'non_logged_in':
            return jsonify({'error': 'AI features are only available after login. Please log in first.'}), 401
        return jsonify({'error': 'Access to Semantic Search is restricted by the administrator.'}), 403

    api_key = ai_search.load_api_key() or common_db.get_any_admin_gemini_key()
    if not api_key:
        return jsonify({'error': 'AI service is currently unavailable. Please contact system administrator.'}), 400
        
    try:
        summary = ai_search.summarize_results(query, results, api_key)
        if user_id:
            common_db.log_user_ai_usage(user_id, 'semantic_search', success=True)
        return jsonify({'summary': summary})
    except Exception as e:
        if user_id:
            common_db.log_user_ai_usage(user_id, 'semantic_search', success=False)
        # Bug #10 fix: return structured JSON error instead of bare re-raise
        err_msg = str(e)
        if config.is_gemini_quota_error(e):
            return jsonify({'error': 'The AI quota has been exhausted. Please try again later or configure your own AI API Key.'}), 429
        return jsonify({'error': f'Summarization error: {err_msg}'}), 500


# =============================================================================
# TAXONOMY & CATEGORY MANAGEMENT SYSTEM
# =============================================================================
TAXONOMY_FILE = os.path.join(os.path.dirname(__file__), 'taxonomy.json')

def get_default_taxonomy():
    return {
        "version": "1.0",
        "nodes": []
    }

def load_taxonomy():
    if os.path.exists(TAXONOMY_FILE):
        try:
            with open(TAXONOMY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'nodes' in data:
                    return data
        except Exception as e:
            print("Error loading taxonomy.json:", e)
    default_data = get_default_taxonomy()
    save_taxonomy(default_data)
    return default_data

def save_taxonomy(data):
    try:
        with open(TAXONOMY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("Error saving taxonomy.json:", e)
        return False

def get_allowed_tags_set():
    tax = load_taxonomy()
    allowed = set()
    for node in tax.get('nodes', []):
        tags = node.get('tags') or []
        if isinstance(tags, (list, tuple, set)):
            for t in tags:
                if isinstance(t, str) and t.strip():
                    allowed.add(t.strip())
    return allowed

def extract_tags_list(tags_raw):
    if not tags_raw:
        return []
    if isinstance(tags_raw, (list, tuple, set)):
        return [str(t).strip() for t in tags_raw if str(t).strip()]
    if isinstance(tags_raw, str):
        return [t.strip() for t in tags_raw.split(',') if t.strip()]
    return []

def sanitize_tags_against_taxonomy(tags_input, published=True):
    """
    Sanitize comma-separated tags string or list of tags.
    If published is True, only tags present in taxonomy.json are returned.
    If published is False (Draft mode), any tags are permitted as-is.
    """
    submitted = extract_tags_list(tags_input)

    if not published:
        return ', '.join(submitted)

    allowed_set = get_allowed_tags_set()
    valid_tags = [t for t in submitted if t in allowed_set]
    return ', '.join(valid_tags)


def get_taxonomy_metrics(include_unpublished=False):
    tax = load_taxonomy()
    all_books = get_all_books(bypass_cache=False, include_unpublished=include_unpublished)
    
    tag_counts = {}
    unlisted_tags_count = {}
    allowed_set = get_allowed_tags_set()
    
    total_books_counted = len(all_books)
    books_with_tags = 0

    for book in all_books:
        b_tags = extract_tags_list(book.get('tags'))
        if b_tags:
            books_with_tags += 1
        for t in b_tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
            if t not in allowed_set:
                unlisted_tags_count[t] = unlisted_tags_count.get(t, 0) + 1

    nodes = tax.get('nodes', [])

    for node in nodes:
        node.pop('parent_id', None)
        node_tags = set(extract_tags_list(node.get('tags')))
        node_book_names = set()
        total_node_tag_uses = 0
        for book in all_books:
            b_tags = extract_tags_list(book.get('tags'))
            b_name = book.get('name') or book.get('folder_name') or book.get('title')
            if any(t in node_tags for t in b_tags):
                if b_name:
                    node_book_names.add(b_name)
            for t in b_tags:
                if t in node_tags:
                    total_node_tag_uses += 1
        node['book_count'] = len(node_book_names)
        node['tag_uses_count'] = total_node_tag_uses
        node['tag_details'] = [
            {'name': t, 'count': tag_counts.get(t, 0)}
            for t in extract_tags_list(node.get('tags'))
        ]

    return {
        'version': tax.get('version', '1.0'),
        'nodes': nodes,
        'all_allowed_tags': sorted(list(allowed_set)),
        'unlisted_tags': [{'name': k, 'count': v} for k, v in sorted(unlisted_tags_count.items(), key=lambda x: x[1], reverse=True)],
        'stats': {
            'total_books': total_books_counted,
            'books_with_tags': books_with_tags,
            'total_nodes': len(nodes),
            'total_permitted_tags': len(allowed_set),
            'total_unlisted_tags': len(unlisted_tags_count)
        }
    }

@app.route('/admin/taxonomy')
@login_required
def admin_taxonomy_page():
    if session.get('admin_role') != 'super':
        return render_template('admin/forbidden.html', permission='SUPERADMIN'), 403
    return render_template('admin/admin_taxonomy.html')

@app.route('/api/v1/taxonomy', methods=['GET'])
def api_get_taxonomy():
    try:
        is_admin_user = is_admin_user_session()
        data = get_taxonomy_metrics(include_unpublished=is_admin_user)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/taxonomy/node', methods=['POST'])
@login_required
def api_save_taxonomy_node():
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Superadmin permission required'}), 403
    
    req_data = request.get_json() or {}
    node_id = req_data.get('id', '').strip() if req_data.get('id') else ''
    name_sa = req_data.get('name_sa', '').strip() if req_data.get('name_sa') else ''
    name_en = req_data.get('name_en', '').strip() if req_data.get('name_en') else ''
    icon = req_data.get('icon', '🏷️').strip() if req_data.get('icon') else '🏷️'
    color = req_data.get('color', '#3b82f6').strip() if req_data.get('color') else '#3b82f6'
    description = req_data.get('description', '').strip() if req_data.get('description') else ''
    
    tags_raw = req_data.get('tags')
    if isinstance(tags_raw, str):
        tags = [t.strip() for t in tags_raw.split(',') if t.strip()]
    elif isinstance(tags_raw, (list, tuple, set)):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []

    if not name_sa and not name_en:
        return jsonify({'error': 'Category name is required'}), 400

    tax = load_taxonomy()
    nodes = tax.get('nodes', [])

    if not node_id:
        node_id = 'cat_' + str(int(time.time() * 1000))
        new_node = {
            'id': node_id,
            'name_sa': name_sa,
            'name_en': name_en,
            'icon': icon,
            'color': color,
            'description': description,
            'tags': tags
        }
        nodes.append(new_node)
    else:
        found = False
        for node in nodes:
            if node['id'] == node_id:
                node['name_sa'] = name_sa
                node['name_en'] = name_en
                node['icon'] = icon
                node['color'] = color
                node.pop('parent_id', None)
                node['description'] = description
                node['tags'] = tags
                found = True
                break
        if not found:
            nodes.append({
                'id': node_id,
                'name_sa': name_sa,
                'name_en': name_en,
                'icon': icon,
                'color': color,
                'description': description,
                'tags': tags
            })

    tax['nodes'] = nodes
    if save_taxonomy(tax):
        return jsonify({'success': True, 'node_id': node_id, 'data': get_taxonomy_metrics()})
    return jsonify({'error': 'Failed to save taxonomy'}), 500

@app.route('/api/v1/taxonomy/node/<node_id>', methods=['DELETE'])
@login_required
def api_delete_taxonomy_node(node_id):
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Superadmin permission required'}), 403

    tax = load_taxonomy()
    nodes = tax.get('nodes', [])
    new_nodes = [n for n in nodes if n['id'] != node_id]

    if len(new_nodes) == len(nodes):
        return jsonify({'error': 'Node not found'}), 404

    for n in new_nodes:
        n.pop('parent_id', None)

    tax['nodes'] = new_nodes
    if save_taxonomy(tax):
        return jsonify({'success': True, 'data': get_taxonomy_metrics()})
    return jsonify({'error': 'Failed to delete taxonomy node'}), 500

@app.route('/api/v1/taxonomy/auto-register', methods=['POST'])
@login_required
def api_auto_register_tag():
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Superadmin permission required'}), 403

    req_data = request.get_json() or {}
    tag_name = req_data.get('tag', '').strip()
    target_node_id = req_data.get('node_id', '').strip()

    if not tag_name:
        return jsonify({'error': 'Tag name required'}), 400

    tax = load_taxonomy()
    nodes = tax.get('nodes', [])

    target_node = None
    if target_node_id:
        for n in nodes:
            if n['id'] == target_node_id:
                target_node = n
                break
    
    if not target_node and nodes:
        target_node = nodes[-1]

    if target_node:
        if tag_name not in target_node['tags']:
            target_node['tags'].append(tag_name)
        tax['nodes'] = nodes
        save_taxonomy(tax)
        return jsonify({'success': True, 'tag': tag_name, 'node_id': target_node['id'], 'data': get_taxonomy_metrics()})

    return jsonify({'error': 'No valid node found to add tag'}), 400

@app.route('/api/v1/taxonomy/validate-tags', methods=['POST'])
def api_validate_tags():
    req_data = request.get_json() or {}
    tags_input = req_data.get('tags', '')
    if isinstance(tags_input, str):
        submitted = [t.strip() for t in tags_input.split(',') if t.strip()]
    else:
        submitted = [str(t).strip() for t in tags_input if str(t).strip()]

    allowed_set = get_allowed_tags_set()
    permitted = [t for t in submitted if t in allowed_set]
    unlisted = [t for t in submitted if t not in allowed_set]

    return jsonify({
        'permitted': permitted,
        'unlisted': unlisted,
        'all_allowed': sorted(list(allowed_set)),
        'is_valid': len(unlisted) == 0
    })

@app.route('/api/v1/taxonomy/export', methods=['GET'])
@login_required
def api_export_taxonomy():
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Superadmin permission required'}), 403
    try:
        tax = load_taxonomy()
        nodes = tax.get('nodes', [])
        allowed_set = get_allowed_tags_set()
        all_books = get_all_books(bypass_cache=False, include_unpublished=True)

        # 1. Build catalog by tag & unlisted tags catalog
        tag_to_books = {}
        unlisted_tag_to_books = {}
        book_catalog_summary = []

        for book in all_books:
            folder_name = book.get('name') or book.get('folder_name', '')
            title = book.get('title') or book.get('name', '')
            author = book.get('author', '')
            b_tags_raw = book.get('tags', '') or ''
            b_tags = [t.strip() for t in b_tags_raw.split(',') if t.strip()]

            book_info = {
                'folder_name': folder_name,
                'title': title,
                'author': author,
                'tags': b_tags
            }
            book_catalog_summary.append(book_info)

            for tag in b_tags:
                if tag not in tag_to_books:
                    tag_to_books[tag] = []
                tag_to_books[tag].append({
                    'folder_name': folder_name,
                    'title': title,
                    'author': author
                })

                if tag not in allowed_set:
                    if tag not in unlisted_tag_to_books:
                        unlisted_tag_to_books[tag] = []
                    unlisted_tag_to_books[tag].append({
                        'folder_name': folder_name,
                        'title': title,
                        'author': author
                    })

        # 2. Build catalog by category node
        catalog_by_category = []
        for node in nodes:
            node_tags = set(extract_tags_list(node.get('tags')))
            matching_books = []
            for book in all_books:
                b_tags = extract_tags_list(book.get('tags'))
                if any(t in node_tags for t in b_tags):
                    matching_books.append({
                        'folder_name': book.get('name') or book.get('folder_name', ''),
                        'title': book.get('title') or book.get('name', ''),
                        'author': book.get('author', ''),
                        'matched_tags': [t for t in b_tags if t in node_tags],
                        'all_tags': b_tags
                    })
            catalog_by_category.append({
                'node_id': node.get('id'),
                'name_sa': node.get('name_sa'),
                'name_en': node.get('name_en'),
                'permitted_tags': extract_tags_list(node.get('tags')),
                'total_books_count': len(matching_books),
                'books': matching_books
            })

        # 3. Construct export payload
        export_payload = {
            'version': tax.get('version', '1.0'),
            'exported_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'system_purpose_and_organization': {
                'purpose': 'This taxonomy standardizes and categorizes digital Indological, Sanskrit, Vedic, Philosophical, and classical heritage texts in Samshodhanam. It provides a controlled vocabulary of permitted tags grouped under top-level category nodes to prevent tag drift, eliminate duplicates, and facilitate precise semantic research.',
                'how_organized': 'Organization: Top-Level Category Nodes (Sanskrit name, English name, icon, color, and description) -> Permitted Tags (curated vocabulary list defined under each node) -> Books (digitized texts assigned one or more tags).',
                'ai_analysis_guidelines': 'This JSON file contains the taxonomy schema, node definitions, permitted tag lists, unlisted/stray tag usages, and a complete catalog of books mapped to each tag/category.'
            },
            'summary_stats': {
                'total_category_nodes': len(nodes),
                'total_permitted_tags': len(allowed_set),
                'total_books_cataloged': len(all_books),
                'total_unlisted_tags_in_use': len(unlisted_tag_to_books)
            },
            'nodes': nodes,
            'catalog_by_category': catalog_by_category,
            'catalog_by_tag': tag_to_books,
            'unlisted_tags_catalog': unlisted_tag_to_books,
            'all_books_catalog': book_catalog_summary,
            'info': 'Samshodhanam Category & Tag Taxonomy System — Core Concept: Structured Indological knowledge classification.'
        }

        json_bytes = json.dumps(export_payload, ensure_ascii=False, indent=2).encode('utf-8')
        filename = f"taxonomy_export_{int(time.time())}.json"
        return Response(
            json_bytes,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/taxonomy/import', methods=['POST'])
@login_required
def api_import_taxonomy():
    if session.get('admin_role') != 'super':
        return jsonify({'error': 'Superadmin permission required'}), 403

    try:
        import_mode = request.form.get('mode') or 'merge'
        raw_data = None

        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                try:
                    file_content = file.read().decode('utf-8')
                    raw_data = json.loads(file_content)
                except Exception as e:
                    return jsonify({'error': f'Invalid JSON file format: {str(e)}'}), 400
        elif request.is_json:
            json_payload = request.get_json() or {}
            import_mode = json_payload.get('mode', import_mode)
            raw_data = json_payload.get('data') or json_payload

        if not raw_data:
            return jsonify({'error': 'No valid JSON taxonomy file or payload received.'}), 400

        nodes_to_import = []
        if isinstance(raw_data, dict):
            nodes_to_import = raw_data.get('nodes', [])
        elif isinstance(raw_data, list):
            nodes_to_import = raw_data

        if not isinstance(nodes_to_import, list):
            return jsonify({'error': 'Invalid taxonomy structure: expected a "nodes" array.'}), 400

        valid_nodes = []
        for idx, n in enumerate(nodes_to_import):
            if not isinstance(n, dict):
                continue
            node_id = str(n.get('id') or f"cat_{int(time.time()*1000)}_{idx}").strip()
            name_sa = str(n.get('name_sa') or n.get('name') or '').strip()
            name_en = str(n.get('name_en') or '').strip()
            if not name_sa and not name_en:
                continue

            icon = str(n.get('icon') or '📜').strip()
            color = str(n.get('color') or '#3b82f6').strip()
            description = str(n.get('description') or '').strip()
            tags = extract_tags_list(n.get('tags'))

            valid_nodes.append({
                'id': node_id,
                'name_sa': name_sa,
                'name_en': name_en,
                'icon': icon,
                'color': color,
                'description': description,
                'tags': list(dict.fromkeys(tags))
            })

        if not valid_nodes:
            return jsonify({'error': 'No valid category nodes found in the provided JSON.'}), 400

        current_tax = load_taxonomy()
        existing_nodes = current_tax.get('nodes', [])

        if import_mode == 'overwrite':
            current_tax['nodes'] = valid_nodes
            current_tax['version'] = str(raw_data.get('version', '1.0')) if isinstance(raw_data, dict) else '1.0'
        else:
            node_map = {n['id']: n for n in existing_nodes}
            for n in valid_nodes:
                nid = n['id']
                if nid in node_map:
                    target = node_map[nid]
                    if n['name_sa']: target['name_sa'] = n['name_sa']
                    if n['name_en']: target['name_en'] = n['name_en']
                    if n['icon']: target['icon'] = n['icon']
                    if n['color']: target['color'] = n['color']
                    target.pop('parent_id', None)
                    if n['description']: target['description'] = n['description']
                    merged_tags = list(dict.fromkeys(extract_tags_list(target.get('tags')) + extract_tags_list(n.get('tags'))))
                    target['tags'] = merged_tags
                else:
                    existing_nodes.append(n)
                    node_map[nid] = n
            current_tax['nodes'] = existing_nodes

        if save_taxonomy(current_tax):
            metrics = get_taxonomy_metrics()
            return jsonify({
                'success': True,
                'message': f"Taxonomy successfully imported ({len(valid_nodes)} categories in '{import_mode}' mode).",
                'mode': import_mode,
                'imported_count': len(valid_nodes),
                'data': metrics
            })
        else:
            return jsonify({'error': 'Failed to save imported taxonomy file to disk.'}), 500
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


# =============================================================================
# END APP ROUTES
# =============================================================================


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    print("Starting Archive OCR Web App...")
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Open http://localhost:{port} in your browser")
    print(f"Admin panel: http://localhost:{port}/admin")
    app.run(debug=True, host='0.0.0.0', port=port)
