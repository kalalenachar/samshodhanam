
"""
Samshodhana Mandiram — Unified Server Entry Point

Architecture:
  /         → static_app   : Landing page, quiz, katha, articles (static files)
  /admin    → admin_app    : Shared admin tools (Hub, Users, Admins)
  /sdl      → sdl_app      : Sanskrit Digital Library (browse, search, reader, AI, upload)

Usage:
  Development:  python server.py
  Production:   gunicorn --workers 4 --threads 4 --bind 127.0.0.1:8000 --timeout 600 server:application
"""

import os
import sys
from flask import Flask, send_from_directory, redirect, jsonify, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware

# Add project root and sdl_web directory to system path so all imports resolve correctly
base_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, base_dir)
sys.path.insert(0, os.path.join(base_dir, 'sdl_web'))

# Import apps and config
import config
from sdl import app as sdl_app
from admin_shared import shared_admin

# =============================================================================
# STATIC SITE APP (Landing Page, Quiz, Articles, Katha)
# =============================================================================

STATIC_SITE_DIR = base_dir

static_app = Flask(__name__, static_folder=None)
static_app.secret_key = config.SECRET_KEY

# Register Unified Sanskrit Apps Blueprint
from apps.backend import apps_bp
static_app.register_blueprint(apps_bp, url_prefix='/apps/api')

@static_app.route('/api/rigveda/<path:subpath>', methods=['GET', 'POST'])
def api_rigveda_alias(subpath):
    target = f"/apps/api/rigveda/{subpath}"
    if request.query_string:
        target += '?' + request.query_string.decode('utf-8')
    return redirect(target, 307)

@static_app.route('/favicon.ico')
def serve_favicon():
    return send_from_directory(STATIC_SITE_DIR, 'favicon.ico')


@static_app.route('/')
def serve_index():
    return send_from_directory(STATIC_SITE_DIR, 'index.html')


@static_app.route('/about')
def serve_about():
    return send_from_directory(STATIC_SITE_DIR, 'about.html')


@static_app.route('/digitization_cost_calculator.html')
@static_app.route('/digitization-cost-calculator')
def serve_digitization_calculator():
    return send_from_directory(STATIC_SITE_DIR, 'digitization_cost_calculator.html')


@static_app.route('/100dhatu')
@static_app.route('/100dhatu/')
@static_app.route('/dhatus-book')
@static_app.route('/dhatus_book.html')
def serve_dhatus_book():
    return redirect('/apps/dhatu_explorer/', 302)



@static_app.route('/katha')
def serve_katha():
    target = '/katha/'
    if request.query_string:
        target += '?' + request.query_string.decode('utf-8')
    return redirect(target, 301)


@static_app.route('/mobile.html')
def serve_mobile():
    return redirect('/about')


def query_db_scalar(db_name, sql):
    import sqlite3
    db_path = os.path.join(STATIC_SITE_DIR, 'db', db_name)
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(sql)
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception as e:
        print(f"Error querying db {db_name}: {e}")
        return 0


