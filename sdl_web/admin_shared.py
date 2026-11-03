"""
Shared Admin Blueprint — Platform-wide administrative tools
============================================================
Handles: Admin Hub, User Management, Admin Management, Audit Logs

This blueprint is mounted directly at /admin in server.py as a standalone Flask app,
separate from the SDL library app (/sdl). It manages platform-wide concerns shared
across all departments (SDL, Quiz, Katha, Articles).
"""

from flask import Blueprint, render_template, request, jsonify, redirect, session, flash, send_file, current_app
from functools import wraps
import math
import json
import os
import uuid
import threading
from werkzeug.utils import secure_filename

from db import common_db, quiz_db, katha_db, articles_db, play_db
import config

def log_change(*args, **kwargs):
    """No-op stub: System Audit Logging has been permanently removed."""
    pass

# ---------------------------------------------------------------------------
# Blueprint — no url_prefix since routes are already relative to /admin mount
# ---------------------------------------------------------------------------

shared_admin = Blueprint(
    'shared_admin',
    __name__,
    template_folder='templates',
    static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'static'),
    static_url_path='/static',
)


@shared_admin.context_processor
def inject_server_startup_id():
    """Inject server_startup_id globally into all templates rendered by the shared_admin blueprint."""
    try:
        from sdl import SERVER_STARTUP_ID
    except ImportError:
        import uuid
        SERVER_STARTUP_ID = str(uuid.uuid4())
    return dict(server_startup_id=SERVER_STARTUP_ID)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    """Require admin session. Redirects to /login for unauthenticated requests."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            if 'user_logged_in' in session:
                return redirect('/user/sdl-profile')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


# ---------------------------------------------------------------------------
# Helpers — imported lazily to avoid circular import at module load time
# ---------------------------------------------------------------------------

def _get_all_books():
    """Lazy import of get_all_books from the SDL module."""
    from sdl import get_all_books
    return get_all_books(bypass_cache=True, include_unpublished=True)


def _get_feedback_data():
    """Lazy import of get_feedback_data from the SDL module."""
    from sdl import get_feedback_data
    return get_feedback_data()


def _get_avatar_for_id(user_id, avatar_idx=None):
    """Lazy import of get_avatar_for_id from the SDL module."""
    from sdl import get_avatar_for_id
    return get_avatar_for_id(user_id, avatar_idx)


@shared_admin.route('/logout', methods=['GET', 'POST'])
def shared_admin_logout():
    """Shared admin logout handler"""
    from flask import make_response
    import json

    ref = request.args.get('redirect') or request.args.get('next') or '/'

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
            print(f"Error purging tokens in shared_admin_logout: {e}")

    session.clear()

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


# ===========================================================================
# ADMIN HUB
# ===========================================================================

@shared_admin.route('/hub')
@login_required
def admin_hub():
    """Unified Admin Hub — routes admins to department panels and shared tools."""
    try:
        book_count = len(_get_all_books())
    except Exception as e:
        print(f"Error getting book count: {e}")
        book_count = 0

    try:
        quiz_count = quiz_db.get_quiz_question_count()
    except Exception as e:
        print(f"Error getting quiz count: {e}")
        quiz_count = 0

    try:
        play_count = play_db.get_synonym_set_count() + play_db.get_word_builder_set_count() + play_db.get_word_search_set_count()
    except Exception as e:
        print(f"Error getting play count: {e}")
        play_count = 0

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

    try:
        user_count = len(common_db.get_all_users())
    except Exception as e:
        print(f"Error getting user count: {e}")
        user_count = 0

    try:
        admin_count = len(common_db.load_admins())
    except Exception as e:
        print(f"Error getting admin count: {e}")
        admin_count = 0

    return render_template(
        'admin/hub.html',
        book_count=book_count,
        quiz_count=quiz_count,
        play_count=play_count,
        katha_count=katha_count,
        article_count=article_count,
        user_count=user_count,
        admin_count=admin_count,
    )




# ===========================================================================
# PUBLIC USER MANAGEMENT
# ===========================================================================

@shared_admin.route('/users')
@login_required
def admin_users_panel():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_USERS' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_USERS'), 403
    return render_template('admin/users.html')


@shared_admin.route('/api/users', methods=['GET'])
@login_required
def admin_api_users():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_USERS' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    users = common_db.get_all_users()

    # Inject feedback counts per user
    feedback_data = _get_feedback_data()
    user_feedback_counts = {}
    for book_id, info in feedback_data.items():
        for c in info.get('comments', []):
            c_user_id = c.get('user_id')
            if c_user_id is not None:
                try:
                    uid = int(c_user_id)
                    user_feedback_counts[uid] = user_feedback_counts.get(uid, 0) + 1
                except (ValueError, TypeError):
                    pass

    for user in users:
        # AUD2-04: Mask mobile numbers for privacy
        if user.get('mobile'):
            m = str(user['mobile']).strip()
            if len(m) > 4:
                user['mobile'] = '*' * (len(m) - 4) + m[-4:]
        user['feedback_count'] = user_feedback_counts.get(user['id'], 0)
        user_avatar = _get_avatar_for_id(user['id'], user.get('avatar_idx', 0))
        user['avatar_emoji'] = user_avatar['emoji']
        user['avatar_gradient'] = user_avatar['gradient']

    return jsonify({'success': True, 'users': users})


@shared_admin.route('/api/user/<int:user_id>/details', methods=['GET'])
@login_required
def admin_get_user_details(user_id):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_USERS' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    user = common_db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # AUD2-04: Mask mobile numbers for privacy
    if user.get('mobile'):
        m = str(user['mobile']).strip()
        if len(m) > 4:
            user['mobile'] = '*' * (len(m) - 4) + m[-4:]

    user_avatar = _get_avatar_for_id(user_id, user.get('avatar_idx', 0))
    user['avatar_emoji'] = user_avatar['emoji']
    user['avatar_gradient'] = user_avatar['gradient']

    # AUD2-04: Zero Surveillance - User reading habits (favourites & booklists) are private
    favs = []
    hydrated_lists = []

    feedback_data = _get_feedback_data()
    user_feedbacks = []
    for book_id, info in feedback_data.items():
        for c in info.get('comments', []):
            c_user_id = c.get('user_id')
            if c_user_id is not None:
                try:
                    if int(c_user_id) == int(user_id):
                        c_copy = c.copy()
                        c_copy['book_id'] = book_id
                        user_feedbacks.append(c_copy)
                except (ValueError, TypeError):
                    pass

    return jsonify({
        'success': True,
        'user': user,
        'favourites': favs,
        'booklists': hydrated_lists,
        'feedbacks': user_feedbacks,
    })


@shared_admin.route('/api/user/<int:user_id>/reset_password', methods=['POST'])
@login_required
def admin_reset_user_password(user_id):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_USERS' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    user = common_db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    data = request.get_json() or {}
    new_password = data.get('password')
    if not new_password or len(new_password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters'}), 400

    success, msg = common_db.reset_user_password(user_id, new_password)
    if success:
        log_change(session.get('admin_username'), 'RESET_PASSWORD', 'USER', user['email'])
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 500


@shared_admin.route('/api/user/<int:user_id>', methods=['DELETE'])
@login_required
def admin_delete_user(user_id):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_USERS' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    user = common_db.get_user_by_id(user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    success = common_db.delete_user(user_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'USER', user['email'])
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    return jsonify({'success': False, 'message': 'Failed to delete user'}), 500


# ===========================================================================
# LOW-LEVEL ADMIN MANAGEMENT (Super-admin only)
# ===========================================================================

@shared_admin.route('/manage-admins')
@login_required
def manage_admins():
    """Display list of low-level admins."""
    if session.get('admin_role') != 'super':
        return render_template('admin/forbidden.html'), 403

    admins = common_db.load_admins()
    low_level_admins = {u: d for u, d in admins.items() if u.upper() != 'SUPERADMIN'}
    return render_template('admin/manage_admins.html', admins=low_level_admins, all_permissions=common_db.ALL_PERMISSIONS)


@shared_admin.route('/add-admin', methods=['POST'])
@login_required
def add_admin():
    """Create a new low-level admin."""
    if session.get('admin_role') != 'super':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')
    permissions = request.form.getlist('permissions')

    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password are required'}), 400
    if password != confirm_password:
        return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'error': 'Password must be at least 8 characters long'}), 400

    success, message = common_db.create_admin(username, password, permissions)
    return jsonify({'success': success, 'message': message})


@shared_admin.route('/edit-admin/<username>', methods=['GET', 'POST'])
@login_required
def edit_admin(username):
    """Edit an existing low-level admin."""
    if session.get('admin_role') != 'super':
        if request.method == 'POST':
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        return render_template('admin/forbidden.html'), 403

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        permissions = request.form.getlist('permissions')

        if password:
            if password != confirm_password:
                return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
            if len(password) < 8:
                return jsonify({'success': False, 'error': 'Password must be at least 8 characters long'}), 400

        success, message = common_db.update_admin(username, permissions, password if password else None)
        return jsonify({'success': success, 'message': message})

    # GET: return admin data for edit modal
    stored_username, admin_data = common_db.get_admin_by_username(username)
    if not stored_username:
        return "Admin not found", 404

    return jsonify({
        'username': stored_username,
        'permissions': admin_data.get('permissions', []),
        'created_at': admin_data.get('created_at'),
        'last_login': admin_data.get('last_login'),
    })


@shared_admin.route('/delete-admin/<username>', methods=['POST'])
@login_required
def delete_admin(username):
    """Delete a low-level admin."""
    if session.get('admin_role') != 'super':
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    if username == session.get('admin_username'):
        return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

    success, message = common_db.delete_admin(username)
    return jsonify({'success': success, 'message': message})








# ===========================================================================
# CHANDAS ADMIN
# ===========================================================================

@shared_admin.route('/chandas')
@login_required
def admin_chandas():
    """Admin panel for Chandas — Sanskrit Meter Analyzer configuration."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_AI'), 403

    return render_template('admin/chandas_admin.html')


