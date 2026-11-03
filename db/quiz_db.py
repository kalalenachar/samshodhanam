"""
Sanskrit Digital Library - Quiz Database Module

SQLite database for quiz questions and user quiz results.
"""

import sqlite3
import os
import json as _json
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'quiz.db')


def _create_tables(conn):
    """Internal helper to create all tables and indexes in the provided connection."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            level TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage INTEGER NOT NULL,
            lang TEXT NOT NULL,
            taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            guest_name TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS quiz_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL DEFAULT 'General',
            level TEXT NOT NULL DEFAULT 'Default',
            question_json TEXT NOT NULL,
            options_json TEXT NOT NULL,
            answer_index INTEGER NOT NULL,
            explanation_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quiz_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL,
            user_id INTEGER,
            vote TEXT NOT NULL,
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_quiz_results_user ON quiz_results(user_id);
        CREATE INDEX IF NOT EXISTS idx_quiz_questions_subject ON quiz_questions(subject);
        CREATE INDEX IF NOT EXISTS idx_quiz_questions_level ON quiz_questions(subject, level);
        CREATE INDEX IF NOT EXISTS idx_quiz_feedback_question ON quiz_feedback(question_id);
    ''')
    conn.commit()


def get_db():
    """Get a database connection with row_factory for dict-like access. Auto-initializes tables if file is missing/empty."""
    db_exists = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    
    if not db_exists:
        try:
            _create_tables(conn)
            print(f"Quiz database auto-initialized at {DB_PATH}")
        except Exception as e:
            print(f"Error auto-initializing database tables: {e}")
            
    return conn


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    try:
        _create_tables(conn)
        # Dynamic migration check to add guest_name column for existing databases
        try:
            conn.execute("ALTER TABLE quiz_results ADD COLUMN guest_name TEXT DEFAULT NULL")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists or table doesn't exist yet
            pass
        print(f"Quiz database initialized at {DB_PATH}")
    finally:
        conn.close()


def save_quiz_result(user_id, subject, level, score, total, percentage, lang, guest_name=None):
    """Save a user's quiz score."""
    conn = get_db()
    try:
        cursor = conn.execute(
            '''INSERT INTO quiz_results (user_id, subject, level, score, total, percentage, lang, guest_name) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, subject, level, score, total, percentage, lang, guest_name)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error saving quiz result: {e}")
        return None
    finally:
        conn.close()


def get_user_quiz_results(user_id):
    """Fetch quiz history for a given user, sorted by date descending."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, subject, level, score, total, percentage, lang, taken_at 
               FROM quiz_results 
               WHERE user_id = ? 
               ORDER BY taken_at DESC''',
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting user quiz results: {e}")
        return []
    finally:
        conn.close()


def get_all_quiz_questions(subject=None, level=None):
    """Get all quiz questions, optionally filtered by subject and/or level.
    Returns list of dicts with parsed JSON fields."""
    conn = get_db()
    try:
        query = 'SELECT * FROM quiz_questions'
        params = []
        conditions = []
        if subject:
            conditions.append('subject = ?')
            params.append(subject)
        if level:
            conditions.append('level = ?')
            params.append(level)
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        query += ' ORDER BY id ASC'

        rows = conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            results.append({
                'id': r['id'],
                'subject': r['subject'],
                'level': r['level'],
                'question': _json.loads(r['question_json']),
                'options': _json.loads(r['options_json']),
                'answerIndex': r['answer_index'],
                'explanation': _json.loads(r['explanation_json']),
            })
        return results
    except Exception as e:
        print(f"Error getting quiz questions: {e}")
        return []
    finally:
        conn.close()


def get_quiz_question_by_id(question_id):
    """Get a single quiz question by ID."""
    conn = get_db()
    try:
        r = conn.execute('SELECT * FROM quiz_questions WHERE id = ?', (question_id,)).fetchone()
        if not r:
            return None
        return {
            'id': r['id'],
            'subject': r['subject'],
            'level': r['level'],
            'question': _json.loads(r['question_json']),
            'options': _json.loads(r['options_json']),
            'answerIndex': r['answer_index'],
            'explanation': _json.loads(r['explanation_json']),
        }
    except Exception as e:
        print(f"Error getting quiz question: {e}")
        return None
    finally:
        conn.close()


def add_quiz_question(subject, level, question, options, answer_index, explanation):
    """Add a new quiz question. question/options/explanation can be dicts or strings (auto-serialized).
    Returns the new question ID or None."""
    conn = get_db()
    try:
        q_json = _json.dumps(question, ensure_ascii=False) if isinstance(question, dict) else question
        o_json = _json.dumps(options, ensure_ascii=False) if isinstance(options, dict) else options
        e_json = _json.dumps(explanation, ensure_ascii=False) if isinstance(explanation, dict) else explanation

        # Duplicate check scoped to subject, question, options
        existing = conn.execute(
            'SELECT id FROM quiz_questions WHERE subject = ? AND question_json = ? AND options_json = ?',
            (subject, q_json, o_json)
        ).fetchone()
        if existing:
            raise ValueError("Duplicate question already exists under this subject.")

        cursor = conn.execute(
            '''INSERT INTO quiz_questions (subject, level, question_json, options_json, answer_index, explanation_json)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (subject, level, q_json, o_json, int(answer_index), e_json)
        )
        conn.commit()
        return cursor.lastrowid
    except ValueError:
        raise
    except Exception as e:
        print(f"Error adding quiz question: {e}")
        return None
    finally:
        conn.close()


def update_quiz_question(question_id, subject, level, question, options, answer_index, explanation):
    """Update an existing quiz question. Returns True on success."""
    conn = get_db()
    try:
        q_json = _json.dumps(question, ensure_ascii=False) if isinstance(question, dict) else question
        o_json = _json.dumps(options, ensure_ascii=False) if isinstance(options, dict) else options
        e_json = _json.dumps(explanation, ensure_ascii=False) if isinstance(explanation, dict) else explanation

        conn.execute(
            '''UPDATE quiz_questions SET subject=?, level=?, question_json=?, options_json=?,
               answer_index=?, explanation_json=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?''',
            (subject, level, q_json, o_json, int(answer_index), e_json, question_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating quiz question: {e}")
        return False
    finally:
        conn.close()


def delete_quiz_question(question_id):
    """Delete a single quiz question. Returns True on success."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM quiz_questions WHERE id = ?', (question_id,))
        
        # Auto-reset autoincrement sequence if table is now empty
        row = conn.execute('SELECT COUNT(*) as cnt FROM quiz_questions').fetchone()
        if row and row['cnt'] == 0:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'quiz_questions'")
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting quiz question: {e}")
        return False
    finally:
        conn.close()


def delete_quiz_questions_bulk(ids):
    """Delete multiple quiz questions by ID list. Returns count deleted."""
    if not ids:
        return 0
    conn = get_db()
    try:
        placeholders = ','.join('?' * len(ids))
        cursor = conn.execute(f'DELETE FROM quiz_questions WHERE id IN ({placeholders})', list(ids))
        
        # Auto-reset autoincrement sequence if table is now empty
        row = conn.execute('SELECT COUNT(*) as cnt FROM quiz_questions').fetchone()
        if row and row['cnt'] == 0:
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'quiz_questions'")
            
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error bulk deleting quiz questions: {e}")
        return 0
    finally:
        conn.close()


def import_quiz_questions(questions_list, default_subject='General', default_level='Default'):
    """Bulk import quiz questions from a list of dicts (same format as questions.json).
    Returns (added_count, errors_list, skipped_list)."""
    added = 0
    errors = []
    skipped = []
    conn = get_db()
    try:
        for i, q in enumerate(questions_list):
            try:
                if not q.get('question') or not q.get('options') or not q.get('explanation'):
                    errors.append(f"Q{i+1}: Missing required fields (question/options/explanation).")
                    continue
                if q.get('answerIndex') is None:
                    errors.append(f"Q{i+1}: Missing answerIndex.")
                    continue

                subj = q.get('subject') or default_subject
                lvl = q.get('level') or default_level
                q_json = _json.dumps(q['question'], ensure_ascii=False) if isinstance(q['question'], dict) else q['question']
                o_json = _json.dumps(q['options'], ensure_ascii=False) if isinstance(q['options'], dict) else q['options']
                e_json = _json.dumps(q['explanation'], ensure_ascii=False) if isinstance(q['explanation'], dict) else q['explanation']

                # Duplicate check scoped to subject, question, options
                existing = conn.execute(
                    'SELECT id FROM quiz_questions WHERE subject = ? AND question_json = ? AND options_json = ?',
                    (subj, q_json, o_json)
                ).fetchone()
                
                if existing:
                    skipped.append({
                        "question": q['question'],
                        "subject": subj
                    })
                    continue

                conn.execute(
                    '''INSERT INTO quiz_questions (subject, level, question_json, options_json, answer_index, explanation_json)
                       VALUES (?, ?, ?, ?, ?, ?)''',
                    (subj, lvl, q_json, o_json, int(q['answerIndex']), e_json)
                )
                added += 1
            except Exception as e:
                errors.append(f"Q{i+1}: {str(e)}")
        conn.commit()
    except Exception as e:
        print(f"Error importing quiz questions: {e}")
        errors.append(f"Database error: {str(e)}")
    finally:
        conn.close()
    return added, errors, skipped


def get_quiz_question_count():
    """Return total number of quiz questions in the database."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as cnt FROM quiz_questions').fetchone()
        return row['cnt'] if row else 0
    except Exception as e:
        print(f"Error counting quiz questions: {e}")
        return 0
    finally:
        conn.close()


def clear_all_quiz_questions():
    """Delete ALL quiz questions from the database."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM quiz_questions')
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'quiz_questions'")
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing quiz questions: {e}")
        return False
    finally:
        conn.close()


def reset_quiz_questions_from_json(json_path):
    """Clear all questions and re-import from a JSON file. Returns count imported."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            questions_list = _json.load(f)
        clear_all_quiz_questions()
        added, errors, skipped = import_quiz_questions(questions_list)
        if errors:
            print(f"Reset import warnings: {errors}")
        return added
    except Exception as e:
        print(f"Error resetting quiz questions from JSON: {e}")
        return 0


def save_quiz_feedback(question_id, user_id, vote, comments=None):
    """Save user feedback (thumbs up/down and optional comments) for a quiz question."""
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO quiz_feedback (question_id, user_id, vote, comments) 
               VALUES (?, ?, ?, ?)''',
            (question_id, user_id, vote, comments)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving quiz feedback: {e}")
        return False
    finally:
        conn.close()


def get_quiz_feedback_summary():
    """Retrieve a list of questions that have feedback with their ratings and recent comment summaries."""
    conn = get_db()
    try:
        query = '''
            SELECT 
                f.question_id,
                COUNT(CASE WHEN f.vote = 'up' THEN 1 END) as up_votes,
                COUNT(CASE WHEN f.vote = 'down' THEN 1 END) as down_votes,
                q.question_json,
                q.subject,
                q.level
            FROM quiz_feedback f
            LEFT JOIN quiz_questions q ON f.question_id = q.id
            GROUP BY f.question_id
            ORDER BY (up_votes + down_votes) DESC
        '''
        rows = conn.execute(query).fetchall()
        results = []
        for r in rows:
            latest_row = conn.execute(
                '''SELECT comments, created_at FROM quiz_feedback 
                   WHERE question_id = ? AND comments IS NOT NULL AND comments != ""
                   ORDER BY created_at DESC LIMIT 1''',
                (r['question_id'],)
            ).fetchone()
            
            q_text = "Question #" + str(r['question_id'])
            if r['question_json']:
                try:
                    q_data = _json.loads(r['question_json'])
                    if isinstance(q_data, dict):
                        q_text = q_data.get('sa') or q_data.get('en') or list(q_data.values())[0]
                    else:
                        q_text = str(q_data)
                except Exception:
                    q_text = str(r['question_json'])
            
            results.append({
                'question_id': r['question_id'],
                'question_text': q_text,
                'subject': r['subject'] or 'General',
                'level': r['level'] or 'Default',
                'up': r['up_votes'],
                'down': r['down_votes'],
                'latest_text': latest_row['comments'] if latest_row else None,
                'latest_time': latest_row['created_at'] if latest_row else None
            })
        return results
    except Exception as e:
        print(f"Error getting quiz feedback summary: {e}")
        return []
    finally:
        conn.close()


def get_quiz_feedback_details(question_id):
    """Retrieve detailed comments list for a specific quiz question."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT f.vote, f.comments, f.created_at, f.user_id
               FROM quiz_feedback f
               WHERE f.question_id = ?
               ORDER BY f.created_at DESC''',
            (question_id,)
        ).fetchall()
        comments = []
        up = 0
        down = 0
        for r in rows:
            if r['vote'] == 'up':
                up += 1
            else:
                down += 1
            # user_id is stored but users table lives in a different DB;
            # display a generic label rather than attempting a cross-DB JOIN
            user_label = f'User #{r["user_id"]}' if r['user_id'] else 'Anonymous'
            comments.append({
                'vote': r['vote'],
                'text': r['comments'] or '',
                'time': r['created_at'],
                'user': user_label
            })
        return {
            'up': up,
            'down': down,
            'comments': comments
        }
    except Exception as e:
        print(f"Error getting quiz feedback details: {e}")
        return {'up': 0, 'down': 0, 'comments': []}
    finally:
        conn.close()


def clear_quiz_feedback(question_id=None):
    """Clear quiz feedback for one question or all questions."""
    conn = get_db()
    try:
        if question_id:
            conn.execute('DELETE FROM quiz_feedback WHERE question_id = ?', (question_id,))
        else:
            conn.execute('DELETE FROM quiz_feedback')
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing quiz feedback: {e}")
        return False
    finally:
        conn.close()


def get_user_quiz_results(user_id):
    """Fetch quiz results for a specific user, sorted by taken_at descending."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT subject, level, score, total, percentage, lang, taken_at
               FROM quiz_results
               WHERE user_id = ?
               ORDER BY taken_at DESC''',
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting quiz results for user {user_id}: {e}")
        return []
    finally:
        conn.close()


def get_all_quiz_results():
    """Fetch all quiz results from the database, sorted by taken_at descending."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, user_id, subject, level, score, total, percentage, lang, taken_at, guest_name 
               FROM quiz_results 
               ORDER BY taken_at DESC'''
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting all quiz results: {e}")
        return []
    finally:
        conn.close()


def delete_quiz_result(result_id):
    """Delete a single quiz result by ID. Returns True on success."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM quiz_results WHERE id = ?', (result_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting quiz result: {e}")
        return False
    finally:
        conn.close()


def clear_all_quiz_results():
    """Delete ALL quiz results/history from the database."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM quiz_results')
        conn.execute("DELETE FROM sqlite_sequence WHERE name = 'quiz_results'")
        conn.commit()
        return True
    except Exception as e:
        print(f"Error clearing quiz results: {e}")
        return False
    finally:
        conn.close()