@static_app.route('/about-stats')
def serve_about_stats():
    stats = {
        "books": 0,
        "published_books": 0,
        "inprogress_books": 0,
        "proofread_pct": 0,
        "pages": 0,
        "chars": 0,
        "inprogress_proofread_pct": 0,
        "inprogress_pages": 0,
        "inprogress_chars": 0,
        "chunks": 0,
        "articles": 0,
        "stories": 0,
        "quizzes": 0,
        "quiz_submissions": 0,
        "games_played": 0,
        "users": 0
    }

    try:
        import math
        import sdl
        sdl.load_catalog_cache()
        all_books = sdl.get_all_books(include_unpublished=True)
        published_books = [b for b in all_books if b.get('published', True)]
        inprogress_books = [b for b in all_books if not b.get('published', True)]

        stats["books"] = len(published_books)
        stats["published_books"] = len(published_books)
        stats["inprogress_books"] = len(inprogress_books)

        if published_books:
            total_pct = sum(b.get('proofread_pct', 0) or 0 for b in published_books)
            avg_pct = total_pct / len(published_books)
            stats["proofread_pct"] = int(avg_pct) if avg_pct.is_integer() else round(avg_pct, 1)
        else:
            stats["proofread_pct"] = 0

        total_pages = 0
        total_chars = 0
        for b in published_books:
            b_meta = sdl.CATALOG_METADATA_CACHE.get(b['name'], {})
            p = b_meta.get('pages', 0)
            c = b_meta.get('chars', 0)
            if p == 0 and c > 0:
                p = max(1, math.ceil(c / 1500))
            total_pages += p
            total_chars += c
        stats["pages"] = total_pages
        stats["chars"] = total_chars

        if inprogress_books:
            total_pct_inp = sum(b.get('proofread_pct', 0) or 0 for b in inprogress_books)
            avg_pct_inp = total_pct_inp / len(inprogress_books)
            stats["inprogress_proofread_pct"] = int(avg_pct_inp) if avg_pct_inp.is_integer() else round(avg_pct_inp, 1)
        else:
            stats["inprogress_proofread_pct"] = 0

        total_pages_inp = 0
        total_chars_inp = 0
        for b in inprogress_books:
            b_meta = sdl.CATALOG_METADATA_CACHE.get(b['name'], {})
            p = b_meta.get('pages', 0)
            c = b_meta.get('chars', 0)
            if p == 0 and c > 0:
                p = max(1, math.ceil(c / 1500))
            total_pages_inp += p
            total_chars_inp += c
        stats["inprogress_pages"] = total_pages_inp
        stats["inprogress_chars"] = total_chars_inp
    except Exception as e:
        print(f"Error loading book metadata stats: {e}")

    try:
        import ai_search
        collection = ai_search.get_collection()
        if collection:
            stats["chunks"] = collection.count()
    except Exception as e:
        print(f"Error getting ChromaDB chunks count: {e}")

    stats["articles"] = query_db_scalar('articles.db', "SELECT COUNT(*) FROM articles WHERE status = 'published'")
    stats["stories"] = query_db_scalar('katha.db', "SELECT COUNT(*) FROM kathas WHERE status = 'published'")
    stats["quizzes"] = query_db_scalar('quiz.db', "SELECT COUNT(*) FROM quiz_questions")
    stats["quiz_submissions"] = query_db_scalar('quiz.db', "SELECT COUNT(*) FROM quiz_results")
    stats["games_played"] = query_db_scalar('play.db', "SELECT COUNT(*) FROM play_results")
    stats["users"] = query_db_scalar('common.db', "SELECT COUNT(*) FROM users")

    return jsonify(stats)


@static_app.route('/login')
def serve_login():
    return send_from_directory(STATIC_SITE_DIR, 'login.html')


@static_app.route('/register')
def serve_register():
    return send_from_directory(STATIC_SITE_DIR, 'login.html')