# ===========================================================================
# SANSKRIT SPEECH TO TEXT ADMIN
# ===========================================================================

@shared_admin.route('/sanskrit-stt')
@login_required
def admin_sanskrit_stt():
    """Admin controller for Sanskrit Speech to Text — AI4Bharat Indic-Conformer STT & Telegram Bot."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_AI'), 403

    return render_template('admin/sanskrit_stt_admin.html')


def _get_stt_bot_db():
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    bot_backend_path = os.path.join(project_root, 'apps', 'sanskrit_stt', 'backend')
    if bot_backend_path not in sys.path:
        sys.path.insert(0, bot_backend_path)
    import bot_db
    return bot_db


def _get_stt_bot_manager():
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    bot_backend_path = os.path.join(project_root, 'apps', 'sanskrit_stt', 'backend')
    if bot_backend_path not in sys.path:
        sys.path.insert(0, bot_backend_path)
    import bot_manager
    return bot_manager


@shared_admin.route('/api/admin/stt/overview', methods=['GET'])
@login_required
def admin_stt_overview():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        bot_mgr = _get_stt_bot_manager()
        
        token = os.getenv("TELEGRAM_BOT_TOKEN") or bot_db.get_setting("telegram_bot_token", "")
        secret = os.getenv("ADMIN_SETUP_SECRET") or bot_db.get_setting("admin_setup_secret", "admin123")
        system_prompt = common_db.get_system_setting('stt_system_prompt', '')

        default_assist_prompt = """You are a highly specialized Multimodal Speech-to-Text (STT) Proofreading Assistant for Sanskrit and Indic languages.
