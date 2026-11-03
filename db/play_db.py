"""
Sanskrit Digital Library - Play Database Module

SQLite database for synonym match, word builder, word search game sets, and play results.
"""

import sqlite3
import os
import json as _json
from datetime import datetime

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, 'play.db')


def _create_tables(conn):
    """Internal helper to create all tables and indexes in the provided connection."""
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS synonym_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            time_limit INTEGER DEFAULT 300,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS synonym_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            set_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            synonym TEXT NOT NULL,
            FOREIGN KEY (set_id) REFERENCES synonym_sets(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS word_builder_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            syllables_json TEXT NOT NULL,
            target_words_json TEXT NOT NULL,
            time_limit INTEGER DEFAULT 300,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS word_search_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            grid_size INTEGER NOT NULL DEFAULT 4,
            target_words_json TEXT NOT NULL,
            time_limit INTEGER DEFAULT 300,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS play_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT NOT NULL,
            set_id INTEGER NOT NULL,
            set_title TEXT NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            percentage INTEGER NOT NULL,
            time_taken INTEGER,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_synonym_pairs_set ON synonym_pairs(set_id);
        CREATE INDEX IF NOT EXISTS idx_play_results_user ON play_results(user_id);
    ''')
    conn.commit()


def get_db():
    """Get a database connection with row_factory for dict-like access. Auto-initializes tables if file is missing/empty."""
    db_exists = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    
    if not db_exists:
        try:
            _create_tables(conn)
            print(f"Play database auto-initialized at {DB_PATH}")
        except Exception as e:
            print(f"Error auto-initializing database tables: {e}")
            
    return conn


def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    try:
        _create_tables(conn)
        
        # Migrations to add time_limit column if they don't exist
        for table in ['synonym_sets', 'word_builder_sets', 'word_search_sets']:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN time_limit INTEGER DEFAULT 300")
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists
                pass
        
        print(f"Play database initialized at {DB_PATH}")
    finally:
        conn.close()


# =============================================================================
# SYNONYM MATCH DB OPERATIONS
# =============================================================================

def get_all_synonym_sets():
    """Fetch all synonym sets with their pairs count."""
    conn = get_db()
    try:
        rows = conn.execute('''
            SELECT s.id, s.title, s.created_at, s.updated_at, COUNT(p.id) as pair_count
            FROM synonym_sets s
            LEFT JOIN synonym_pairs p ON s.id = p.set_id
            GROUP BY s.id
            ORDER BY s.id DESC
        ''').fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting synonym sets: {e}")
        return []
    finally:
        conn.close()


def get_synonym_set(set_id):
    """Fetch a single synonym set with all its pairs."""
    conn = get_db()
    try:
        s_row = conn.execute('SELECT * FROM synonym_sets WHERE id = ?', (set_id,)).fetchone()
        if not s_row:
            return None
        
        p_rows = conn.execute('SELECT id, word, synonym FROM synonym_pairs WHERE set_id = ?', (set_id,)).fetchall()
        
        result = dict(s_row)
        result['pairs'] = [dict(p) for p in p_rows]
        return result
    except Exception as e:
        print(f"Error getting synonym set {set_id}: {e}")
        return None
    finally:
        conn.close()


def add_synonym_set(title, pairs, time_limit=300):
    """Create a synonym set and insert its pairs.
    'pairs' should be a list of dicts: [{'word': '...', 'synonym': '...'}, ...]
    """
    conn = get_db()
    try:
        cursor = conn.execute('INSERT INTO synonym_sets (title, time_limit) VALUES (?, ?)', (title, time_limit))
        set_id = cursor.lastrowid
        
        for p in pairs:
            if p.get('word') and p.get('synonym'):
                conn.execute(
                    'INSERT INTO synonym_pairs (set_id, word, synonym) VALUES (?, ?, ?)',
                    (set_id, p['word'].strip(), p['synonym'].strip())
                )
        
        conn.commit()
        return set_id
    except Exception as e:
        print(f"Error adding synonym set: {e}")
        return None
    finally:
        conn.close()


def update_synonym_set(set_id, title, pairs, time_limit=300):
    """Update a synonym set title and replace its pairs."""
    conn = get_db()
    try:
        # Check if set exists
        existing = conn.execute('SELECT id FROM synonym_sets WHERE id = ?', (set_id,)).fetchone()
        if not existing:
            return False
        
        # Update title, time_limit and timestamp
        conn.execute(
            'UPDATE synonym_sets SET title = ?, time_limit = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (title, time_limit, set_id)
        )
        
        # Delete old pairs
        conn.execute('DELETE FROM synonym_pairs WHERE set_id = ?', (set_id,))
        
        # Insert new pairs
        for p in pairs:
            if p.get('word') and p.get('synonym'):
                conn.execute(
                    'INSERT INTO synonym_pairs (set_id, word, synonym) VALUES (?, ?, ?)',
                    (set_id, p['word'].strip(), p['synonym'].strip())
                )
                
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating synonym set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_synonym_set(set_id):
    """Delete a synonym set (cascade deletes pairs)."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM synonym_sets WHERE id = ?', (set_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting synonym set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_synonym_sets_bulk(ids):
    """Delete multiple synonym sets by ID list."""
    if not ids:
        return 0
    conn = get_db()
    try:
        placeholders = ','.join('?' * len(ids))
        cursor = conn.execute(f'DELETE FROM synonym_sets WHERE id IN ({placeholders})', list(ids))
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error bulk deleting synonym sets: {e}")
        return 0
    finally:
        conn.close()


def import_synonym_sets(sets_list):
    """Bulk import synonym sets from a list of dicts.
    Returns (added_count, errors_list).
    """
    added = 0
    errors = []
    for i, s in enumerate(sets_list):
        try:
            title = s.get('title')
            pairs = s.get('pairs', [])
            time_limit = s.get('time_limit', 300)
            if not title:
                errors.append(f"Set {i+1}: Missing title.")
                continue
            if not pairs:
                errors.append(f"Set {i+1} ({title}): Has no pairs.")
                continue
            
            set_id = add_synonym_set(title, pairs, time_limit)
            if set_id:
                added += 1
            else:
                errors.append(f"Set {i+1} ({title}): Failed to save in database.")
        except Exception as e:
            errors.append(f"Set {i+1}: {str(e)}")
    return added, errors


def get_synonym_set_count():
    """Return total count of synonym sets."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as cnt FROM synonym_sets').fetchone()
        return row['cnt'] if row else 0
    except Exception as e:
        print(f"Error counting synonym sets: {e}")
        return 0
    finally:
        conn.close()


# =============================================================================
# WORD BUILDER DB OPERATIONS
# =============================================================================

def get_all_word_builder_sets():
    """Fetch all word builder sets."""
    conn = get_db()
    try:
        rows = conn.execute('SELECT * FROM word_builder_sets ORDER BY id DESC').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['syllables'] = _json.loads(r['syllables_json'])
            d['target_words'] = _json.loads(r['target_words_json'])
            result.append(d)
        return result
    except Exception as e:
        print(f"Error getting word builder sets: {e}")
        return []
    finally:
        conn.close()


def get_word_builder_set(set_id):
    """Fetch a single word builder set."""
    conn = get_db()
    try:
        r = conn.execute('SELECT * FROM word_builder_sets WHERE id = ?', (set_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d['syllables'] = _json.loads(r['syllables_json'])
        d['target_words'] = _json.loads(r['target_words_json'])
        return d
    except Exception as e:
        print(f"Error getting word builder set {set_id}: {e}")
        return None
    finally:
        conn.close()


def _generate_syllables_from_targets(target_words):
    """Internal helper to split target words into Devanagari syllables."""
    import re
    import random
    syllables_set = set()
    for word in target_words:
        if not word:
            continue
        matches = re.findall(r'.्?[ािीुूृेैोौ]?[ःं]?', word.strip())
        idx_match = 0
        while idx_match < len(matches):
            syl = matches[idx_match]
            if syl.endswith('्') and idx_match + 1 < len(matches):
                syl += matches[idx_match+1]
                idx_match += 1
            if syl.strip():
                syllables_set.add(syl.strip())
            idx_match += 1
    syllables_list = list(syllables_set)
    random.shuffle(syllables_list)
    return syllables_list


def add_word_builder_set(title, syllables, target_words, time_limit=300):
    """Add a new word builder set.
    'syllables' and 'target_words' are lists of strings.
    """
    conn = get_db()
    try:
        targets_clean = [t.strip() for t in target_words if t.strip()]
        
        # Auto-generate syllables if empty
        if not syllables or not [s.strip() for s in syllables if s.strip()]:
            syllables_clean = _generate_syllables_from_targets(targets_clean)
        else:
            syllables_clean = [s.strip() for s in syllables if s.strip()]
            
        s_json = _json.dumps(syllables_clean, ensure_ascii=False)
        t_json = _json.dumps(targets_clean, ensure_ascii=False)
        
        cursor = conn.execute(
            'INSERT INTO word_builder_sets (title, syllables_json, target_words_json, time_limit) VALUES (?, ?, ?, ?)',
            (title, s_json, t_json, time_limit)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error adding word builder set: {e}")
        return None
    finally:
        conn.close()


def update_word_builder_set(set_id, title, syllables, target_words, time_limit=300):
    """Update a word builder set."""
    conn = get_db()
    try:
        targets_clean = [t.strip() for t in target_words if t.strip()]
        
        # Auto-generate syllables if empty
        if not syllables or not [s.strip() for s in syllables if s.strip()]:
            syllables_clean = _generate_syllables_from_targets(targets_clean)
        else:
            syllables_clean = [s.strip() for s in syllables if s.strip()]
            
        s_json = _json.dumps(syllables_clean, ensure_ascii=False)
        t_json = _json.dumps(targets_clean, ensure_ascii=False)
        
        conn.execute(
            '''UPDATE word_builder_sets 
               SET title = ?, syllables_json = ?, target_words_json = ?, time_limit = ?, updated_at = CURRENT_TIMESTAMP 
               WHERE id = ?''',
            (title, s_json, t_json, time_limit, set_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating word builder set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_word_builder_set(set_id):
    """Delete a word builder set."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM word_builder_sets WHERE id = ?', (set_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting word builder set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_word_builder_sets_bulk(ids):
    """Delete multiple word builder sets by ID list."""
    if not ids:
        return 0
    conn = get_db()
    try:
        placeholders = ','.join('?' * len(ids))
        cursor = conn.execute(f'DELETE FROM word_builder_sets WHERE id IN ({placeholders})', list(ids))
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error bulk deleting word builder sets: {e}")
        return 0
    finally:
        conn.close()


def import_word_builder_sets(sets_list):
    """Bulk import word builder sets."""
    added = 0
    errors = []
    for i, s in enumerate(sets_list):
        try:
            title = s.get('title')
            syllables = s.get('syllables', [])
            target_words = s.get('target_words', [])
            time_limit = s.get('time_limit', 300)
            if not title:
                errors.append(f"Set {i+1}: Missing title.")
                continue
            if not target_words:
                errors.append(f"Set {i+1} ({title}): Missing target words list.")
                continue
            
            # If syllables list is empty, auto-generate it from target_words
            if not syllables:
                syllables = _generate_syllables_from_targets(target_words)

            if not syllables:
                errors.append(f"Set {i+1} ({title}): Missing syllables list.")
                continue
            
            set_id = add_word_builder_set(title, syllables, target_words, time_limit)
            if set_id:
                added += 1
            else:
                errors.append(f"Set {i+1} ({title}): Failed to save in database.")
        except Exception as e:
            errors.append(f"Set {i+1}: {str(e)}")
    return added, errors


def get_word_builder_set_count():
    """Return total count of word builder sets."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as cnt FROM word_builder_sets').fetchone()
        return row['cnt'] if row else 0
    except Exception as e:
        print(f"Error counting word builder sets: {e}")
        return 0
    finally:
        conn.close()


# =============================================================================
# WORD SEARCH DB OPERATIONS
# =============================================================================

def get_all_word_search_sets():
    """Fetch all word search sets."""
    conn = get_db()
    try:
        rows = conn.execute('SELECT * FROM word_search_sets ORDER BY id DESC').fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d['target_words'] = _json.loads(r['target_words_json'])
            result.append(d)
        return result
    except Exception as e:
        print(f"Error getting word search sets: {e}")
        return []
    finally:
        conn.close()


def get_word_search_set(set_id):
    """Fetch a single word search set."""
    conn = get_db()
    try:
        r = conn.execute('SELECT * FROM word_search_sets WHERE id = ?', (set_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d['target_words'] = _json.loads(r['target_words_json'])
        return d
    except Exception as e:
        print(f"Error getting word search set {set_id}: {e}")
        return None
    finally:
        conn.close()


def add_word_search_set(title, grid_size, target_words, time_limit=300):
    """Add a new word search set.
    'target_words' is a list of strings.
    """
    conn = get_db()
    try:
        targets_clean = [t.strip() for t in target_words if t.strip()]
        t_json = _json.dumps(targets_clean, ensure_ascii=False)
        
        cursor = conn.execute(
            'INSERT INTO word_search_sets (title, grid_size, target_words_json, time_limit) VALUES (?, ?, ?, ?)',
            (title, int(grid_size), t_json, time_limit)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error adding word search set: {e}")
        return None
    finally:
        conn.close()


def update_word_search_set(set_id, title, grid_size, target_words, time_limit=300):
    """Update a word search set."""
    conn = get_db()
    try:
        targets_clean = [t.strip() for t in target_words if t.strip()]
        t_json = _json.dumps(targets_clean, ensure_ascii=False)
        
        conn.execute(
            '''UPDATE word_search_sets 
               SET title = ?, grid_size = ?, target_words_json = ?, time_limit = ?, updated_at = CURRENT_TIMESTAMP 
               WHERE id = ?''',
            (title, int(grid_size), t_json, time_limit, set_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error updating word search set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_word_search_set(set_id):
    """Delete a word search set."""
    conn = get_db()
    try:
        conn.execute('DELETE FROM word_search_sets WHERE id = ?', (set_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting word search set {set_id}: {e}")
        return False
    finally:
        conn.close()


def delete_word_search_sets_bulk(ids):
    """Delete multiple word search sets by ID list."""
    if not ids:
        return 0
    conn = get_db()
    try:
        placeholders = ','.join('?' * len(ids))
        cursor = conn.execute(f'DELETE FROM word_search_sets WHERE id IN ({placeholders})', list(ids))
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        print(f"Error bulk deleting word search sets: {e}")
        return 0
    finally:
        conn.close()


def import_word_search_sets(sets_list):
    """Bulk import word search sets."""
    added = 0
    errors = []
    for i, s in enumerate(sets_list):
        try:
            title = s.get('title')
            grid_size = s.get('grid_size', 4)
            target_words = s.get('target_words', [])
            time_limit = s.get('time_limit', 300)
            if not title:
                errors.append(f"Set {i+1}: Missing title.")
                continue
            if not target_words:
                errors.append(f"Set {i+1} ({title}): Missing target words list.")
                continue
            
            set_id = add_word_search_set(title, grid_size, target_words, time_limit)
            if set_id:
                added += 1
            else:
                errors.append(f"Set {i+1} ({title}): Failed to save in database.")
        except Exception as e:
            errors.append(f"Set {i+1}: {str(e)}")
    return added, errors


def get_word_search_set_count():
    """Return total count of word search sets."""
    conn = get_db()
    try:
        row = conn.execute('SELECT COUNT(*) as cnt FROM word_search_sets').fetchone()
        return row['cnt'] if row else 0
    except Exception as e:
        print(f"Error counting word search sets: {e}")
        return 0
    finally:
        conn.close()


# =============================================================================
# PLAY RESULTS DB OPERATIONS
# =============================================================================

def save_play_result(user_id, game_type, set_id, set_title, score, total, percentage, time_taken):
    """Save a user's game results."""
    conn = get_db()
    try:
        cursor = conn.execute(
            '''INSERT INTO play_results (user_id, game_type, set_id, set_title, score, total, percentage, time_taken) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, game_type, set_id, set_title, score, total, percentage, time_taken)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        print(f"Error saving play result: {e}")
        return None
    finally:
        conn.close()


def get_user_play_results(user_id):
    """Fetch play results history for a given user, sorted by date descending."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, game_type, set_id, set_title, score, total, percentage, time_taken, played_at 
               FROM play_results 
               WHERE user_id = ? 
               ORDER BY played_at DESC''',
            (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error getting user play results: {e}")
        return []
    finally:
        conn.close()
