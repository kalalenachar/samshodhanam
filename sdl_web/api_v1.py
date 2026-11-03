from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, flash
from functools import wraps
import api_manager
import os
import time
from db import common_db, quiz_db, katha_db, articles_db, play_db
def log_change(*args, **kwargs):
    pass
from time_utils import get_ist_now

# Create the Blueprint
api_bp = Blueprint('api_v1', __name__)

# =============================================================================
# AUTHENTICATION DECORATOR
# =============================================================================

def api_key_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow logged in Web session (Admin or User)
        if session.get('logged_in') or session.get('user_logged_in'):
            request.api_user = {
                'user_id': session.get('user', session.get('user_id', 'session_user')),
                'rate_limit': 1000
            }
            return f(*args, **kwargs)

        api_key = request.headers.get('X-API-Key')
        if not api_key:
            # Also support query param for easier testing
            api_key = request.args.get('api_key')
            
        key_data = api_manager.validate_key(api_key) if api_key else None
        if not key_data:
            return jsonify({
                "success": False,
                "error": "Invalid or missing API Key. Use X-API-Key header."
            }), 401
            
        # Attach key info to request for use in route
        request.api_user = key_data
        return f(*args, **kwargs)
    return decorated_function

# =============================================================================
# API ROUTES (v1)
# =============================================================================

@api_bp.route('/status', methods=['GET'])
def get_status():
    """Health check and API info."""
    return jsonify({
        "status": "online",
        "version": "1.0.0",
        "service": "Sanskrit Digital Library API"
    })

@api_bp.route('/auth/profile', methods=['GET'])
@api_bp.route('/auth/profile/', methods=['GET'])
def api_v1_auth_profile():
    """Retrieve logged-in user profile details via blueprint context"""
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

@api_bp.route('/docs')
def api_docs():
    """Render the API documentation page."""
    return render_template('api_docs.html')