You are provided with BOTH an actual recorded Sanskrit audio clip AND a raw Speech-to-Text (STT) text reference.

STRICT INSTRUCTIONS:
1. Listen carefully to the attached Sanskrit audio clip and cross-verify with the provided STT text reference to resolve mishearings, acoustic ambiguities, and phonetic typos.
2. Correct grammatical case endings (vibhakti), verbal tenses/moods (lakāra), gender/number agreements (liṅga/vacana), missing or incorrect visargas (ः), anusvāras (ं), and avagrahas (ऽ) so the text makes syntactic and semantic sense.
3. Apply standard Sanskrit Sandhi rules for smooth reading, while keeping word boundaries clear and readable (avoiding compound overload).
4. Do NOT alter named entities (proper nouns) unless they are clear phonetic mishearings.
5. Preserve standard Sanskrit punctuation (dandas । and ॥) and format verses/ślokas with appropriate line breaks.
6. Cleanly remove stutters, hesitations, and filler sounds (e.g. 'umm', 'aah'). Preserve legitimate non-Sanskrit words if intentionally spoken in mixed speech/lectures.
7. Output ONLY the phonetically verified, grammatically sound text in Devanāgarī script without commentary or markdown codeblocks."""

        default_clean_prompt = """You are a highly specialized Speech-to-Text (STT) Proofreading Assistant for Sanskrit and Indic languages.
The input text was generated by a Speech-to-Text (STT) voice recognition model and contains acoustic mishearings, phonetic typos, missing or incorrect visargas (ः), anusvāras (ं), sandhi boundaries, or grammatical slips.