@static_app.route('/logout')
def serve_logout():
    import json
    from flask import make_response, session
    from db import common_db

    ref = request.args.get('redirect') or request.args.get('next') or '/'

    # 1. Purge active API tokens if user or admin in session
    user_id = session.get('user_id')
    if not user_id and session.get('admin_username'):
        admin_username = session.get('admin_username').upper()
        admin_email = f"{admin_username.lower()}@system.local"
        try:
            conn = common_db.get_db()
            row = conn.execute('SELECT id FROM users WHERE email = ?', (admin_email,)).fetchone()
            conn.close()
            if row:
                user_id = row['id']
        except Exception:
            pass

    if user_id:
        try:
            conn = common_db.get_db()
            conn.execute('DELETE FROM user_tokens WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error purging tokens in serve_logout: {e}")

    # 2. Clear Flask session
    session.clear()

    # 3. Build response with HTTP Set-Cookie expiration and JS storage cleanup
    html = f"""<!DOCTYPE html>
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
            window.location.href = {json.dumps(ref)};
        }})();
    </script>
</head>
<body>
    <p style="font-family: sans-serif; text-align: center; margin-top: 50px; color: #666;">Logging out...</p>
</body>
</html>"""

    resp = make_response(html)
    resp.set_cookie('session', '', expires=0, max_age=0, path='/', httponly=True, samesite='Lax')
    return resp



# =============================================================================
# VOLUNTEER SUBMISSION API & EMAIL NOTIFICATIONS
# =============================================================================

def send_volunteer_email_async(data):
    """Send volunteer contact request via SMTP to admin (pure contact details, no IP or device metadata)."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_server = getattr(config, 'SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(getattr(config, 'SMTP_PORT', 587))
    smtp_user = getattr(config, 'SMTP_USER', None)
    smtp_pass = getattr(config, 'SMTP_PASSWORD', None)
    admin_email = getattr(config, 'ADMIN_EMAIL', None) or os.environ.get('ADMIN_EMAIL', '') or (smtp_user or '')

    if not smtp_user or not smtp_pass:
        print("[Volunteer] SMTP credentials not configured. Skipping email dispatch.")
        return

    try:
        name = data.get('name', 'Anonymous')
        phone = data.get('phone', 'N/A')

        msg = MIMEMultipart('alternative')
        msg['From'] = f"Samshodhana Mandiram <{smtp_user}>"
        msg['To'] = admin_email
        msg['Subject'] = f"[Volunteer HR Call Request] {name} - {phone} (Time & Skills)"

        plain_text = f"""New Volunteer HR Request (Time & Skills — No Money Donation)

Volunteer Details:
------------------
Name: {name}
Phone / WhatsApp: {phone}
Type: Human Resources (Creative thinking, social media handling, tech/AI, etc. — No money donation)
Action: Call and speak with volunteer soon.

--
Samshodhana Mandiram Volunteer Registry
"""

        clean_digits = ''.join(c for c in phone if c.isdigit())
        whatsapp_link = f"https://wa.me/{clean_digits}" if clean_digits else ""

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f6f8fb; margin: 0; padding: 24px; color: #2d3748;">
  <div style="max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;">
    <div style="background: linear-gradient(135deg, #d4af37 0%, #e65100 50%, #9a3412 100%); padding: 24px 28px; color: #ffffff;">
      <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.9; font-weight: 700;">संशोधन मन्दिरम् &bull; Human Resources / Seva</div>
      <h2 style="margin: 6px 0 0 0; font-size: 22px; font-weight: 700; color: #ffffff;">New Volunteer (Time & Skills)</h2>
      <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">Creative thinking, social media handling, and skills contribution (Not a money donation).</p>
    </div>
    
    <div style="padding: 24px 28px;">
      <table style="width: 100%; border-collapse: collapse; font-size: 15px;">
        <tr style="border-bottom: 1px solid #edf2f7;">
          <td style="padding: 12px 0; font-weight: 600; color: #718096; width: 140px;">Full Name</td>
          <td style="padding: 12px 0; color: #1a202c; font-weight: 700; font-size: 16px;">{name}</td>
        </tr>
        <tr style="border-bottom: 1px solid #edf2f7;">
          <td style="padding: 12px 0; font-weight: 600; color: #718096;">Phone / Mobile</td>
          <td style="padding: 12px 0; color: #1a202c; font-weight: 700; font-size: 16px;">
            <a href="tel:{phone}" style="color: #2b6cb0; text-decoration: none;">{phone}</a>
            {" &nbsp;<a href='" + whatsapp_link + "' style='background:#25d366; color:#ffffff; padding:3px 10px; border-radius:12px; font-size:12px; text-decoration:none; font-weight:600;'>WhatsApp Call/Chat</a>" if whatsapp_link else ""}
          </td>
        </tr>
        <tr>
          <td style="padding: 12px 0; font-weight: 600; color: #718096;">Action Required</td>
          <td style="padding: 12px 0; color: #e65100; font-weight: 600;">📞 Call and speak with volunteer</td>
        </tr>
      </table>
    </div>
    
    <div style="background: #edf2f7; padding: 14px 28px; font-size: 12px; color: #718096; text-align: center;">
      Samshodhana Mandiram &bull; Sri Trayee Vidya Gurukulam &bull; <a href="mailto:samshodhanamandiram@gmail.com" style="color: #718096;">samshodhanamandiram@gmail.com</a>
    </div>
  </div>
</body>
</html>
"""
        msg.attach(MIMEText(plain_text, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        print(f"[Volunteer] Application email dispatched successfully for {name} ({phone}) to {admin_email}")
    except Exception as e:
        print(f"[Volunteer] Error dispatching email: {e}")


@static_app.route('/api/volunteer/submit', methods=['POST'])
def submit_volunteer():
    """Handle volunteer application submissions: directly emails admin without database logging or device fingerprinting."""
    import threading

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    phone = (data.get('phone') or '').strip()

    if not name or not phone:
        return jsonify({
            'success': False,
            'error': 'Full Name and Phone Number are mandatory.'
        }), 400

    # Dispatch email asynchronously in background thread (no DB logging, no IP tracking)
    threading.Thread(target=send_volunteer_email_async, args=(data,), daemon=True).start()

    return jsonify({
        'success': True,
        'message': 'Thank you! We will call and speak with you soon.'
    })


SAFE_STATIC_EXTENSIONS = {
    '.html', '.htm', '.css', '.js', '.mjs', '.png', '.jpg', '.jpeg',
    '.gif', '.svg', '.ico', '.webp', '.woff', '.woff2', '.ttf', '.eot',
    '.json', '.csv', '.tsv', '.mp3', '.wav', '.ogg', '.pdf', '.txt',
    '.xml', '.map', '.webmanifest'
}

DANGEROUS_EXTENSIONS = {
    '.db', '.sqlite', '.sqlite3', '.py', '.pyc', '.pyo', '.env', '.log',
    '.key', '.pem', '.cert', '.crt', '.sh', '.bat', '.ps1', '.cmd', '.bak', '.tmp'
}

@static_app.route('/<path:filepath>')
def serve_static_file(filepath):
    """Serve specific public files (quiz, articles, katha, favicon, safe apps assets) from the root directory."""
    normalized_path = os.path.normpath(filepath).replace('\\', '/')
    allowed = False

    # Block directory traversal sequences
    if '..' in normalized_path or normalized_path.startswith('/'):
        return "Not Found", 404

    # Block direct access to index.html files — use the clean URL instead (e.g. /katha not /katha/index.html)
    if normalized_path.endswith('/index.html'):
        clean_url = '/' + normalized_path[:-len('index.html')]
        clean_url = clean_url.rstrip('/')
        if request.query_string:
            clean_url += '?' + request.query_string.decode('utf-8')
        return redirect(clean_url, 301)

    # Never serve hidden files (.env, .git) or backend internal directories
    path_segments = [seg.lower() for seg in normalized_path.split('/')]
    if any(seg.startswith('.') for seg in path_segments if seg):
        return "Not Found", 404
    if any(seg in ('backend', '__pycache__', 'venv', '.git') for seg in path_segments):
        return "Not Found", 404

    # Block dangerous file extensions
    _, ext = os.path.splitext(normalized_path)
    ext = ext.lower()
    if ext in DANGEROUS_EXTENSIONS:
        return "Not Found", 404

    if normalized_path in ('favicon.ico', 'CNAME'):
        allowed = True
    elif normalized_path.startswith(('quiz/', 'quiz', 'articles/', 'articles', 'katha/', 'katha', 'play/', 'play', 'static/', 'static')):
        allowed = True
    elif normalized_path.startswith(('apps/', 'apps')):
        # For apps/, only serve explicitly safe static assets (HTML/CSS/JS/images/media)
        # Never serve databases, python scripts, or configuration files
        if not ext or ext in SAFE_STATIC_EXTENSIONS:
            allowed = True

    if not allowed:
        return "Not Found", 404

    real_static_dir = os.path.realpath(STATIC_SITE_DIR)
    full_path = os.path.realpath(os.path.join(STATIC_SITE_DIR, filepath))

    # Strict containment check
    if not full_path.startswith(real_static_dir + os.sep) and full_path != real_static_dir:
        return "Not Found", 404

    if os.path.isdir(full_path):
        index_path = os.path.realpath(os.path.join(full_path, 'index.html'))
        if os.path.exists(index_path) and index_path.startswith(real_static_dir + os.sep):
            # Redirect to trailing-slash URL so relative assets (style.css, etc.)
            # resolve correctly against the directory, not the parent.
            if not filepath.endswith('/'):
                target = '/' + filepath + '/'
                if request.query_string:
                    target += '?' + request.query_string.decode('utf-8')
                return redirect(target, 301)
            return send_from_directory(full_path, 'index.html')

    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    if os.path.isfile(full_path):
        return send_from_directory(directory, filename)

    return "Not Found", 404


# =============================================================================
# SHARED ADMIN APP (Hub, Users, Manage Admins, Audit Logs)
# =============================================================================

admin_app = Flask(
    __name__,
    template_folder=os.path.join(base_dir, 'sdl_web', 'templates'),
    static_folder=os.path.join(base_dir, 'static'),
    static_url_path='/static',
)
admin_app.secret_key = config.SECRET_KEY
admin_app.config['TEMPLATES_AUTO_RELOAD'] = True
admin_app.config['SESSION_COOKIE_PATH'] = '/'

# Register the shared admin blueprint (routes like /hub, /users …)
admin_app.register_blueprint(shared_admin)


# =============================================================================
# COMBINED WSGI APPLICATION
# =============================================================================

class AdminPathRewriteMiddleware:
    """Transparent WSGI middleware to rewrite SDL-specific paths into /sdl/... mount.

    Routing logic:
      /admin/*  shared admin paths  → go directly to admin_app (no rewrite)
      /admin/*  SDL admin paths     → rewritten to /sdl/admin/* → sdl_app
      /api/*, /book/*, /user/*, … → rewritten to /sdl/* → sdl_app
      Everything else              → static_app or admin_app as mounted
    """

    # Shared admin paths served by admin_app — these must NOT be rewritten to /sdl
    SHARED_ADMIN_PREFIXES = (
        '/admin/hub',
        '/admin/logout',
        '/admin/users',
        '/admin/api/users',
        '/admin/api/user/',
        '/admin/manage-admins',
        '/admin/add-admin',
        '/admin/edit-admin/',
        '/admin/delete-admin/',
        '/admin/static',
        '/admin/chandas',
        '/admin/vyakarana',
        '/admin/sanskrit-stt',
        '/admin/transliterator-bot',
        '/admin/ocr-bot',
        '/admin/ocr_bot',
    )

    # All other SDL app paths that need /sdl prefix rewrite
    SDL_REWRITE_PREFIXES = (
        '/admin',    # SDL-specific admin routes (dashboard, books, upload, AI…)
        '/api',
        '/logout',
        '/book',
        '/download',
        '/details',
        '/search',
        '/library',
        '/transliterator',
        '/varga-panchama',
        '/ocr',
        '/browse',
        '/item',
        '/reader',
        '/user',
        '/contribute',
        '/upload-book',
        '/favicon',
    )

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')

        # Direct root /api/ocr_bot and /api/rigveda requests to /apps/api/... blueprint
        if path.startswith('/api/ocr_bot'):
            environ['PATH_INFO'] = '/apps' + path
            return self.app(environ, start_response)
        if path.startswith('/api/rigveda'):
            environ['PATH_INFO'] = '/apps' + path
            return self.app(environ, start_response)

        # If path is a shared admin route, let it pass through to admin_app unchanged
        is_shared = False
        for p in self.SHARED_ADMIN_PREFIXES:
            if path == p:
                is_shared = True
                break
            if p.endswith('/'):
                if path.startswith(p):
                    is_shared = True
                    break
            else:
                if path.startswith(p + '/') or path.startswith(p + '?'):
                    is_shared = True
                    break

        if is_shared:
            return self.app(environ, start_response)

        # Otherwise, rewrite SDL routes to /sdl/...
        if any(path.startswith(p) for p in self.SDL_REWRITE_PREFIXES):
            if not path.startswith('/api/volunteer'):
                environ['PATH_INFO'] = '/sdl' + path
                # Clear SCRIPT_NAME so Flask url_for() generates clean URLs without /sdl prefix
                environ['SCRIPT_NAME'] = ''

        return self.app(environ, start_response)


# DispatcherMiddleware routes by URL prefix:
#   /admin → admin_app (shared admin tools)
#   /sdl   → sdl_app   (SDL library)
#   /      → static_app (landing page, quiz, katha, articles)
application = DispatcherMiddleware(static_app, {
    '/admin': admin_app,
    '/sdl':   sdl_app,
})

from werkzeug.middleware.proxy_fix import ProxyFix

# Wrap with path rewriter so SDL routes work without /sdl prefix in the browser
application = AdminPathRewriteMiddleware(application)

# Fix client IP address when running behind a reverse proxy
application = ProxyFix(application, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# =============================================================================
# DEVELOPMENT SERVER
# =============================================================================

if __name__ == '__main__':
    from werkzeug.serving import run_simple
    port = int(os.environ.get('PORT', 5001))
    run_simple('127.0.0.1', port, application, use_reloader=True, use_debugger=True, threaded=True)