@api_bp.route('/books', methods=['GET'])
@api_key_required
def list_books():
    """List all available books with metadata."""
    from sdl import get_all_books # Late import to avoid circular issues
    
    try:
        books = get_all_books()
        # Clean up path info for external consumption
        sanitized_books = []
        for b in books:
            sanitized_books.append({
                "id": b['name'],
                "name": b['name'],
                "tags": b.get('tags', ''),
                "archive_url": b.get('archive_url', ''),
                "has_ocr": b.get('has_txt', False)
            })
            
        return jsonify({
            "success": True,
            "count": len(sanitized_books),
            "books": sanitized_books
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/search', methods=['GET'])
@api_key_required
def search():
    """Advanced search across all books."""
    from sdl import search_in_folder, get_metadata_from_folder, highlight_text, get_subbook_for_page, get_full_level_path_py # Late import
    import sdl as main_app # To get config
    
    text_query = request.args.get('q', '').strip()
    tags_query = request.args.get('tags', '').strip() or request.args.get('q_tag', '').strip()
    logic = request.args.get('logic', 'or').lower()
    if logic not in ['and', 'or']: logic = 'or'
    
    search_mode = request.args.get('mode', 'contains').lower()
    if search_mode not in ['contains', 'exact', 'starts_with', 'ends_with']: search_mode = 'contains'
    
    # Sanskrit normalization toggle (Matches your web logic)
    sanskrit_normalize = request.args.get('normalize', 'true').lower() == 'true'
    
    try:
        max_per_book = int(request.args.get('limit', 0))
        max_per_book = max(0, min(max_per_book, 1000)) # Cap it for safety
    except (ValueError, TypeError):
        max_per_book = 0
    
    if not text_query and not tags_query:
        return jsonify({"success": False, "error": "Search query 'q' or 'tags' is required"}), 400

    if text_query and len(text_query) < 2:
        return jsonify({"success": False, "error": "Search query must be at least 2 characters"}), 400

    start_time = time.time()
    all_results = []
    upload_folder = main_app.app.config['UPLOAD_FOLDER']
    
    # Use existing feedback sorting logic
    from sdl import get_feedback_data, get_book_sort_key
    feedback_data = get_feedback_data()
    
    if os.path.exists(upload_folder):
        folders = [f for f in os.listdir(upload_folder) if os.path.isdir(os.path.join(upload_folder, f))]
        # Sort folders by feedback just like the website
        folders.sort(key=lambda f: get_book_sort_key(f, feedback_data))
        
        for folder_name in folders:
            folder_path = os.path.join(upload_folder, folder_name)
            metadata = get_metadata_from_folder(folder_path)
            
            # 1. Tag Filtering
            if tags_query:
                meta_tags_raw = metadata.get('tags', '')
                meta_tags_list = [t.strip().lower() for t in meta_tags_raw.split(',') if t.strip()]
                t_q = tags_query.strip().lower()
                if t_q not in meta_tags_raw.lower() and not any(t_q == t or t_q in t for t in meta_tags_list):
                    continue
            
            # 2. Text Search
            if text_query:
                # search_in_folder handles the complex Sanskrit logic
                matches = [m for m in search_in_folder(folder_path, [text_query], logic, 
                                                      sanskrit_normalize=sanskrit_normalize,
                                                      max_results=max_per_book, search_mode=search_mode)
                          if m is not None and isinstance(m, dict) and 'page' in m]
                
                if matches:
                    levels_map = metadata.get('levels', {})
                    subbooks_list = metadata.get('subbooks', [])
                    for match in matches:
                        sub_book = get_subbook_for_page(match['page'], subbooks_list)
                        res_item = {
                            "book": folder_name,
                            "folder_name": folder_name,
                            "title": metadata.get('title') or folder_name,
                            "tags": metadata.get('tags', ''),
                            "page": match['page'],
                            "sub_book": sub_book,
                            "text": match['text'],
                            "archive_url": metadata.get('source', '')
                        }
                        if match.get('level_code'):
                            res_item['level_code'] = match['level_code']
                            level_disp = get_full_level_path_py(match['level_code'], levels_map)
                            if level_disp:
                                res_item['level_display'] = level_disp
                        all_results.append(res_item)
            else:
                # Just book matching tags
                all_results.append({
                    "book": folder_name,
                    "folder_name": folder_name,
                    "title": metadata.get('title') or folder_name,
                    "tags": metadata.get('tags', ''),
                    "archive_url": metadata.get('source', '')
                })
                if max_per_book > 0 and len(all_results) >= max_per_book:
                    break

    return jsonify({
        "success": True,
        "query": {"q": text_query, "tags": tags_query},
        "count": len(all_results),
        "results": all_results,
        "time_sec": round(time.time() - start_time, 2)
    })

@api_bp.route('/book/<book_id>/page/<int:page_num>', methods=['GET'])
@api_key_required
def get_page_content(book_id, page_num):
    """Get the full OCR text for a specific page."""
    from sdl import get_cached_file_content # Late import
    import sdl as main_app
    import re
    
    book_path = os.path.join(main_app.app.config['UPLOAD_FOLDER'], book_id)
    if not os.path.exists(book_path):
        return jsonify({"success": False, "error": "Book not found"}), 404
        
    # Find all txt/sdl files (excluding metadata.txt)
    txt_files = [f for f in sorted(os.listdir(book_path)) 
                if (f.endswith('.txt') and f.lower() != 'metadata.txt') or f.endswith('.sdl')]
    
    if not txt_files:
        return jsonify({"success": False, "error": "No OCR text available for this book"}), 404
        
    # Concatenate all files to ensure we find the page regardless of which file it's in
    full_text = ""
    for txt_file in txt_files:
        try:
            full_text += get_cached_file_content(os.path.join(book_path, txt_file)) + "\n"
        except:
            continue
    
    # Extract page content using markers {[(page_num)]}
    pattern = rf'\{{\[\({page_num}\)\]\}}'
    next_pattern = r'\{{\[\(\d+\)\]\}}'
    
    start_match = re.search(pattern, full_text)
    if not start_match:
        return jsonify({"success": False, "error": f"Page {page_num} not found"}), 404
        
    content_start = start_match.end()
    # Find start of next page
    remaining_text = full_text[content_start:]
    end_match = re.search(next_pattern, remaining_text)
    
    if end_match:
        page_content = remaining_text[:end_match.start()].strip()
    else:
        page_content = remaining_text.strip()
        
    return jsonify({
        "success": True,
        "book": book_id,
        "page": page_num,
        "content": page_content
    })

@api_bp.route('/suggest', methods=['POST'])
@api_key_required
def submit_suggestion():
    """Allow API users to submit suggestions or corrections."""
    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({"success": False, "error": "Suggestion content is required"}), 400
        
    key_label = request.api_user.get('label', 'Unknown API User')
    content = data.get('content')
    
    if api_manager.save_suggestion(key_label, content):
        return jsonify({
            "success": True, 
            "message": "Suggestion received. Thank you!"
        })
    else:
        return jsonify({"success": False, "error": "Failed to save suggestion"}), 500

@api_bp.route('/feedback', methods=['POST'])
@api_key_required
def submit_feedback():
    """Submit thumbs up/down and comments for a book/page."""
    import sdl as main_app # Late import
    import json
    
    data = request.get_json()
    book_id = data.get('book_id')
    status = data.get('status') # 'up' or 'down'
    comment = data.get('comment', '').strip()
    page = data.get('page')
    
    if not book_id or status not in ['up', 'down']:
        return jsonify({"success": False, "error": "book_id and status (up/down) are required"}), 400
        
    feedback_file = main_app.FEEDBACK_FILE
    
    # Load existing feedback
    feedback_data = {}
    if os.path.exists(feedback_file):
        try:
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedback_data = json.load(f)
        except:
            pass
            
    if book_id not in feedback_data:
        feedback_data[book_id] = {'up': 0, 'down': 0, 'comments': []}
        
    # Update counts
    if status == 'up':
        feedback_data[book_id]['up'] += 1
    else:
        feedback_data[book_id]['down'] += 1
        
    # Add comment/log entry
    feedback_entry = {
        'text': f"[API: {request.api_user.get('label')}] {comment}" if comment else f"[API: {request.api_user.get('label')}]",
        'page': page,
        'status': status,
        'time': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    feedback_data[book_id]['comments'].append(feedback_entry)
    
    # 2. ALSO: Send it directly to the Superadmin's API Panel as a suggestion
    suggestion_content = f"FEEDBACK [{status.upper()}]\nBook: {book_id}\nPage: {page if page else 'N/A'}\nComment: {comment if comment else '(No comment)'}"
    api_manager.save_suggestion(request.api_user.get('label'), suggestion_content)
    
    try:
        with open(feedback_file, 'w', encoding='utf-8') as f:
            json.dump(feedback_data, f, indent=2)
        return jsonify({"success": True, "message": "Feedback recorded and sent to Superadmin"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =============================================================================
# ADMIN PANEL ROUTES (For managing keys)
# =============================================================================

@api_bp.route('/admin/api-panel')
def admin_panel():
    """Render the API key management panel."""
    # This assumes the user is logged in via the main app session
    if 'logged_in' not in session:
        return redirect(url_for('admin_login'))
    
    if session.get('admin_role') != 'super':
        return "Access Denied: Superadmin only", 403
        
    keys = api_manager.load_keys()
    suggestions = api_manager.load_suggestions()
    return render_template('admin/api_panel.html', keys=keys, suggestions=suggestions)

@api_bp.route('/admin/api/clear-suggestions', methods=['POST'])
def clear_suggestions():
    if 'logged_in' not in session or session.get('admin_role') != 'super':
        return jsonify({"error": "Unauthorized"}), 403
        
    if api_manager.clear_suggestions():
        flash('All suggestions cleared', 'success')
    else:
        flash('Failed to clear suggestions', 'error')
        
    return redirect(url_for('api_v1.admin_panel'))

@api_bp.route('/admin/api/generate', methods=['POST'])
def generate_key():
    if 'logged_in' not in session or session.get('admin_role') != 'super':
        return jsonify({"error": "Unauthorized"}), 403
        
    label = request.form.get('label', 'New API Key')
    new_key = api_manager.create_key(label)
    
    if new_key:
        flash(f'Successfully generated key: {new_key}', 'success')
        # Store in session temporarily to show it to the user once
        session['last_generated_key'] = new_key
    else:
        flash('Failed to generate key', 'error')
        
    return redirect(url_for('api_v1.admin_panel'))

@api_bp.route('/admin/api/delete/<key_hash>', methods=['POST'])
def delete_key(key_hash):
    if 'logged_in' not in session or session.get('admin_role') != 'super':
        return jsonify({"error": "Unauthorized"}), 403
        
    if api_manager.delete_key(key_hash):
        flash('Key deleted successfully', 'success')
    else:
        flash('Failed to delete key', 'error')
        
    return redirect(url_for('api_v1.admin_panel'))

@api_bp.route('/quiz/admin-login', methods=['POST'])
def quiz_admin_login():
    """Verify quiz admin credentials against admins.json.
    Accepts SUPERADMIN or any admin with PERM_MANAGE_QUIZ permission."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
        
    stored_username, admin_data = common_db.get_admin_by_username(username)
    
    if stored_username and admin_data and common_db.verify_password(password, admin_data['password_hash']):
        session['logged_in'] = True
        session['admin_username'] = stored_username
        # Super-admin always has access
        if stored_username.upper() == 'SUPERADMIN':
            session['admin_role'] = 'super'
            session['admin_permissions'] = common_db.ALL_PERMISSIONS
            return jsonify({"success": True, "role": "superadmin"})
        # Check for PERM_MANAGE_QUIZ or PERM_MANAGE_PLAY permission
        perms = admin_data.get('permissions', [])
        if common_db.PERM_MANAGE_QUIZ in perms or 'PERM_MANAGE_PLAY' in perms:
            session['admin_role'] = 'low-level'
            session['admin_permissions'] = perms
            return jsonify({"success": True, "role": "play_admin" if 'PERM_MANAGE_PLAY' in perms else "quiz_admin"})
            
    return jsonify({"success": False, "error": "Invalid admin credentials"}), 401


# =============================================================================
# QUIZ QUESTION MANAGEMENT API
# =============================================================================

def quiz_admin_required(f):
    """Decorator: require SUPERADMIN, PERM_MANAGE_QUIZ or PERM_MANAGE_PLAY for quiz admin endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if session.get('admin_role') == 'super':
            return f(*args, **kwargs)
        user_perms = session.get('admin_permissions', [])
        if common_db.PERM_MANAGE_QUIZ in user_perms or 'PERM_MANAGE_PLAY' in user_perms:
            return f(*args, **kwargs)
        return jsonify({"success": False, "error": "Quiz admin access required"}), 403
    return decorated_function


@api_bp.route('/quiz/questions', methods=['GET'])
def quiz_get_questions():
    """Get all quiz questions. Public endpoint (candidates + admin).
    Optional query params: ?subject=...&level=..."""
    subject = request.args.get('subject', '').strip() or None
    level = request.args.get('level', '').strip() or None
    questions = quiz_db.get_all_quiz_questions(subject=subject, level=level)
    return jsonify({"success": True, "questions": questions, "count": len(questions)})


@api_bp.route('/quiz/questions', methods=['POST'])
@quiz_admin_required
def quiz_add_question():
    """Add a single quiz question."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400

    subject = data.get('subject', '').strip()
    level = data.get('level', '').strip()
    question = data.get('question')
    options = data.get('options')
    answer_index = data.get('answerIndex')
    explanation = data.get('explanation')

    if not subject or not level:
        return jsonify({"success": False, "error": "Subject and Level are required"}), 400
    if not question or not options or answer_index is None or not explanation:
        return jsonify({"success": False, "error": "Missing question fields"}), 400

    try:
        new_id = quiz_db.add_quiz_question(subject, level, question, options, answer_index, explanation)
        if new_id:
            log_change(session.get('admin_username'), 'CREATE', 'QUIZ_QUESTION', new_id, after_data={'subject': subject, 'level': level, 'question': question})
            return jsonify({"success": True, "id": new_id, "message": "Question added"})
        return jsonify({"success": False, "error": "Failed to add question"}), 500
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400


@api_bp.route('/quiz/questions/<int:question_id>', methods=['PUT'])
@quiz_admin_required
def quiz_update_question(question_id):
    """Update a single quiz question."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400

    subject = data.get('subject', '').strip()
    level = data.get('level', '').strip()
    question = data.get('question')
    options = data.get('options')
    answer_index = data.get('answerIndex')
    explanation = data.get('explanation')

    if not subject or not level:
        return jsonify({"success": False, "error": "Subject and Level are required"}), 400
    if not question or not options or answer_index is None or not explanation:
        return jsonify({"success": False, "error": "Missing question fields"}), 400

    success = quiz_db.update_quiz_question(question_id, subject, level, question, options, answer_index, explanation)
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'QUIZ_QUESTION', question_id, after_data={'subject': subject, 'level': level, 'question': question})
        return jsonify({"success": True, "message": "Question updated"})
    return jsonify({"success": False, "error": "Failed to update question"}), 500


@api_bp.route('/quiz/questions/<int:question_id>', methods=['DELETE'])
@quiz_admin_required
def quiz_delete_question(question_id):
    """Delete a single quiz question."""
    success = quiz_db.delete_quiz_question(question_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'QUIZ_QUESTION', question_id)
        return jsonify({"success": True, "message": "Question deleted"})
    return jsonify({"success": False, "error": "Failed to delete question"}), 500


@api_bp.route('/quiz/questions/bulk-delete', methods=['POST'])
@quiz_admin_required
def quiz_bulk_delete():
    """Delete multiple quiz questions by ID list."""
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    count = quiz_db.delete_quiz_questions_bulk(ids)
    log_change(session.get('admin_username'), 'DELETE_BULK', 'QUIZ_QUESTION', f"{count} questions", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Deleted {count} question(s)"})


@api_bp.route('/quiz/questions/import', methods=['POST'])
@quiz_admin_required
def quiz_import_questions():
    """Bulk import quiz questions from a JSON array in request body."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400

    questions_list = data.get('questions', [])
    default_subject = data.get('defaultSubject', 'General')
    default_level = data.get('defaultLevel', 'Default')

    if not questions_list or not isinstance(questions_list, list):
        return jsonify({"success": False, "error": "questions must be a non-empty array"}), 400

    added, errors, skipped = quiz_db.import_quiz_questions(questions_list, default_subject, default_level)
    total = quiz_db.get_quiz_question_count()
    log_change(session.get('admin_username'), 'IMPORT', 'QUIZ_QUESTION', f"{added} questions", after_data={'added': added, 'errors': len(errors), 'skipped': len(skipped)})
    return jsonify({
        "success": True,
        "added": added,
        "total": total,
        "errors": errors,
        "skipped": skipped
    })


@api_bp.route('/quiz/questions/reset', methods=['POST'])
@quiz_admin_required
def quiz_reset_questions():
    """Clear all questions and re-import from the static questions.json file."""
    json_path = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'quiz', 'questions.json'))
    if not os.path.exists(json_path):
        return jsonify({"success": False, "error": "Default questions.json not found"}), 404

    count = quiz_db.reset_quiz_questions_from_json(json_path)
    log_change(session.get('admin_username'), 'RESET', 'QUIZ_QUESTION', 'all', after_data={'imported': count})
    return jsonify({"success": True, "imported": count, "message": f"Reset complete. Imported {count} questions."})


# =============================================================================
# QUIZ CATEGORIES / FOLDERS API
# =============================================================================

def generate_default_categories():
    # Return an empty list by default. All database quizzes will remain
    # uncategorized and be dynamically appended to the root level.
    return []



@api_bp.route('/quiz/categories', methods=['GET'])
def get_quiz_categories():
    """Get the quiz categories folder hierarchy.
    
    Always merges in any DB (subject, level) pairs that are not yet referenced
    anywhere in the saved tree, appending them as quiz nodes at the root so
    students can always access every quiz even if the admin hasn't categorised it.
    """
    import json
    import uuid

    def collect_referenced(nodes):
        """Recursively collect all (subject, level) tuples already in the tree."""
        refs = set()
        for n in nodes:
            if n.get('type') == 'quiz' and n.get('subject') and n.get('level'):
                refs.add((n['subject'], n['level']))
            if n.get('children'):
                refs |= collect_referenced(n['children'])
        return refs

    def get_db_pairs():
        """Return list of {subject, level, count} from the quiz DB."""
        try:
            conn = quiz_db.get_db()
            rows = conn.execute(
                "SELECT subject, level, COUNT(*) as cnt FROM quiz_questions "
                "GROUP BY subject, level ORDER BY subject, level"
            ).fetchall()
            conn.close()
            return [{'subject': r['subject'] or 'General',
                     'level':   r['level']   or 'Default',
                     'count':   r['cnt'] or 0} for r in rows]
        except Exception as e:
            app.logger.error(f"Error querying DB pairs: {e}")
            return []

    try:
        categories_json_path = os.path.realpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
            'quiz', 'categories.json'
        ))

        # ── 1. Load the saved tree (or auto-generate one) ──────────────────
        tree = None
        if os.path.exists(categories_json_path):
            try:
                with open(categories_json_path, 'r', encoding='utf-8') as f:
                    raw = f.read().strip()
                if raw:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        tree = parsed
                if tree is None:
                    app.logger.warning("categories.json empty or not a list; regenerating.")
                    os.remove(categories_json_path)
            except Exception as e:
                app.logger.error(f"Error reading categories.json: {e}")
                try:
                    os.remove(categories_json_path)
                except Exception:
                    pass

        if tree is None:
            tree = generate_default_categories()
            try:
                os.makedirs(os.path.dirname(categories_json_path), exist_ok=True)
                with open(categories_json_path, 'w', encoding='utf-8') as f:
                    json.dump(tree, f, ensure_ascii=False, indent=2)
            except Exception as e:
                app.logger.error(f"Error saving auto-generated categories.json: {e}")

        # ── 2. Find uncategorised DB pairs and append to root ──────────────
        referenced = collect_referenced(tree)
        db_pairs   = get_db_pairs()
        db_counts  = {(p['subject'], p['level']): p['count'] for p in db_pairs}

        def update_tree_counts(nodes):
            for n in nodes:
                if n.get('type') == 'quiz' and n.get('subject') and n.get('level'):
                    n['count'] = db_counts.get((n['subject'], n['level']), 0)
                if n.get('children'):
                    update_tree_counts(n['children'])

        update_tree_counts(tree)

        for pair in db_pairs:
            key = (pair['subject'], pair['level'])
            if key not in referenced:
                tree.append({
                    'id':      f"node_uncat_{uuid.uuid4().hex[:8]}",
                    'name':    f"{pair['subject']} – {pair['level']}",
                    'type':    'quiz',
                    'subject': pair['subject'],
                    'level':   pair['level'],
                    'count':   pair['count'],
                })

        return jsonify({"success": True, "categories": tree})

    except Exception as e:
        app.logger.error(f"Unhandled error in get_quiz_categories: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route('/quiz/categories', methods=['POST'])
@quiz_admin_required
def save_quiz_categories():
    """Save the updated quiz categories folder hierarchy."""
    import json
    data = request.get_json()
    if not data or 'categories' not in data:
        return jsonify({"success": False, "error": "Missing categories data"}), 400
        
    categories_json_path = os.path.realpath(os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'quiz', 'categories.json'))
    try:
        os.makedirs(os.path.dirname(categories_json_path), exist_ok=True)
        with open(categories_json_path, 'w', encoding='utf-8') as f:
            json.dump(data['categories'], f, ensure_ascii=False, indent=2)
        log_change(session.get('admin_username'), 'UPDATE', 'QUIZ_CATEGORIES', 'categories.json')
        return jsonify({"success": True, "message": "Categories hierarchy saved successfully"})
    except Exception as e:
        app.logger.error(f"Error saving categories.json: {e}")
        return jsonify({"success": False, "error": f"Failed to save categories: {str(e)}"}), 500


@api_bp.route('/quiz/db-subjects-levels', methods=['GET'])
def get_db_subjects_levels():
    """Get list of unique subjects and levels in the database to link in categories."""
    conn = quiz_db.get_db()
    try:
        rows = conn.execute("SELECT DISTINCT subject, level FROM quiz_questions ORDER BY subject, level").fetchall()
        result = [{"subject": r['subject'], "level": r['level']} for r in rows]
        return jsonify({"success": True, "pairs": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/quiz/folder-icon', methods=['POST'])
@quiz_admin_required
def upload_folder_icon():
    """Upload an image file to be used as a folder icon."""
    import uuid

    if 'icon' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
        
    file = request.files['icon']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected for uploading"}), 400
        
    # Validate extension
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({"success": False, "error": f"Invalid file extension. Allowed: {', '.join(allowed_extensions)}"}), 400
        
    base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    icons_dir = os.path.join(base_dir, 'quiz', 'folder-icons')
    try:
        os.makedirs(icons_dir, exist_ok=True)
        
        # Optimize image with PIL
        from PIL import Image
        
        file.seek(0)
        
        # Preserve animated GIFs by saving them directly
        if ext == 'gif':
            new_filename = f"{uuid.uuid4().hex}.gif"
            file_path = os.path.join(icons_dir, new_filename)
            file.save(file_path)
        else:
            try:
                img = Image.open(file)
            except Exception as img_err:
                return jsonify({"success": False, "error": f"Invalid image format: {str(img_err)}"}), 400
                
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            
            # Resize if too large
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            
            # Always save as WebP for optimal compression
            new_filename = f"{uuid.uuid4().hex}.webp"
            file_path = os.path.join(icons_dir, new_filename)
            img.save(file_path, format='WEBP', quality=85)
        log_change(session.get('admin_username'), 'UPLOAD', 'QUIZ_FOLDER_ICON', new_filename)
        return jsonify({"success": True, "url": f"/quiz/folder-icons/{new_filename}"})
    except Exception as e:
        app.logger.error(f"Error saving folder icon upload: {e}")
        return jsonify({"success": False, "error": f"Failed to save file: {str(e)}"}), 500


# =============================================================================
# KATHA (STORY) MANAGEMENT & PUBLIC API
# =============================================================================

def katha_admin_required(f):
    """Decorator: require SUPERADMIN or PERM_MANAGE_KATHA for katha admin endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if session.get('admin_role') == 'super':
            return f(*args, **kwargs)
        user_perms = session.get('admin_permissions', [])
        if common_db.PERM_MANAGE_KATHA in user_perms:
            return f(*args, **kwargs)
        return jsonify({"success": False, "error": "Katha admin access required"}), 403
    return decorated_function


@api_bp.route('/katha/admin-login', methods=['POST'])
def katha_admin_login():
    """Verify katha admin credentials against admins.json.
    Accepts SUPERADMIN or any admin with PERM_MANAGE_KATHA permission."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
        
    stored_username, admin_data = common_db.get_admin_by_username(username)
    
    if stored_username and admin_data and common_db.verify_password(password, admin_data['password_hash']):
        session['logged_in'] = True
        session['admin_username'] = stored_username
        # Super-admin always has access
        if stored_username.upper() == 'SUPERADMIN':
            session['admin_role'] = 'super'
            session['admin_permissions'] = common_db.ALL_PERMISSIONS
            return jsonify({"success": True, "role": "superadmin"})
        # Check for PERM_MANAGE_KATHA permission
        perms = admin_data.get('permissions', [])
        if common_db.PERM_MANAGE_KATHA in perms:
            session['admin_role'] = 'low-level'
            session['admin_permissions'] = perms
            return jsonify({"success": True, "role": "katha_admin"})
            
    return jsonify({"success": False, "error": "Invalid admin credentials"}), 401


@api_bp.route('/katha/stories', methods=['GET'])
def katha_get_stories():
    """Get all published stories. Public endpoint.
    Optional query params: ?category=...&sort=..."""
    category = request.args.get('category', '').strip() or None
    sort_by = request.args.get('sort', 'title').strip()
    stories = katha_db.get_published_kathas(category=category, sort_by=sort_by)
    return jsonify({"success": True, "stories": stories, "count": len(stories)})


@api_bp.route('/katha/stories/<int:katha_id>', methods=['GET'])
def katha_get_story(katha_id):
    """Get a single story. If draft, requires katha admin permissions."""
    story = katha_db.get_katha_by_id(katha_id)
    if not story:
        return jsonify({"success": False, "error": "Story not found"}), 404
        
    if story['status'] != 'published':
        # Check if admin is logged in
        is_admin = False
        if 'logged_in' in session:
            if session.get('admin_role') == 'super':
                is_admin = True
            else:
                if common_db.PERM_MANAGE_KATHA in session.get('admin_permissions', []):
                    is_admin = True
        if not is_admin:
            return jsonify({"success": False, "error": "Story not found"}), 404
            
    # Get voter's current vote and comments
    voter_feedback = katha_db.get_voter_feedback(katha_id, request.remote_addr)
    story_dict = dict(story)
    story_dict['current_vote'] = voter_feedback['vote']
    story_dict['current_comment'] = voter_feedback['comments']
    return jsonify({"success": True, "story": story_dict})


@api_bp.route('/katha/categories', methods=['GET'])
def katha_get_categories():
    """Get distinct categories from published stories."""
    categories = katha_db.get_categories()
    return jsonify({"success": True, "categories": categories})


@api_bp.route('/katha/stories/<int:katha_id>/feedback', methods=['POST'])
def katha_submit_feedback(katha_id):
    """Submit feedback (upvote/downvote and optional comment) for a story."""
    data = request.get_json()
    if not data or 'vote' not in data:
        return jsonify({"success": False, "error": "Vote parameter is required"}), 400
        
    vote = data.get('vote')
    if vote not in ('up', 'down'):
        return jsonify({"success": False, "error": "Invalid vote value. Must be 'up' or 'down'"}), 400
        
    comments = data.get('comments', '').strip() or None
    voter_ip = request.remote_addr
    res = katha_db.submit_feedback(katha_id, vote, voter_ip, comments=comments)
    return jsonify({
        "success": True,
        "vote": res.get('vote'),
        "upvotes": res.get('upvotes', 0),
        "downvotes": res.get('downvotes', 0)
    })


@api_bp.route('/katha/stories/<int:katha_id>/feedback-comments', methods=['GET'])
@katha_admin_required
def katha_get_feedback_comments(katha_id):
    """Get feedback comments for a story (admin only)."""
    comments = katha_db.get_katha_feedback_comments(katha_id)
    return jsonify({"success": True, "comments": comments})


@api_bp.route('/katha/admin/stories', methods=['GET'])
@katha_admin_required
def katha_admin_get_stories():
    """Get all stories (including drafts) and categories for admin dashboard."""
    stories = katha_db.get_all_kathas()
    categories = katha_db.get_all_categories()
    return jsonify({
        "success": True,
        "stories": stories,
        "categories": categories
    })


@api_bp.route('/katha/admin/stories', methods=['POST'])
@katha_admin_required
def katha_admin_create_story():
    """Create a new story."""
    import json
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    title = data.get('title', '').strip()
    category = data.get('category', '').strip() or 'सामान्य'
    author = data.get('author', '').strip()
    reading_time = int(data.get('reading_time', 5))
    cover_image_url = data.get('cover_image_url', '').strip()
    summary = ""
    content_html = data.get('content_html', '').strip()
    status = data.get('status', 'draft')
    published_at = data.get('published_at', '').strip() or None
    
    if not title or not content_html:
        return jsonify({"success": False, "error": "Title and content are required"}), 400
        
    if status == 'published' and not cover_image_url:
        return jsonify({"success": False, "error": "Cover image URL is required when publishing"}), 400
        
    new_id = katha_db.create_katha(
        title=title,
        summary=summary,
        content_html=content_html,
        category=category,
        cover_image_url=cover_image_url,
        media_json='[]',
        author=author,
        reading_time=reading_time,
        status=status,
        published_at=published_at
    )
    
    if new_id:
        log_change(session.get('admin_username'), 'CREATE', 'KATHA_STORY', new_id, after_data={'title': title, 'category': category, 'status': status})
        return jsonify({"success": True, "id": new_id, "message": "Story created successfully"})
    return jsonify({"success": False, "error": "Failed to create story"}), 500


@api_bp.route('/katha/admin/stories/<int:katha_id>', methods=['PUT'])
@katha_admin_required
def katha_admin_update_story(katha_id):
    """Update an existing story."""
    import json
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    title = data.get('title', '').strip()
    category = data.get('category', '').strip() or 'सामान्य'
    author = data.get('author', '').strip()
    reading_time = int(data.get('reading_time', 5))
    cover_image_url = data.get('cover_image_url', '').strip()
    summary = ""
    content_html = data.get('content_html', '').strip()
    published_at = data.get('published_at', '').strip() or None
    status = data.get('status')
    
    if not title or not content_html:
        return jsonify({"success": False, "error": "Title and content are required"}), 400
        
    check_status = status
    if not check_status:
        existing = katha_db.get_katha_by_id(katha_id)
        check_status = existing.get('status') if existing else 'draft'
        
    if check_status == 'published' and not cover_image_url:
        return jsonify({"success": False, "error": "Cover image URL is required when publishing"}), 400
        
    success = katha_db.update_katha(
        katha_id=katha_id,
        title=title,
        summary=summary,
        content_html=content_html,
        category=category,
        cover_image_url=cover_image_url,
        media_json='[]',
        author=author,
        reading_time=reading_time,
        published_at=published_at,
        status=status
    )
    
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'KATHA_STORY', katha_id, after_data={'title': title, 'category': category, 'status': status})
        return jsonify({"success": True, "message": "Story updated successfully"})
    return jsonify({"success": False, "error": "Failed to update story"}), 500


@api_bp.route('/katha/admin/stories/<int:katha_id>', methods=['DELETE'])
@katha_admin_required
def katha_admin_delete_story(katha_id):
    """Delete a story."""
    story = katha_db.get_katha_by_id(katha_id)
    success = katha_db.delete_katha(katha_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'KATHA_STORY', katha_id)
        if story:
            cover_url = story.get('cover_image_url', '')
            if cover_url and cover_url.startswith('/katha/uploads/'):
                filename = os.path.basename(cover_url)
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                upload_dir = os.path.join(base_dir, 'katha', 'uploads')
                cov_path = os.path.join(upload_dir, filename)
                if os.path.exists(cov_path):
                    try:
                        os.remove(cov_path)
                    except Exception as e:
                        print(f"Error deleting cover file: {e}")
                thumb_path = os.path.join(upload_dir, f"thumb_{filename}")
                if os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception as e:
                        print(f"Error deleting thumbnail: {e}")
        return jsonify({"success": True, "message": "Story deleted successfully"})
    return jsonify({"success": False, "error": "Failed to delete story"}), 500


@api_bp.route('/katha/admin/stories/bulk-delete', methods=['POST'])
@katha_admin_required
def katha_admin_bulk_delete_stories():
    """Delete multiple stories by ID list."""
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(base_dir, 'katha', 'uploads')

    count = 0
    for story_id in ids:
        story = katha_db.get_katha_by_id(story_id)
        if katha_db.delete_katha(story_id):
            count += 1
            if story:
                cover_url = story.get('cover_image_url', '')
                if cover_url and cover_url.startswith('/katha/uploads/'):
                    filename = os.path.basename(cover_url)
                    cov_path = os.path.join(upload_dir, filename)
                    if os.path.exists(cov_path):
                        try:
                            os.remove(cov_path)
                        except Exception as e:
                            print(f"Error deleting cover file: {e}")
                    thumb_path = os.path.join(upload_dir, f"thumb_{filename}")
                    if os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)
                        except Exception as e:
                            print(f"Error deleting thumbnail: {e}")

    log_change(session.get('admin_username'), 'DELETE_BULK', 'KATHA_STORY', f"{count} stories", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Successfully deleted {count} stories"})


@api_bp.route('/katha/admin/stories/<int:katha_id>/toggle-status', methods=['POST'])
@katha_admin_required
def katha_admin_toggle_status(katha_id):
    """Toggle story status between draft and published."""
    try:
        new_status = katha_db.toggle_status(katha_id)
        if new_status:
            log_change(session.get('admin_username'), 'UPDATE', 'KATHA_STORY', katha_id, after_data={'status': new_status})
            return jsonify({"success": True, "status": new_status, "message": f"Story status updated to {new_status}"})
        return jsonify({"success": False, "error": "Failed to toggle status"}), 500
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route('/katha/admin/stories/import', methods=['POST'])
@katha_admin_required
def katha_admin_import_stories():
    """Bulk import stories from a JSON array in request body."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400

    stories_list = data.get('stories', [])
    if not stories_list or not isinstance(stories_list, list):
        return jsonify({"success": False, "error": "stories must be a non-empty array"}), 400

    added, errors, skipped = katha_db.import_kathas(stories_list)
    log_change(session.get('admin_username'), 'IMPORT', 'KATHA_STORY', f"{added} stories", after_data={'added': added, 'errors': len(errors), 'skipped': len(skipped)})
    
    # Get total stories count from database to return in response
    conn = katha_db.get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM kathas").fetchone()[0]
    except Exception:
        total = 0
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "added": added,
        "total": total,
        "errors": errors,
        "skipped": skipped
    })


@api_bp.route('/katha/admin/stories/import-zip', methods=['POST'])
@katha_admin_required
def katha_admin_import_zip():
    """Bulk import stories from a uploaded ZIP archive containing text chapters and cover images."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    category = request.form.get('category', '').strip() or 'सामान्य'
    author = request.form.get('author', '').strip() or ''
    
    if not file.filename.lower().endswith('.zip'):
        return jsonify({"success": False, "error": "Only ZIP files are allowed"}), 400
        
    import zipfile
    import tempfile
    import shutil
    import re
    from PIL import Image
    from datetime import datetime
    
    # Create a secure temporary directory inside the workspace
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    temp_dir = tempfile.mkdtemp(dir=os.path.join(base_dir, 'katha'))
    
    added = 0
    errors = []
    skipped = []
    
    try:
        # Save ZIP temporarily to extract it
        zip_path = os.path.join(temp_dir, 'import.zip')
        file.save(zip_path)
        
        # Extract the ZIP archive safely
        real_temp_dir = os.path.realpath(temp_dir)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.infolist():
                target_path = os.path.realpath(os.path.join(real_temp_dir, member.filename))
                if not target_path.startswith(real_temp_dir + os.sep) and target_path != real_temp_dir:
                    raise Exception(f"Unsafe ZIP entry detected: {member.filename}")
                zip_ref.extract(member, temp_dir)
            
        # Find all files recursively in extracted folder
        all_extracted_files = []
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                abs_path = os.path.join(root, f)
                all_extracted_files.append((f, abs_path))
                
        # Find all .txt files
        txt_files = [x for x in all_extracted_files if x[0].lower().endswith('.txt')]
        
        # Sort them by their parsed leading number
        def get_leading_num(name):
            match = re.match(r'^(\d+)', name)
            return int(match.group(1)) if match else 999999
        txt_files.sort(key=lambda x: get_leading_num(x[0]))
        
        upload_dir = os.path.join(base_dir, 'katha', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        conn = katha_db.get_db()
        
        for fname, abs_path in txt_files:
            try:
                # 1. Parse number and title
                fname_no_ext = os.path.splitext(fname)[0]
                num_match = re.match(r'^(\d+)', fname_no_ext)
                if not num_match:
                    continue
                num_str = num_match.group(1)
                
                # Keep the full filename (with numbers) as the title
                title = fname_no_ext.strip()
                    
                # Prevent duplicate titles
                existing = conn.execute(
                    'SELECT id FROM kathas WHERE title = ?', (title,)
                ).fetchone()
                if existing:
                    skipped.append({"title": title, "reason": "Already exists"})
                    continue
                
                # 2. Read story content and format as HTML
                content_text = ""
                for encoding in ('utf-8', 'utf-8-sig', 'utf-16', 'latin-1'):
                    try:
                        with open(abs_path, 'r', encoding=encoding) as f:
                            content_text = f.read().strip()
                        break
                    except UnicodeDecodeError:
                        continue
                        
                if not content_text:
                    errors.append(f"File {fname}: Empty or unreadable text content.")
                    continue
                    
                # Convert double newlines to paragraph HTML tags
                paragraphs = [p.strip() for p in re.split(r'\n\s*\n', content_text) if p.strip()]
                content_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)
                
                # Estimate reading time (roughly 120 words per minute)
                word_count = len(content_text.split())
                reading_time = max(1, int(word_count / 120))
                
                # Summary not used
                summary = ""
                
                # 3. Find matching cover image
                cover_image_url = ""
                status = "draft"
                
                img_extensions = ('.png',)
                matching_images = []
                for f_name, f_abs in all_extracted_files:
                    f_name_lower = f_name.lower()
                    name_no_ext = os.path.splitext(f_name_lower)[0]
                    if name_no_ext == num_str and f_name_lower.endswith(img_extensions):
                        matching_images.append(f_abs)
                        
                if matching_images:
                    img_abs_path = matching_images[0]
                    import time
                    timestamp = int(time.time())
                    safe_ext = '.png'
                    
                    new_filename = f"cov_zip_{timestamp}_{num_str}{safe_ext}"
                    thumb_filename = f"thumb_cov_zip_{timestamp}_{num_str}{safe_ext}"
                    
                    dest_file_path = os.path.join(upload_dir, new_filename)
                    dest_thumb_path = os.path.join(upload_dir, thumb_filename)
                    
                    try:
                        file_size = os.path.getsize(img_abs_path)
                        
                        # Save optimized cover
                        if file_size > 2 * 1024 * 1024:
                            with Image.open(img_abs_path) as img:
                                orig_format = img.format
                                img_cover = img.copy()
                                img_cover.thumbnail((1200, 1200))
                                img_cover.save(dest_file_path, format=orig_format, quality=80)
                        else:
                            shutil.copy(img_abs_path, dest_file_path)
                            
                        # Save thumbnail
                        if file_size > 2 * 1024 * 1024:
                            with Image.open(img_abs_path) as img:
                                orig_format = img.format
                                img_thumb = img.copy()
                                img_thumb.thumbnail((400, 400))
                                img_thumb.save(dest_thumb_path, format=orig_format, quality=75)
                        else:
                            shutil.copy(img_abs_path, dest_thumb_path)
                            
                        cover_image_url = f"/katha/uploads/{new_filename}"
                        status = "published"
                    except Exception as img_err:
                        print(f"Error compressing image {img_abs_path}: {img_err}")
                        errors.append(f"Chapter {num_str}: Image failed to compress, imported as draft.")
                        
                # 4. Save to DB
                conn.execute(
                    '''INSERT INTO kathas (title, summary, content_html, category, cover_image_url,
                       media_json, author, reading_time, status, published_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (title, summary, content_html, category, cover_image_url,
                     '[]', author, reading_time, status, get_ist_now().isoformat() if status == 'published' else None)
                )
                conn.commit()
                added += 1
                
            except Exception as e:
                errors.append(f"File {fname}: {str(e)}")
                
        conn.close()
        
    except Exception as e:
        errors.append(f"ZIP parsing error: {str(e)}")
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            
    total = katha_db.get_katha_count()
    log_change(session.get('admin_username'), 'IMPORT_ZIP', 'KATHA_STORY', f"{added} stories from zip", after_data={'added': added, 'errors': len(errors), 'skipped': len(skipped)})
    
    return jsonify({
        "success": True,
        "added": added,
        "total": total,
        "errors": errors,
        "skipped": skipped
    })


@api_bp.route('/katha/admin/stories/export-zip', methods=['POST'])
@katha_admin_required
def katha_admin_export_zip():
    """Export selected stories as a ZIP archive of text files and cover images."""
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400
        
    import zipfile
    import io
    import re
    import time
    from flask import send_file
    
    zip_buffer = io.BytesIO()
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(base_dir, 'katha', 'uploads')
    
    conn = katha_db.get_db()
    try:
        placeholders = ', '.join('?' for _ in ids)
        rows = conn.execute(f"SELECT * FROM kathas WHERE id IN ({placeholders})", ids).fetchall()
        stories = [dict(r) for r in rows]
    except Exception as e:
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500
    finally:
        conn.close()
        
    if not stories:
        return jsonify({"success": False, "error": "No stories found"}), 404
        
    # Sort stories by their ID to preserve sequential ordering
    stories.sort(key=lambda s: s['id'])
    
    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for i, s in enumerate(stories, 1):
                num_str = f"{i:02d}"  # Formatting sequence number prefix e.g., 01, 02
                
                # Sanitize title for file system
                clean_title = re.sub(r'[\/\\:\*\?"<>\|]', '', s['title']).strip()
                
                # Detect existing number prefix (e.g. "01 Tapasvi")
                prefix_match = re.match(r'^(\d+)\s', clean_title)
                if prefix_match:
                    export_prefix = prefix_match.group(1)
                else:
                    # Check if it has a prefix without space (e.g. "01Tapasvi")
                    prefix_no_space_match = re.match(r'^(\d+)', clean_title)
                    if prefix_no_space_match:
                        export_prefix = prefix_no_space_match.group(1)
                        # Add space after prefix in clean_title
                        clean_title = f"{export_prefix} {clean_title[len(export_prefix):].strip()}"
                    else:
                        export_prefix = num_str
                        clean_title = f"{export_prefix} {clean_title}"
                
                # Sanitize category/folder name
                category_name = s['category'] or 'सामान्य'
                category_dir = re.sub(r'[\/\\:\*\?"<>\|]', '', category_name).strip() or 'सामान्य'
                
                txt_filename = f"{category_dir}/{clean_title}.txt"
                
                # Format HTML to double-newline paragraphs for clean text representation
                html = s['content_html'] or ''
                text_content = re.sub(r'</p>\s*<p>', '\n\n', html)
                text_content = re.sub(r'<[^>]+>', '', text_content).strip()
                
                # Write the text file inside its category folder
                zip_file.writestr(txt_filename, text_content)
                
                # Copy cover image file to zip inside its category folder if it is stored locally
                cover_url = s['cover_image_url'] or ''
                if cover_url.startswith('/katha/uploads/'):
                    img_filename = os.path.basename(cover_url)
                    img_path = os.path.join(upload_dir, img_filename)
                    if os.path.exists(img_path):
                        ext = os.path.splitext(img_filename)[1].lower()
                        if not ext:
                            ext = '.png'
                        zip_file.write(img_path, f"{category_dir}/{export_prefix}{ext}")
                        
        zip_buffer.seek(0)
        zip_size = zip_buffer.getbuffer().nbytes
        
        # Log the change
        log_change(session.get('admin_username'), 'EXPORT_ZIP', 'KATHA_STORY', f"{len(stories)} stories exported to zip")
        
        response = send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f"katha_export_{int(time.time())}.zip"
        )
        response.headers['Content-Length'] = zip_size
        return response
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to build ZIP: {str(e)}"}), 500


@api_bp.route('/katha/admin/upload-image', methods=['POST'])
@katha_admin_required
def katha_admin_upload_image():
    """Upload a cover image/media file. Saves to katha/uploads/ directory."""
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    if file:
        allowed_extensions = {'png'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({"success": False, "error": "Allowed format: PNG"}), 400
            
        import time
        from werkzeug.utils import secure_filename
        
        # Determine target path
        base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        upload_dir = os.path.join(base_dir, 'katha', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save file with secure timestamp prefix to prevent name collisions
        safe_filename = secure_filename(file.filename)
        filename = f"cov_{int(time.time())}_{safe_filename}"
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        
        # Optimize cover and generate thumbnail
        try:
            from PIL import Image
            import shutil
            
            file_size = os.path.getsize(file_path)
            
            # If cover is > 2 MB, resize and optimize it in place
            if file_size > 2 * 1024 * 1024:
                with Image.open(file_path) as img:
                    orig_format = img.format
                    img_cover = img.copy()
                    img_cover.thumbnail((1200, 1200))
                    img_cover.save(file_path, format=orig_format)
            
            # Save thumbnail
            thumb_filename = f"thumb_{filename}"
            thumb_file_path = os.path.join(upload_dir, thumb_filename)
            
            if file_size > 2 * 1024 * 1024:
                with Image.open(file_path) as img:
                    orig_format = img.format
                    img_thumb = img.copy()
                    img_thumb.thumbnail((400, 400))
                    img_thumb.save(thumb_file_path, format=orig_format)
            else:
                shutil.copy(file_path, thumb_file_path)
        except Exception as e:
            print(f"Error generating thumbnail for uploaded image: {e}")
            
        # Return the relative URL path to serve it
        url = f"/katha/uploads/{filename}"
        return jsonify({"success": True, "url": url})
        
    return jsonify({"success": False, "error": "Failed to save file"}), 500


@api_bp.route('/katha/admin/folders', methods=['GET'])
@katha_admin_required
def katha_admin_get_folders():
    """Get all folders/categories with draft and published counts."""
    conn = katha_db.get_db()
    try:
        rows = conn.execute('''
            SELECT category, 
                   COUNT(CASE WHEN status = 'draft' THEN 1 END) as drafts,
                   COUNT(CASE WHEN status = 'published' THEN 1 END) as published,
                   COUNT(*) as total
            FROM kathas
            GROUP BY category
            ORDER BY category ASC
        ''').fetchall()
        folders = [dict(r) for r in rows]
        return jsonify({"success": True, "folders": folders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/katha/admin/folders/rename', methods=['PUT'])
@katha_admin_required
def katha_admin_rename_folder():
    """Rename a category/folder, updating all stories in that category."""
    from datetime import datetime
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    
    if not old_name or not new_name:
        return jsonify({"success": False, "error": "Both old_name and new_name are required"}), 400
        
    conn = katha_db.get_db()
    try:
        cursor = conn.execute(
            'UPDATE kathas SET category = ?, updated_at = ? WHERE category = ?',
            (new_name, get_ist_now().isoformat(), old_name)
        )
        conn.commit()
        count = cursor.rowcount
        log_change(session.get('admin_username'), 'RENAME_FOLDER', 'KATHA_FOLDER', old_name, after_data={'new_name': new_name, 'affected_stories': count})
        return jsonify({"success": True, "message": f"Successfully renamed folder '{old_name}' to '{new_name}'. {count} story/stories updated."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/katha/admin/folders/delete', methods=['POST'])
@katha_admin_required
def katha_admin_delete_folder():
    """Delete a category/folder, either deleting all stories inside or moving them to another category."""
    from datetime import datetime
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    folder_name = data.get('folder_name', '').strip()
    action = data.get('action', 'delete').strip() # 'delete' or 'move'
    move_to = data.get('move_to', 'सामान्य').strip()
    
    if not folder_name:
        return jsonify({"success": False, "error": "folder_name is required"}), 400
        
    conn = katha_db.get_db()
    try:
        if action == 'move':
            cursor = conn.execute(
                'UPDATE kathas SET category = ?, updated_at = ? WHERE category = ?',
                (move_to, get_ist_now().isoformat(), folder_name)
            )
            conn.commit()
            count = cursor.rowcount
            log_change(session.get('admin_username'), 'MOVE_FOLDER_STORIES', 'KATHA_FOLDER', folder_name, after_data={'moved_to': move_to, 'affected_stories': count})
            return jsonify({"success": True, "message": f"Folder '{folder_name}' removed. {count} stories moved to '{move_to}'."})
        else:
            cursor = conn.execute(
                'DELETE FROM kathas WHERE category = ?',
                (folder_name,)
            )
            cnt = conn.execute('SELECT COUNT(*) FROM kathas').fetchone()[0]
            if cnt == 0:
                conn.execute("DELETE FROM sqlite_sequence WHERE name = 'kathas'")
            conn.commit()
            count = cursor.rowcount
            log_change(session.get('admin_username'), 'DELETE_FOLDER', 'KATHA_FOLDER', folder_name, after_data={'deleted_stories': count})
            return jsonify({"success": True, "message": f"Folder '{folder_name}' and all its {count} stories have been deleted."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/sync/metadata/<path:book_name>', methods=['GET'])
def sync_get_metadata(book_name):
    """Serve the metadata.txt file for a specific book."""
    import sdl as main_app
    from flask import send_file as _send_file

    upload_folder = main_app.app.config['UPLOAD_FOLDER']
    metadata_path = os.path.join(upload_folder, book_name, 'metadata.txt')

    if os.path.exists(metadata_path):
        return _send_file(metadata_path, mimetype='text/plain')
    return jsonify({'error': 'Metadata not found'}), 404


@api_bp.route('/sync/book-files/<path:book_name>', methods=['GET'])
def sync_download_book_files(book_name):
    """Returns a JSON mapping of all filenames and their contents (text or base64) in the book's uploads directory."""
    import sdl as main_app
    import base64

    upload_folder = main_app.app.config['UPLOAD_FOLDER']
    book_dir = os.path.join(upload_folder, book_name)

    # Basic security checks against path traversal
    if '..' in book_name or book_name.startswith('/'):
        return jsonify({'error': 'Invalid book name'}), 400

    if not os.path.exists(book_dir) or not os.path.isdir(book_dir):
        return jsonify({'error': 'Book directory not found'}), 404

    files_data = {}
    for filename in os.listdir(book_dir):
        file_path = os.path.join(book_dir, filename)
        if os.path.isfile(file_path):
            try:
                # Try reading as text
                with open(file_path, 'r', encoding='utf-8') as f:
                    files_data[filename] = {
                        'type': 'text',
                        'content': f.read()
                    }
            except UnicodeDecodeError:
                # If binary, base64 encode
                with open(file_path, 'rb') as f:
                    files_data[filename] = {
                        'type': 'binary',
                        'content': base64.b64encode(f.read()).decode('utf-8')
                    }
            except Exception as e:
                return jsonify({'error': f"Failed to read file {filename}: {str(e)}"}), 500

    return jsonify({'success': True, 'files': files_data})


@api_bp.route('/sync/books-list', methods=['POST'])
def sync_books_list():
    """Returns a list of all books."""
    from sdl import get_all_books
    try:
        books = get_all_books()
        sanitized_books = []
        for b in books:
            sanitized_books.append({
                "name": b['name'],
                "tags": b.get('tags', ''),
                "archive_url": b.get('archive_url', ''),
                "has_ocr": b.get('has_txt', False),
                "notes": b.get('notes', '')
            })
        return jsonify({"success": True, "books": sanitized_books})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route('/sync/favorites', methods=['POST'])
def sync_favorites():
    """2-way merge favorites: receives local favorites, returns merged set."""

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Missing request body'}), 400

    token = data.get('token', '')
    local_favs = data.get('favorites', [])

    # Verify token
    user_id = common_db.verify_user_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

    # Get server-side favorites
    server_favs = common_db.get_favourites(user_id)
    server_fav_names = set(f['book_name'] for f in server_favs)
    local_fav_set = set(local_favs)

    force_update = data.get('force_update', False)

    if force_update:
        # Client made a local change — overwrite server with client's list
        conn = common_db.get_db()
        try:
            conn.execute('DELETE FROM favourites WHERE user_id = ?', (user_id,))
            for book_name in local_fav_set:
                conn.execute(
                    'INSERT OR IGNORE INTO favourites (user_id, book_name) VALUES (?, ?)',
                    (user_id, book_name)
                )
            conn.commit()
        finally:
            conn.close()
        merged = local_fav_set
    else:
        # Page-load sync — server is the source of truth.
        # Just return the server's current favorites. Client will overwrite local to match.
        merged = server_fav_names

    return jsonify({
        'success': True,
        'merged_favorites': list(merged)
    })


@api_bp.route('/sync/booklists', methods=['POST'])
def sync_booklists():
    """Sync booklists: server is source of truth.
    force_update=True: client overwrites server.
    force_update=False: server returns its current state."""

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Missing request body'}), 400

    token = data.get('token', '')
    local_booklists = data.get('booklists', [])

    user_id = common_db.verify_user_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

    force_update = data.get('force_update', False)

    if force_update:
        # Client made local changes — overwrite server with client's booklists
        conn = common_db.get_db()
        try:
            # Delete all existing booklists and items for this user
            existing_lists = common_db.get_booklists(user_id)
            for bl in existing_lists:
                conn.execute('DELETE FROM booklist_items WHERE booklist_id = ?', (bl['id'],))
                conn.execute('DELETE FROM booklists WHERE id = ?', (bl['id'],))

            # Re-create from client's data
            for local_bl in local_booklists:
                bl_name = local_bl.get('name', '')
                bl_desc = local_bl.get('description', '')
                bl_items = local_bl.get('items', [])
                cursor = conn.execute(
                    'INSERT INTO booklists (user_id, name, description) VALUES (?, ?, ?)',
                    (user_id, bl_name, bl_desc)
                )
                new_id = cursor.lastrowid
                for item in bl_items:
                    conn.execute(
                        'INSERT OR IGNORE INTO booklist_items (booklist_id, book_name) VALUES (?, ?)',
                        (new_id, item)
                    )
            conn.commit()
        finally:
            conn.close()

    # Build response from server's current state (which may have just been overwritten above)
    server_lists = common_db.get_booklists(user_id)
    merged = []
    for bl in server_lists:
        detail = common_db.get_booklist_detail(bl['id'], user_id)
        if detail:
            merged.append({
                'name': detail['name'],
                'description': detail.get('description', ''),
                'items': [item['book_name'] for item in detail.get('items', [])]
            })

    return jsonify({
        'success': True,
        'merged_booklists': merged
    })


@api_bp.route('/sync/quiz-results', methods=['POST'])
def sync_quiz_results():
    """Receive quiz results from Granthalaya OS. Duplicate prevention by
    checking (user_id, subject, level, score, taken_at) composite."""

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Missing request body'}), 400

    token = data.get('token', '')
    results = data.get('results', [])

    user_id = common_db.verify_user_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401

    new_count = 0
    conn = common_db.get_db()
    try:
        for r in results:
            subject = r.get('subject', '')
            level = r.get('level', '')
            score = r.get('score', 0)
            total = r.get('total', 0)
            percentage = r.get('percentage', 0)
            lang = r.get('lang', 'en')
            taken_at = r.get('taken_at', '')

            # Check for duplicate
            existing = conn.execute(
                '''SELECT id FROM quiz_results
                   WHERE user_id = ? AND subject = ? AND level = ? AND score = ? AND taken_at = ?''',
                (user_id, subject, level, score, taken_at)
            ).fetchone()

            if not existing:
                conn.execute(
                    '''INSERT INTO quiz_results (user_id, subject, level, score, total, percentage, lang, taken_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, subject, level, score, total, percentage, lang, taken_at or time.strftime('%Y-%m-%d %H:%M:%S'))
                )
                new_count += 1

        conn.commit()
    finally:
        conn.close()

    return jsonify({
        'success': True,
        'new_count': new_count,
        'total_received': len(results)
    })


@api_bp.route('/sync/articles', methods=['GET'])
def sync_get_articles():
    """Returns a list of all static articles and their modification times."""
    import sdl as main_app
    import hashlib
    articles_dir = os.path.join(main_app.app.root_path, '..', 'articles')
    articles_list = []
    
    if os.path.exists(articles_dir):
        for filename in os.listdir(articles_dir):
            if filename.endswith('.html'):
                file_path = os.path.join(articles_dir, filename)
                mtime = os.path.getmtime(file_path)
                # Compute quick sha256 for integrity checks
                sha256 = hashlib.sha256()
                with open(file_path, 'rb') as f:
                    sha256.update(f.read())
                articles_list.append({
                    'name': filename,
                    'mtime': mtime,
                    'checksum': f'sha256:{sha256.hexdigest()}'
                })
                
    return jsonify({
        'success': True,
        'articles': articles_list
    })


@api_bp.route('/sync/article/<path:filename>', methods=['GET'])
def sync_download_article(filename):
    """Download a specific article HTML file."""
    import sdl as main_app
    from flask import send_from_directory
    articles_dir = os.path.join(main_app.app.root_path, '..', 'articles')
    
    # Basic security against path traversal
    if '..' in filename or filename.startswith('/'):
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
        
    return send_from_directory(articles_dir, filename)


@api_bp.route('/sync/profile-pic', methods=['POST'])
def sync_profile_pic():
    """2-way sync for user profile picture and avatar index."""
    import base64
    import sdl as main_app
    
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Missing request body'}), 400

    token = data.get('token', '')
    user_id = common_db.verify_user_token(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        
    local_avatar_idx = data.get('avatar_idx', 0)
    local_has_pic = data.get('has_pic', False)
    local_pic_mtime = data.get('pic_mtime', 0)
    local_pic_b64 = data.get('pic_base64', '')
    local_pic_ext = data.get('pic_ext', 'jpg')
    
    # Get server user details
    server_user = common_db.get_user_by_id(user_id)
    if not server_user:
        return jsonify({'success': False, 'error': 'User not found'}), 404
        
    server_avatar_idx = server_user.get('avatar_idx') or 0
    server_profile_pic = server_user.get('profile_pic')
    
    upload_dir = os.path.join(main_app.app.root_path, 'static', 'uploads', 'profile_pics')
    server_pic_mtime = 0
    if server_profile_pic:
        server_pic_path = os.path.join(upload_dir, server_profile_pic)
        if os.path.exists(server_pic_path):
            server_pic_mtime = os.path.getmtime(server_pic_path)
        else:
            server_profile_pic = None
            
    action = 'none'
    force_update = data.get('force_update', False)
    
    if force_update:
        # Force overwrite the server state from client's payload
        common_db.update_user_avatar(user_id, local_avatar_idx)
        
        if local_has_pic and local_pic_b64:
            try:
                pic_data = base64.b64decode(local_pic_b64)
                os.makedirs(upload_dir, exist_ok=True)
                new_filename = f"user_{user_id}.{local_pic_ext}"
                file_path = os.path.join(upload_dir, new_filename)
                with open(file_path, 'wb') as f:
                    f.write(pic_data)
                
                # Align timestamps to prevent infinite loops due to clock drift
                try:
                    os.utime(file_path, (time.time(), local_pic_mtime or time.time()))
                except:
                    pass
                common_db.update_user_profile_pic(user_id, new_filename)
            except Exception as e:
                return jsonify({'success': False, 'error': f'Failed to force save picture: {str(e)}'}), 500
        else:
            # Delete file if exists and clear database
            if server_profile_pic:
                try:
                    old_path = os.path.join(upload_dir, server_profile_pic)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except:
                    pass
            common_db.update_user_profile_pic(user_id, None)
            
        return jsonify({
            'success': True,
            'action': 'updated_server',
            'avatar_idx': local_avatar_idx,
            'has_pic': local_has_pic
        })

    # Non-force: Server is source of truth. Return server's current state.
    # The client will update its local DB to match.
    if server_profile_pic:
        server_pic_path = os.path.join(upload_dir, server_profile_pic)
        try:
            with open(server_pic_path, 'rb') as f:
                server_pic_base64 = base64.b64encode(f.read()).decode('utf-8')
            ext = server_profile_pic.rsplit('.', 1)[-1] if '.' in server_profile_pic else 'jpg'
            
            return jsonify({
                'success': True,
                'action': 'updated_local',
                'avatar_idx': server_avatar_idx,
                'has_pic': True,
                'pic_base64': server_pic_base64,
                'pic_ext': ext,
                'pic_mtime': server_pic_mtime
            })
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to read server picture: {str(e)}'}), 500

    # Server has no profile pic — return avatar index only
    return jsonify({
        'success': True,
        'action': 'none',
        'avatar_idx': server_avatar_idx,
        'has_pic': False
    })






# =============================================================================
# ARTICLES ADMINISTRATIVE & PUBLIC API
# =============================================================================

def articles_admin_required(f):
    """Decorator: require SUPERADMIN or PERM_MANAGE_ARTICLES for articles admin endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if session.get('admin_role') == 'super':
            return f(*args, **kwargs)
        user_perms = session.get('admin_permissions', [])
        if common_db.PERM_MANAGE_ARTICLES in user_perms:
            return f(*args, **kwargs)
        return jsonify({"success": False, "error": "Articles admin access required"}), 403
    return decorated_function


@api_bp.route('/articles/admin-login', methods=['POST'])
def articles_admin_login():
    """Verify articles admin credentials.
    Accepts SUPERADMIN or any admin with PERM_MANAGE_ARTICLES permission."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({"success": False, "error": "Username and password are required"}), 400
        
    stored_username, admin_data = common_db.get_admin_by_username(username)
    
    if stored_username and admin_data and common_db.verify_password(password, admin_data['password_hash']):
        session['logged_in'] = True
        session['admin_username'] = stored_username
        # Super-admin always has access
        if stored_username.upper() == 'SUPERADMIN':
            session['admin_role'] = 'super'
            session['admin_permissions'] = common_db.ALL_PERMISSIONS
            return jsonify({"success": True, "role": "superadmin"})
        # Check for PERM_MANAGE_ARTICLES permission
        perms = admin_data.get('permissions', [])
        if common_db.PERM_MANAGE_ARTICLES in perms:
            session['admin_role'] = 'low-level'
            session['admin_permissions'] = perms
            return jsonify({"success": True, "role": "articles_admin"})
            
    return jsonify({"success": False, "error": "Invalid admin credentials"}), 401


# Public APIs
@api_bp.route('/articles', methods=['GET'])
def get_articles():
    """Get published articles for public landing page."""
    category = request.args.get('category', '').strip() or None
    sort_by = request.args.get('sort_by', 'date_desc').strip()
    articles = articles_db.get_published_articles(category=category, sort_by=sort_by)
    return jsonify({"success": True, "articles": articles, "count": len(articles)})


@api_bp.route('/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """Get a single article by ID."""
    article = articles_db.get_article_by_id(article_id)
    if not article:
        return jsonify({"success": False, "error": "Article not found"}), 404
    return jsonify({"success": True, "article": article})


@api_bp.route('/articles/categories', methods=['GET'])
def get_articles_categories():
    """Get distinct article categories."""
    categories = articles_db.get_categories()
    return jsonify({"success": True, "categories": categories})


@api_bp.route('/articles/<int:article_id>/feedback', methods=['POST'])
def submit_article_feedback(article_id):
    """Submit thumbs up/down vote for an article."""
    data = request.get_json()
    if not data or 'vote' not in data:
        return jsonify({"success": False, "error": "Vote parameter is required"}), 400
        
    vote = data.get('vote')
    if vote not in ('up', 'down'):
        return jsonify({"success": False, "error": "Invalid vote value. Must be 'up' or 'down'"}), 400
        
    voter_ip = request.remote_addr
    res = articles_db.submit_feedback(article_id, vote, voter_ip)
    return jsonify({
        "success": True,
        "vote": res.get('vote'),
        "upvotes": res.get('upvotes', 0),
        "downvotes": res.get('downvotes', 0)
    })


# Admin CRUD APIs
@api_bp.route('/articles/admin/articles', methods=['GET'])
@articles_admin_required
def admin_get_articles():
    """Get all articles (including drafts) and categories."""
    articles = articles_db.get_all_articles()
    categories = articles_db.get_all_categories()
    return jsonify({
        "success": True,
        "articles": articles,
        "categories": categories
    })


@api_bp.route('/articles/admin/articles', methods=['POST'])
@articles_admin_required
def admin_create_article():
    """Create a new article."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    title = data.get('title', '').strip()
    summary = data.get('summary', '').strip()
    content_html = data.get('content_html', '').strip()
    category = data.get('category', '').strip() or 'सामान्य'
    cover_image_url = data.get('cover_image_url', '').strip()
    author = data.get('author', '').strip()
    reading_time = int(data.get('reading_time', 5))
    status = data.get('status', 'draft')
    published_at = data.get('published_at', '').strip() or None
    
    if not title or not content_html:
        return jsonify({"success": False, "error": "Title and content are required"}), 400
        
    new_id = articles_db.create_article(
        title=title,
        summary=summary,
        content_html=content_html,
        category=category,
        cover_image_url=cover_image_url,
        author=author,
        reading_time=reading_time,
        status=status,
        published_at=published_at
    )
    
    if new_id:
        log_change(session.get('admin_username'), 'CREATE', 'ARTICLE', new_id, after_data={'title': title, 'category': category, 'status': status})
        return jsonify({"success": True, "id": new_id, "message": "Article created successfully"})
    return jsonify({"success": False, "error": "Failed to create article"}), 500


@api_bp.route('/articles/admin/articles/<int:article_id>', methods=['PUT'])
@articles_admin_required
def admin_update_article(article_id):
    """Update an existing article."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
        
    title = data.get('title', '').strip()
    summary = data.get('summary', '').strip()
    content_html = data.get('content_html', '').strip()
    category = data.get('category', '').strip() or 'सामान्य'
    cover_image_url = data.get('cover_image_url', '').strip()
    author = data.get('author', '').strip()
    reading_time = int(data.get('reading_time', 5))
    published_at = data.get('published_at', '').strip() or None
    status = data.get('status')
    
    if not title or not content_html:
        return jsonify({"success": False, "error": "Title and content are required"}), 400
        
    check_status = status
    if not check_status:
        existing = articles_db.get_article_by_id(article_id)
        check_status = existing.get('status') if existing else 'draft'
        
    success = articles_db.update_article(
        article_id=article_id,
        title=title,
        summary=summary,
        content_html=content_html,
        category=category,
        cover_image_url=cover_image_url,
        author=author,
        reading_time=reading_time,
        published_at=published_at,
        status=status
    )
    
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'ARTICLE', article_id, after_data={'title': title, 'category': category, 'status': status})
        return jsonify({"success": True, "message": "Article updated successfully"})
    return jsonify({"success": False, "error": "Failed to update article"}), 500


@api_bp.route('/articles/admin/articles/<int:article_id>', methods=['DELETE'])
@articles_admin_required
def admin_delete_article(article_id):
    """Delete an article."""
    success = articles_db.delete_article(article_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'ARTICLE', article_id)
        return jsonify({"success": True, "message": "Article deleted successfully"})
    return jsonify({"success": False, "error": "Failed to delete article"}), 500


@api_bp.route('/articles/admin/articles/<int:article_id>/toggle-status', methods=['POST'])
@articles_admin_required
def admin_toggle_article_status(article_id):
    """Toggle article status between draft and published."""
    try:
        new_status = articles_db.toggle_status(article_id)
        if new_status:
            log_change(session.get('admin_username'), 'UPDATE', 'ARTICLE', article_id, after_data={'status': new_status})
            return jsonify({"success": True, "status": new_status, "message": f"Article status updated to {new_status}"})
        return jsonify({"success": False, "error": "Failed to toggle status"}), 500
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route('/articles/admin/articles/bulk-delete', methods=['POST'])
@articles_admin_required
def admin_bulk_delete_articles():
    """Delete multiple articles by ID list."""
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400

    count = 0
    for article_id in ids:
        if articles_db.delete_article(article_id):
            count += 1

    log_change(session.get('admin_username'), 'DELETE_BULK', 'ARTICLE', f"{count} articles", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Successfully deleted {count} articles"})


@api_bp.route('/articles/admin/articles/import', methods=['POST'])
@articles_admin_required
def admin_import_articles():
    """Bulk import articles from a JSON array in request body."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400

    articles_list = data.get('articles', [])
    if not articles_list or not isinstance(articles_list, list):
        return jsonify({"success": False, "error": "articles must be a non-empty array"}), 400

    added, errors, skipped = articles_db.import_articles(articles_list)
    log_change(session.get('admin_username'), 'IMPORT', 'ARTICLE', f"{added} articles", after_data={'added': added, 'errors': len(errors), 'skipped': len(skipped)})
    
    total = articles_db.get_article_count()
    return jsonify({
        "success": True,
        "added": added,
        "total": total,
        "errors": errors,
        "skipped": skipped
    })


@api_bp.route('/articles/admin/upload-image', methods=['POST'])
@articles_admin_required
def admin_upload_article_image():
    """Upload article cover or content images to articles/uploads/ directory."""
    if 'image' not in request.files:
        return jsonify({"success": False, "error": "No image file provided"}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400
        
    import uuid
    import time
    
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    upload_dir = os.path.join(app_root, 'articles', 'uploads')
    try:
        os.makedirs(upload_dir, exist_ok=True)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to create upload directory: {e}"}), 500
        
    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    filename = f"img_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
    dest_path = os.path.join(upload_dir, filename)
    
    try:
        file.save(dest_path)
        return jsonify({"success": True, "url": f"/articles/uploads/{filename}"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save image: {e}"}), 500


# =============================================================================
# UNIFIED PLAY (GAMES) API
# =============================================================================

def play_admin_required(f):
    """Decorator: require SUPERADMIN or PERM_MANAGE_PLAY for play admin endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if session.get('admin_role') == 'super':
            return f(*args, **kwargs)
        user_perms = session.get('admin_permissions', [])
        if 'PERM_MANAGE_PLAY' in user_perms:
            return f(*args, **kwargs)
        return jsonify({"success": False, "error": "Play admin access required"}), 403
    return decorated_function


# --- Public Game Data Endpoints ---

@api_bp.route('/play/synonym-match/sets', methods=['GET'])
def play_get_synonym_sets():
    sets = play_db.get_all_synonym_sets()
    return jsonify({"success": True, "sets": sets, "count": len(sets)})


@api_bp.route('/play/synonym-match/sets/<int:set_id>', methods=['GET'])
def play_get_synonym_set(set_id):
    s = play_db.get_synonym_set(set_id)
    if not s:
        return jsonify({"success": False, "error": "Set not found"}), 404
    return jsonify({"success": True, "set": s})


@api_bp.route('/play/word-builder/sets', methods=['GET'])
def play_get_word_builder_sets():
    sets = play_db.get_all_word_builder_sets()
    return jsonify({"success": True, "sets": sets, "count": len(sets)})


@api_bp.route('/play/word-builder/sets/<int:set_id>', methods=['GET'])
def play_get_word_builder_set(set_id):
    s = play_db.get_word_builder_set(set_id)
    if not s:
        return jsonify({"success": False, "error": "Set not found"}), 404
    return jsonify({"success": True, "set": s})


@api_bp.route('/play/word-search/sets', methods=['GET'])
def play_get_word_search_sets():
    sets = play_db.get_all_word_search_sets()
    return jsonify({"success": True, "sets": sets, "count": len(sets)})


@api_bp.route('/play/word-search/sets/<int:set_id>', methods=['GET'])
def play_get_word_search_set(set_id):
    s = play_db.get_word_search_set(set_id)
    if not s:
        return jsonify({"success": False, "error": "Set not found"}), 404
    return jsonify({"success": True, "set": s})


@api_bp.route('/play/results', methods=['POST'])
def play_save_result():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
    
    user_id = session.get('user_id') if 'user_logged_in' in session else None
    
    game_type = data.get('game_type')
    set_id = data.get('set_id')
    set_title = data.get('set_title')
    score = data.get('score')
    total = data.get('total')
    percentage = data.get('percentage')
    time_taken = data.get('time_taken')
    
    if not game_type or set_id is None or not set_title or score is None or total is None or percentage is None:
         return jsonify({"success": False, "error": "Missing required fields"}), 400
         
    try:
         res_id = play_db.save_play_result(
             user_id=user_id,
             game_type=game_type,
             set_id=int(set_id),
             set_title=set_title,
             score=int(score),
             total=int(total),
             percentage=int(percentage),
             time_taken=int(time_taken) if time_taken is not None else None
         )
         if res_id:
             return jsonify({"success": True, "id": res_id, "message": "Result saved successfully"})
         return jsonify({"success": False, "error": "Failed to save result"}), 500
    except Exception as e:
         return jsonify({"success": False, "error": str(e)}), 500


# --- Admin CRUD Endpoints (Synonym Match) ---

@api_bp.route('/play/synonym-match/sets', methods=['POST'])
@play_admin_required
def play_add_synonym_set():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    pairs = data.get('pairs', [])
    time_limit = int(data.get('time_limit', 300))
    
    set_id = play_db.add_synonym_set(title, pairs, time_limit)
    if set_id:
        log_change(session.get('admin_username'), 'CREATE', 'PLAY_SYNONYM_SET', set_id, after_data={'title': title, 'pairs_count': len(pairs)})
        return jsonify({"success": True, "id": set_id, "message": "Set added successfully"})
    return jsonify({"success": False, "error": "Failed to add set"}), 500


@api_bp.route('/play/synonym-match/sets/<int:set_id>', methods=['PUT'])
@play_admin_required
def play_update_synonym_set(set_id):
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    pairs = data.get('pairs', [])
    time_limit = int(data.get('time_limit', 300))
    
    success = play_db.update_synonym_set(set_id, title, pairs, time_limit)
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'PLAY_SYNONYM_SET', set_id, after_data={'title': title, 'pairs_count': len(pairs)})
        return jsonify({"success": True, "message": "Set updated successfully"})
    return jsonify({"success": False, "error": "Failed to update set"}), 500


@api_bp.route('/play/synonym-match/sets/<int:set_id>', methods=['DELETE'])
@play_admin_required
def play_delete_synonym_set(set_id):
    success = play_db.delete_synonym_set(set_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'PLAY_SYNONYM_SET', set_id)
        return jsonify({"success": True, "message": "Set deleted successfully"})
    return jsonify({"success": False, "error": "Failed to delete set"}), 500


@api_bp.route('/play/synonym-match/sets/bulk-delete', methods=['POST'])
@play_admin_required
def play_bulk_delete_synonym_sets():
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400
    count = play_db.delete_synonym_sets_bulk(ids)
    log_change(session.get('admin_username'), 'DELETE_BULK', 'PLAY_SYNONYM_SET', f"{count} sets", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Deleted {count} set(s)"})


@api_bp.route('/play/synonym-match/import', methods=['POST'])
@play_admin_required
def play_import_synonym_sets():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
    sets_list = data.get('sets', [])
    if not sets_list or not isinstance(sets_list, list):
        return jsonify({"success": False, "error": "sets must be a non-empty array"}), 400
        
    added, errors = play_db.import_synonym_sets(sets_list)
    log_change(session.get('admin_username'), 'IMPORT', 'PLAY_SYNONYM_SET', f"{added} sets", after_data={'added': added, 'errors': len(errors)})
    return jsonify({
        "success": True,
        "added": added,
        "total": play_db.get_synonym_set_count(),
        "errors": errors
    })


# --- Admin CRUD Endpoints (Word Builder) ---

@api_bp.route('/play/word-builder/sets', methods=['POST'])
@play_admin_required
def play_add_word_builder_set():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    syllables = data.get('syllables', [])
    target_words = data.get('target_words', [])
    time_limit = int(data.get('time_limit', 300))
    
    set_id = play_db.add_word_builder_set(title, syllables, target_words, time_limit)
    if set_id:
        log_change(session.get('admin_username'), 'CREATE', 'PLAY_WORD_BUILDER_SET', set_id, after_data={'title': title, 'syllables_count': len(syllables), 'targets_count': len(target_words)})
        return jsonify({"success": True, "id": set_id, "message": "Set added successfully"})
    return jsonify({"success": False, "error": "Failed to add set"}), 500


@api_bp.route('/play/word-builder/sets/<int:set_id>', methods=['PUT'])
@play_admin_required
def play_update_word_builder_set(set_id):
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    syllables = data.get('syllables', [])
    target_words = data.get('target_words', [])
    time_limit = int(data.get('time_limit', 300))
    
    success = play_db.update_word_builder_set(set_id, title, syllables, target_words, time_limit)
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'PLAY_WORD_BUILDER_SET', set_id, after_data={'title': title, 'syllables_count': len(syllables), 'targets_count': len(target_words)})
        return jsonify({"success": True, "message": "Set updated successfully"})
    return jsonify({"success": False, "error": "Failed to update set"}), 500


@api_bp.route('/play/word-builder/sets/<int:set_id>', methods=['DELETE'])
@play_admin_required
def play_delete_word_builder_set(set_id):
    success = play_db.delete_word_builder_set(set_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'PLAY_WORD_BUILDER_SET', set_id)
        return jsonify({"success": True, "message": "Set deleted successfully"})
    return jsonify({"success": False, "error": "Failed to delete set"}), 500


@api_bp.route('/play/word-builder/sets/bulk-delete', methods=['POST'])
@play_admin_required
def play_bulk_delete_word_builder_sets():
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400
    count = play_db.delete_word_builder_sets_bulk(ids)
    log_change(session.get('admin_username'), 'DELETE_BULK', 'PLAY_WORD_BUILDER_SET', f"{count} sets", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Deleted {count} set(s)"})


@api_bp.route('/play/word-builder/import', methods=['POST'])
@play_admin_required
def play_import_word_builder_sets():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
    sets_list = data.get('sets', [])
    if not sets_list or not isinstance(sets_list, list):
        return jsonify({"success": False, "error": "sets must be a non-empty array"}), 400
        
    added, errors = play_db.import_word_builder_sets(sets_list)
    log_change(session.get('admin_username'), 'IMPORT', 'PLAY_WORD_BUILDER_SET', f"{added} sets", after_data={'added': added, 'errors': len(errors)})
    return jsonify({
        "success": True,
        "added": added,
        "total": play_db.get_word_builder_set_count(),
        "errors": errors
    })


# --- Admin CRUD Endpoints (Word Search) ---

@api_bp.route('/play/word-search/sets', methods=['POST'])
@play_admin_required
def play_add_word_search_set():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    grid_size = data.get('grid_size', 4)
    target_words = data.get('target_words', [])
    time_limit = int(data.get('time_limit', 300))
    
    set_id = play_db.add_word_search_set(title, grid_size, target_words, time_limit)
    if set_id:
        log_change(session.get('admin_username'), 'CREATE', 'PLAY_WORD_SEARCH_SET', set_id, after_data={'title': title, 'grid_size': grid_size, 'targets_count': len(target_words)})
        return jsonify({"success": True, "id": set_id, "message": "Set added successfully"})
    return jsonify({"success": False, "error": "Failed to add set"}), 500


@api_bp.route('/play/word-search/sets/<int:set_id>', methods=['PUT'])
@play_admin_required
def play_update_word_search_set(set_id):
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({"success": False, "error": "Title is required"}), 400
    title = data['title'].strip()
    grid_size = data.get('grid_size', 4)
    target_words = data.get('target_words', [])
    time_limit = int(data.get('time_limit', 300))
    
    success = play_db.update_word_search_set(set_id, title, grid_size, target_words, time_limit)
    if success:
        log_change(session.get('admin_username'), 'UPDATE', 'PLAY_WORD_SEARCH_SET', set_id, after_data={'title': title, 'grid_size': grid_size, 'targets_count': len(target_words)})
        return jsonify({"success": True, "message": "Set updated successfully"})
    return jsonify({"success": False, "error": "Failed to update set"}), 500


@api_bp.route('/play/word-search/sets/<int:set_id>', methods=['DELETE'])
@play_admin_required
def play_delete_word_search_set(set_id):
    success = play_db.delete_word_search_set(set_id)
    if success:
        log_change(session.get('admin_username'), 'DELETE', 'PLAY_WORD_SEARCH_SET', set_id)
        return jsonify({"success": True, "message": "Set deleted successfully"})
    return jsonify({"success": False, "error": "Failed to delete set"}), 500


@api_bp.route('/play/word-search/sets/bulk-delete', methods=['POST'])
@play_admin_required
def play_bulk_delete_word_search_sets():
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"}), 400
    count = play_db.delete_word_search_sets_bulk(ids)
    log_change(session.get('admin_username'), 'DELETE_BULK', 'PLAY_WORD_SEARCH_SET', f"{count} sets", after_data={'ids': ids})
    return jsonify({"success": True, "deleted": count, "message": f"Deleted {count} set(s)"})


@api_bp.route('/play/word-search/import', methods=['POST'])
@play_admin_required
def play_import_word_search_sets():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Missing request body"}), 400
    sets_list = data.get('sets', [])
    if not sets_list or not isinstance(sets_list, list):
        return jsonify({"success": False, "error": "sets must be a non-empty array"}), 400
        
    added, errors = play_db.import_word_search_sets(sets_list)
    log_change(session.get('admin_username'), 'IMPORT', 'PLAY_WORD_SEARCH_SET', f"{added} sets", after_data={'added': added, 'errors': len(errors)})
    return jsonify({
        "success": True,
        "added": added,
        "total": play_db.get_word_search_set_count(),
        "errors": errors
    })