STRICT INSTRUCTIONS:
1. Proofread and replace words ONLY with phonetically and grammatically correct versions.
2. Correct grammatical case endings (vibhakti), lakāras, missing visargas (ः), anusvāras (ं), and avagrahas (ऽ) so the text is syntactically sound.
3. Apply standard Sanskrit Sandhi rules for smooth reading, keeping words readable and clear.
4. Do NOT change words into non-phonetically similar synonyms or alter named entities unless they are misspellings/mishearings.
5. Preserve standard Sanskrit punctuation (dandas । and ॥) and format verses/ślokas with clean line breaks.
6. Cleanly remove stutters, hesitations, and filler sounds (e.g. 'umm', 'aah'). Preserve legitimate non-Sanskrit words if part of lecture text.
7. Output ONLY the cleaned, corrected text in Devanāgarī script without markdown code blocks, explanations, or commentary."""

        stt_ai_assist_prompt = bot_db.get_setting('stt_ai_assist_prompt', default_assist_prompt)
        stt_ai_assist_model = bot_db.get_setting('stt_ai_assist_model', 'gemini-3.6-flash')
        stt_ai_clean_prompt = bot_db.get_setting('stt_ai_clean_prompt', default_clean_prompt)
        stt_ai_clean_model = bot_db.get_setting('stt_ai_clean_model', 'models/gemini-3.5-flash')
        
        bot_status = bot_mgr.get_full_bot_status()

        codes = bot_db.list_access_codes()
        users = bot_db.list_users()
        unified = bot_db.list_unified_users_and_codes()
        logs = bot_db.get_recent_logs(50)

        active_codes = len([c for c in codes if c.get('status') == 'active'])
        total_audio_sec = sum(u.get('total_used_seconds', 0) for u in users)

        return jsonify({
            "success": True,
            "bot_token_set": bool(token),
            "bot_token": token,
            "bot_status": bot_status,
            "system_prompt": system_prompt,
            "stt_ai_assist_prompt": stt_ai_assist_prompt,
            "stt_ai_assist_model": stt_ai_assist_model,
            "stt_ai_clean_prompt": stt_ai_clean_prompt,
            "stt_ai_clean_model": stt_ai_clean_model,
            "setup_secret": secret,
            "total_codes": len(codes),
            "active_access_codes": active_codes,
            "total_users": len(users),
            "total_audio_seconds": total_audio_sec,
            "access_codes": codes,
            "users": users,
            "unified_users": unified,
            "recent_logs": logs,
            "total_logs_count": bot_db.get_total_logs_count()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/logs')
@login_required
def admin_stt_paginated_logs():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        import math
        bot_db = _get_stt_bot_db()
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        if page < 1: page = 1
        if per_page < 1: per_page = 50

        offset = (page - 1) * per_page
        logs = bot_db.get_recent_logs(limit=per_page, offset=offset)
        total_count = bot_db.get_total_logs_count()
        total_pages = math.ceil(total_count / per_page) if per_page > 0 else 1

        return jsonify({
            "success": True,
            "logs": logs,
            "total_count": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/bot_action', methods=['POST'])
@login_required
def admin_stt_bot_action():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_mgr = _get_stt_bot_manager()
        data = request.get_json() or {}
        action = data.get('action', '').strip().lower()

        if action == 'start':
            success, msg = bot_mgr.start_bot()
        elif action == 'stop':
            success, msg = bot_mgr.stop_bot()
        elif action == 'restart':
            success, msg = bot_mgr.restart_bot()
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400

        log_change(session.get('admin_username'), 'ACTION', 'STT_BOT', f'Executed Telegram Bot action: {action} ({msg})')
        status = bot_mgr.get_full_bot_status()
        return jsonify({"success": success, "message": msg, "bot_status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/bot_logs', methods=['GET'])
@login_required
def admin_stt_bot_logs():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_mgr = _get_stt_bot_manager()
        lines = int(request.args.get('lines', 50))
        logs_text = bot_mgr.get_bot_logs(lines)
        return jsonify({"success": True, "logs": logs_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/audio/<path:filename>', methods=['GET'])
@login_required
def admin_stt_get_audio(filename):
    """Audio retention and playback disabled for user privacy."""
    return jsonify({"success": False, "error": "Audio log retrieval has been permanently disabled for user privacy."}), 410


# ===========================================================================
# TRANSLITERATOR TELEGRAM BOT ADMIN
# ===========================================================================

def _get_transliterator_bot_db():
    import sys, importlib.util
    project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    file_path = os.path.join(project_root, 'apps', 'transliterator', 'backend', 'bot_db.py')
    spec = importlib.util.spec_from_file_location("transliterator_bot_db_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _get_transliterator_bot_manager():
    import sys, importlib.util
    project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    file_path = os.path.join(project_root, 'apps', 'transliterator', 'backend', 'bot_manager.py')
    spec = importlib.util.spec_from_file_location("transliterator_bot_manager_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@shared_admin.route('/transliterator-bot')
@login_required
def admin_transliterator_bot():
    """Admin controller for Transliterator Telegram Bot."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_AI'), 403

    return render_template('admin/transliterator_admin.html')


@shared_admin.route('/ocr-bot')
@shared_admin.route('/ocr_bot')
@login_required
def admin_ocr_bot():
    """Admin controller for Telegram OCR Bot — High-Accuracy OCR & Transliteration."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_AI'), 403

    return render_template('admin/ocr_bot_admin.html')




@shared_admin.route('/api/admin/transliterator/overview', methods=['GET'])
@login_required
def admin_transliterator_overview():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_mgr = _get_transliterator_bot_manager()
        status_info = bot_mgr.get_bot_status_info()
        return jsonify({"success": True, "data": status_info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/transliterator/settings', methods=['POST'])
@login_required
def admin_transliterator_save_settings():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        data = request.get_json() or {}
        token = data.get('bot_token', '').strip()
        if not token:
            return jsonify({"success": False, "error": "Please provide a valid Telegram Bot Token"}), 400

        bot_db = _get_transliterator_bot_db()
        bot_mgr = _get_transliterator_bot_manager()

        valid, bot_info = bot_mgr.check_telegram_token_valid(token)
        if not valid or not bot_info:
            return jsonify({"success": False, "error": "Invalid Telegram Bot Token. Telegram API verification failed."}), 400

        detected_username = bot_info.get('username', '')
        bot_db.set_setting('transliterator_bot_token', token)
        if detected_username:
            bot_db.set_setting('transliterator_bot_username', detected_username)

        log_change(session.get('admin_username'), 'UPDATE', 'TRANSLITERATOR_BOT', f'Saved Transliterator Bot Token (Detected Username: @{detected_username})')
        return jsonify({
            "success": True,
            "message": f"Settings saved! Verified bot: @{detected_username}",
            "bot_username": detected_username
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/transliterator/service/<action>', methods=['POST'])
@login_required
def admin_transliterator_service_control(action):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_mgr = _get_transliterator_bot_manager()
        if action == 'start':
            success, msg = bot_mgr.start_bot()
        elif action == 'stop':
            success, msg = bot_mgr.stop_bot()
        elif action == 'restart':
            success, msg = bot_mgr.restart_bot()
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400

        log_change(session.get('admin_username'), 'ACTION', 'TRANSLITERATOR_BOT', f'Executed Transliterator Bot action: {action} ({msg})')
        status = bot_mgr.get_bot_status_info()
        return jsonify({"success": success, "message": msg, "bot_status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/transliterator/bot_logs', methods=['GET'])
@login_required
def admin_transliterator_bot_logs():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_mgr = _get_transliterator_bot_manager()
        lines = int(request.args.get('lines', 50))
        logs_text = bot_mgr.get_bot_logs(lines)
        return jsonify({"success": True, "logs": logs_text})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/config', methods=['POST'])
@login_required
def admin_stt_save_config():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        token = data.get('telegram_bot_token', '').strip()
        prompt = data.get('system_prompt', '').strip()
        stt_ai_assist_prompt = data.get('stt_ai_assist_prompt')
        stt_ai_assist_model = data.get('stt_ai_assist_model')
        stt_ai_clean_prompt = data.get('stt_ai_clean_prompt')
        stt_ai_clean_model = data.get('stt_ai_clean_model')

        if token:
            bot_db.set_setting('telegram_bot_token', token)
            os.environ['TELEGRAM_BOT_TOKEN'] = token
        if prompt:
            common_db.set_system_setting('stt_system_prompt', prompt)
        if stt_ai_assist_prompt is not None:
            bot_db.set_setting('stt_ai_assist_prompt', stt_ai_assist_prompt.strip())
        if stt_ai_assist_model is not None:
            bot_db.set_setting('stt_ai_assist_model', stt_ai_assist_model.strip())
        if stt_ai_clean_prompt is not None:
            bot_db.set_setting('stt_ai_clean_prompt', stt_ai_clean_prompt.strip())
        if stt_ai_clean_model is not None:
            bot_db.set_setting('stt_ai_clean_model', stt_ai_clean_model.strip())

        log_change(session.get('admin_username'), 'UPDATE', 'STT_SETTINGS', 'Updated Sanskrit STT Bot & AI configuration')
        return jsonify({"success": True, "message": "Configuration saved successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/create_code', methods=['POST'])
@login_required
def admin_stt_create_code():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        daily_max_seconds = float(data.get('daily_max_seconds', 6000))

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        max_minutes = daily_max_seconds / 60.0
        new_code = bot_db.create_access_code(code, daily_max_minutes=max_minutes)
        log_change(session.get('admin_username'), 'CREATE', 'STT_ACCESS_CODE', f'Created STT access code: {code}')
        return jsonify({"success": True, "code": new_code, "message": f"Access code '{code}' created successfully!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/update_limit', methods=['POST'])
@login_required
def admin_stt_update_limit():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        daily_max_minutes = float(data.get('daily_max_minutes', 100))

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        updated_code = bot_db.update_access_code_limit(code, daily_max_minutes)
        log_change(session.get('admin_username'), 'UPDATE', 'STT_ACCESS_CODE', f'Updated STT access code limit: {code} -> {daily_max_minutes} mins')
        return jsonify({"success": True, "code": updated_code, "message": f"Daily limit for '{code}' updated to {daily_max_minutes} mins."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/update_permissions', methods=['POST'])
@login_required
def admin_stt_update_permissions():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        allow_ai_clean = data.get('allow_ai_clean')
        allow_ai_assist = data.get('allow_ai_assist')

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        updated_code = bot_db.update_access_code_permissions(code, allow_ai_clean=allow_ai_clean, allow_ai_assist=allow_ai_assist)
        log_change(session.get('admin_username'), 'UPDATE', 'STT_ACCESS_CODE_PERMISSIONS', f'Updated permissions for code {code}: clean={allow_ai_clean}, assist={allow_ai_assist}')
        return jsonify({"success": True, "code": updated_code, "message": f"Permissions for '{code}' updated successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/send_message', methods=['POST'])
@login_required
def admin_stt_send_message():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        import requests
        bot_db = _get_stt_bot_db()
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
            return jsonify({"success": False, "error": "No registered Telegram users found to receive the message."}), 404

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

        log_change(session.get('admin_username'), 'SEND', 'STT_TELEGRAM_MSG', f'Sent message to Telegram target {target} (Success: {success_count}, Failed: {fail_count})')
        return jsonify({
            "success": success_count > 0,
            "sent_count": success_count,
            "fail_count": fail_count,
            "errors": errors,
            "message": f"Message sent to {success_count} user(s)." + (f" ({fail_count} failed)" if fail_count > 0 else "")
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/toggle_code', methods=['POST'])
@login_required
def admin_stt_toggle_code():

    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        code = data.get('code', '').strip().upper()
        status = data.get('status', 'revoked').strip().lower()

        if not code:
            return jsonify({"success": False, "error": "Access code string is required."}), 400

        if status == 'revoked':
            bot_db.revoke_access_code(code)
        else:
            bot_db.create_access_code(code)
        log_change(session.get('admin_username'), 'UPDATE', 'STT_ACCESS_CODE', f'Updated STT access code status: {code} -> {status}')
        return jsonify({"success": True, "message": f"Access code '{code}' status updated to {status}."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/languages', methods=['GET'])
@login_required
def admin_stt_languages_get():
    """Return all languages, enabled list, and current default."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        return jsonify({
            "success": True,
            "default": bot_db.get_default_language(),
            "enabled": bot_db.get_enabled_languages(),
            "all_languages": bot_db.ALL_LANGUAGES
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@shared_admin.route('/api/admin/stt/languages', methods=['POST'])
@login_required
def admin_stt_languages_post():
    """Update enabled languages and default language."""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    try:
        bot_db = _get_stt_bot_db()
        data = request.get_json() or {}
        enabled_list = data.get('enabled', [])
        default_code = data.get('default', 'sa')

        if not isinstance(enabled_list, list) or len(enabled_list) == 0:
            return jsonify({"success": False, "error": "At least one language must be enabled."}), 400

        bot_db.set_enabled_languages(enabled_list)
        bot_db.set_default_language(default_code)

        log_change(session.get('admin_username'), 'UPDATE', 'STT_LANGUAGE_CONFIG',
                   f'Updated STT languages: enabled={enabled_list}, default={bot_db.get_default_language()}')

        return jsonify({
            "success": True,
            "default": bot_db.get_default_language(),
            "enabled": bot_db.get_enabled_languages(),
            "message": "Language controls updated successfully!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ===========================================================================
# VYAKARANA COMPANION ADMIN
# ===========================================================================

import sqlite3

def get_vyakarana_db():
    project_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    db_path = os.path.join(project_root, 'db', 'vyakarana_kosha.db')
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


@shared_admin.route('/vyakarana')
@login_required
def admin_vyakarana():
    """Admin panel for Vyakarana App (Ashtadhyayi Companion)"""
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return render_template('admin/forbidden.html', permission='PERM_MANAGE_AI'), 403
    return render_template('admin/vyakarana_admin.html')


@shared_admin.route('/vyakarana/api/sutras', methods=['GET'])
@login_required
def admin_vyakarana_get_sutras():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    query = request.args.get('query', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = (page - 1) * limit

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        
        ref_match = None
        import re
        if query:
            ref_match = re.match(r'^([1-8])[\.\s]([1-4])[\.\s](\d+)$', query)

        if ref_match:
            a, p, n = ref_match.groups()
            where_clause = "WHERE adhyaya = ? AND pada = ? AND number = ?"
            params = [int(a), int(p), int(n)]
        elif query:
            partial_ref_match = re.match(r'^([1-8])[\.\s]([1-4])$', query)
            if partial_ref_match:
                a, p = partial_ref_match.groups()
                where_clause = "WHERE adhyaya = ? AND pada = ?"
                params = [int(a), int(p)]
            else:
                from vidyut.lipi import Scheme, transliterate
                query_slp1 = query
                try:
                    query_slp1 = transliterate(query, Scheme.Devanagari, Scheme.Slp1)
                except Exception:
                    pass
                where_clause = "WHERE sutra LIKE ? OR sutra_slp1 LIKE ? OR padachheda LIKE ? OR sutrartha_english LIKE ?"
                params = [f"%{query}%", f"%{query_slp1}%", f"%{query}%", f"%{query}%"]
        else:
            where_clause = ""
            params = []

        count_query = f"SELECT COUNT(*) FROM sutraani {where_clause}"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]

        select_query = f"""
            SELECT idx, adhyaya, pada, number, sutra, sutra_slp1, sk_number, lsk_number, type, padachheda, sutrartha_english 
            FROM sutraani 
            {where_clause} 
            ORDER BY adhyaya ASC, pada ASC, number ASC 
            LIMIT ? OFFSET ?
        """
        cursor.execute(select_query, params + [limit, offset])
        rows = cursor.fetchall()
        
        results = [dict(row) for row in rows]
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'total_pages': math.ceil(total_records / limit)
            }
        })
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/sutra/<int:idx>', methods=['GET'])
@login_required
def admin_vyakarana_get_sutra(idx):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sutraani WHERE idx = ?", (idx,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'message': 'Sutra not found'}), 404

        return jsonify({'success': True, 'sutra': dict(row)})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/sutra/save', methods=['POST'])
@login_required
def admin_vyakarana_save_sutra():
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    data = request.get_json() or {}
    idx = data.get('idx')

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(sutraani)")
        columns = [row[1] for row in cursor.fetchall() if row[1] != 'idx']
        
        fields = []
        placeholders = []
        values = []
        update_pairs = []

        for col in columns:
            if col in data:
                fields.append(col)
                placeholders.append('?')
                values.append(data[col])
                update_pairs.append(f"{col} = ?")

        if idx and int(idx) > 0:
            sql = f"UPDATE sutraani SET {', '.join(update_pairs)} WHERE idx = ?"
            cursor.execute(sql, values + [int(idx)])
            conn.commit()
            log_change(session.get('admin_username'), 'UPDATE', 'VYAKARANA_SUTRA', f"Updated sutra idx={idx} ({data.get('sutra', '')})")
        else:
            cursor.execute("SELECT MAX(idx) FROM sutraani")
            max_idx = cursor.fetchone()[0] or 0
            new_idx = max_idx + 1

            sql = f"INSERT INTO sutraani (idx, {', '.join(fields)}) VALUES (?, {', '.join(placeholders)})"
            cursor.execute(sql, [new_idx] + values)
            conn.commit()
            idx = new_idx
            log_change(session.get('admin_username'), 'INSERT', 'VYAKARANA_SUTRA', f"Created new sutra idx={new_idx} ({data.get('sutra', '')})")

        conn.close()
        return jsonify({'success': True, 'idx': idx})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/sutra/delete/<int:idx>', methods=['POST'])
@login_required
def admin_vyakarana_delete_sutra(idx):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT sutra FROM sutraani WHERE idx = ?", (idx,))
        row = cursor.fetchone()
        sutra_text = row['sutra'] if row else f"idx={idx}"

        cursor.execute("DELETE FROM sutraani WHERE idx = ?", (idx,))
        conn.commit()
        conn.close()

        log_change(session.get('admin_username'), 'DELETE', 'VYAKARANA_SUTRA', f"Deleted sutra idx={idx} ({sutra_text})")
        return jsonify({'success': True})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


ALLOWED_VYAKARANA_TABLES = {
    'shivasutras', 'vartikas', 'ganapatha', 'unadipatha', 
    'linganushasanam', 'shiksha', 'phitsutrani', 
    'mahabhashyam', 'vakyapadeeyam', 'paribhashendushekhar', 
    'bhushanasara', 'paramalaghumanjoosha', 'tarkasangraha',
    'sutra_prayogas', 'kosha_words', 'kosha_entries'
}


@shared_admin.route('/vyakarana/api/table/<table_name>', methods=['GET'])
@login_required
def admin_vyakarana_get_table(table_name):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    if table_name not in ALLOWED_VYAKARANA_TABLES:
        return jsonify({'success': False, 'message': 'Forbidden table'}), 403

    query = request.args.get('query', '').strip()
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = (page - 1) * limit

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        columns = [c[1] for c in cols]
        pk_cols = [c[1] for c in cols if c[5] > 0]
        pk_col = pk_cols[0] if pk_cols else 'id'

        where_clause = ""
        params = []
        if query:
            search_conds = []
            for col in columns:
                search_conds.append(f"{col} LIKE ?")
                params.append(f"%{query}%")
            if search_conds:
                where_clause = f"WHERE {' OR '.join(search_conds)}"

        count_sql = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
        cursor.execute(count_sql, params)
        total_records = cursor.fetchone()[0]

        order_col = pk_col
        if 'num' in columns:
            order_col = "CAST(num AS INTEGER), num"
        elif 'id' in columns and table_name not in ['unadipatha', 'linganushasanam', 'shiksha', 'phitsutrani']:
            order_col = "CAST(id AS INTEGER), id"

        select_sql = f"""
            SELECT * FROM {table_name} 
            {where_clause} 
            ORDER BY {order_col} ASC 
            LIMIT ? OFFSET ?
        """
        cursor.execute(select_sql, params + [limit, offset])
        rows = cursor.fetchall()
        
        results = [dict(row) for row in rows]
        conn.close()

        return jsonify({
            'success': True,
            'results': results,
            'columns': columns,
            'primary_key': pk_col,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'total_pages': math.ceil(total_records / limit)
            }
        })
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/table/<table_name>/<row_id>', methods=['GET'])
@login_required
def admin_vyakarana_get_row(table_name, row_id):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    if table_name not in ALLOWED_VYAKARANA_TABLES:
        return jsonify({'success': False, 'message': 'Forbidden table'}), 403

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        pk_cols = [c[1] for c in cols if c[5] > 0]
        pk_col = pk_cols[0] if pk_cols else 'id'

        cursor.execute(f"SELECT * FROM {table_name} WHERE {pk_col} = ?", (row_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'success': False, 'message': 'Record not found'}), 404

        return jsonify({'success': True, 'data': dict(row)})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/table/<table_name>/save', methods=['POST'])
@login_required
def admin_vyakarana_save_row(table_name):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    if table_name not in ALLOWED_VYAKARANA_TABLES:
        return jsonify({'success': False, 'message': 'Forbidden table'}), 403

    data = request.get_json() or {}

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        columns = [c[1] for c in cols]
        pk_cols = [c[1] for c in cols if c[5] > 0]
        pk_col = pk_cols[0] if pk_cols else 'id'
        
        pk_val = data.get(pk_col)
        
        record_exists = False
        if pk_val is not None:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {pk_col} = ?", (pk_val,))
            record_exists = cursor.fetchone()[0] > 0

        fields = []
        placeholders = []
        values = []
        update_pairs = []

        for col in columns:
            if col == pk_col and record_exists:
                continue
            if col in data:
                fields.append(col)
                placeholders.append('?')
                values.append(data[col])
                update_pairs.append(f"{col} = ?")

        if record_exists:
            sql = f"UPDATE {table_name} SET {', '.join(update_pairs)} WHERE {pk_col} = ?"
            cursor.execute(sql, values + [pk_val])
            conn.commit()
            log_change(session.get('admin_username'), 'UPDATE', f"VYAKARANA_{table_name.upper()}", f"Updated {table_name} row {pk_col}={pk_val}")
        else:
            if pk_col not in data or data[pk_col] is None or data[pk_col] == '':
                pass
            else:
                fields.append(pk_col)
                placeholders.append('?')
                values.append(data[pk_col])

            sql = f"INSERT INTO {table_name} ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cursor.execute(sql, values)
            conn.commit()
            
            if pk_val is None or pk_val == '':
                pk_val = cursor.lastrowid
                
            log_change(session.get('admin_username'), 'INSERT', f"VYAKARANA_{table_name.upper()}", f"Created new {table_name} row {pk_col}={pk_val}")

        conn.close()
        return jsonify({'success': True, 'id': pk_val})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


@shared_admin.route('/vyakarana/api/table/<table_name>/delete/<row_id>', methods=['POST'])
@login_required
def admin_vyakarana_delete_row(table_name, row_id):
    is_super = session.get('admin_role') == 'super'
    user_perms = session.get('admin_permissions', [])
    if not is_super and 'PERM_MANAGE_AI' not in user_perms:
        return jsonify({'success': False, 'message': 'Access denied'}), 403

    if table_name not in ALLOWED_VYAKARANA_TABLES:
        return jsonify({'success': False, 'message': 'Forbidden table'}), 403

    conn = get_vyakarana_db()
    if not conn:
        return jsonify({'success': False, 'message': 'Vyakarana database not found'}), 404

    try:
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = cursor.fetchall()
        pk_cols = [c[1] for c in cols if c[5] > 0]
        pk_col = pk_cols[0] if pk_cols else 'id'

        cursor.execute(f"DELETE FROM {table_name} WHERE {pk_col} = ?", (row_id,))
        conn.commit()
        conn.close()

        log_change(session.get('admin_username'), 'DELETE', f"VYAKARANA_{table_name.upper()}", f"Deleted {table_name} row {pk_col}={row_id}")
        return jsonify({'success': True})
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500
